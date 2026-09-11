/*
 * iot-network-bottleneck-probe.cc  --  §10 INSTRUMENTED BOTTLENECK PROBE
 *
 * A SEPARATE simulator (scratch/iot-network-v3-ext.cc is never edited). It replicates the
 * V3 Official topology / PHY / MAC / traffic exactly (uniform-random sensors from
 * std::mt19937(seed), gateway at field centre, 802.11b ad-hoc DSSS 1 Mbps, LogDistance
 * exponent 3.0 / refLoss 40, 512 B UDP CBR, 300 s, appStart 30 s) for --protocol=olsr|static
 * only, and adds PER-NODE instrumentation to localise packet loss:
 *
 *   - node position + hop-distance to gateway (BFS over the 90 m disk graph)
 *   - per-node PHY channel state time (TX / RX / CCA_BUSY) -> airtime "busy" fraction
 *   - per-node PHY RX drops (collisions / undecodable)
 *   - per-node WifiMac queue drops (buffer overflow)  [DropBeforeEnqueue + DropAfterDequeue]
 *   - per-node Ipv4L3Protocol drops split by reason (NO_ROUTE / TTL / ROUTE_ERROR / QUEUE / other)
 *   - per-node PHY TX packets & bytes (load carried on air)
 *   - per-node L3 unicast-forward count (relay load) and app-level originated count
 *   - per-node MAC retry-exhaustion drops (WifiRemoteStationManager::MacTxFinalDataFailed --
 *     fires once per MPDU that is finally dropped after exceeding the retry limit; distinct
 *     from MacTxDataFailed, which fires on every individual failed attempt including ones
 *     later retried successfully) [added for the retry-exhaustion measurement gap]
 *
 * --offeredRateKbps (added for the Phase-1 offered-rate-sweep experiment): optional override
 * of the per-sensor OnOff DataRate. Default 0.0 is a sentinel meaning "unset" -- the existing
 * --trafficLevel=medium|high -> 8/16 kbps mapping is used unchanged, so every prior invocation
 * (§10, retry-exhaustion) reproduces byte-identical behavior. When > 0, it overrides the
 * per-sensor rate directly; --trafficLevel is still required (kept as the run's output-file
 * label) but no longer determines the actual rate in that case. The actual applied rate is
 * always recorded in probe_aggregate.csv's offered_rate_kbps column.
 *
 * Output (into --outDir):
 *   probe_aggregate.csv                          -- one appended row per run (run-level summary)
 *   pernode/probe_<proto>_<n>_<traffic>_seed<s>.csv  -- one row per node
 *
 * Read-only w.r.t. every existing dataset; writes only into --outDir.
 */
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/wifi-module.h"
#include "ns3/applications-module.h"
#include "ns3/olsr-module.h"
#include "ns3/flow-monitor-module.h"

#include <fstream>
#include <sstream>
#include <queue>
#include <random>
#include <map>
#include <vector>
#include <cmath>
#include <ctime>
#include <sys/stat.h>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("IotBottleneckProbe");

// ------------------------------------------------------------------ per-node accumulators
struct NodeStat
{
    double txTime = 0.0, rxTime = 0.0, ccaBusyTime = 0.0;   // seconds in each PHY state
    uint64_t phyTxPkts = 0, phyTxBytes = 0;
    uint64_t phyRxDrops = 0;
    uint64_t macQueueDrops = 0;
    uint64_t maxRetryDrops = 0;
    uint64_t ipDropNoRoute = 0, ipDropTtl = 0, ipDropRouteErr = 0, ipDropQueue = 0, ipDropOther = 0;
    uint64_t l3UnicastForward = 0;
    uint64_t appOriginated = 0;
};
static std::vector<NodeStat> g_stat;

static void OnPhyState(uint32_t node, Time /*start*/, Time duration, WifiPhyState state)
{
    if (node >= g_stat.size()) return;
    double d = duration.GetSeconds();
    switch (state)
    {
    case WifiPhyState::TX:       g_stat[node].txTime += d; break;
    case WifiPhyState::RX:       g_stat[node].rxTime += d; break;
    case WifiPhyState::CCA_BUSY: g_stat[node].ccaBusyTime += d; break;
    default: break;
    }
}
static void OnPhyTxBegin(uint32_t node, Ptr<const Packet> p, double /*txPowerW*/)
{
    if (node >= g_stat.size()) return;
    g_stat[node].phyTxPkts++;
    g_stat[node].phyTxBytes += p->GetSize();
}
static void OnPhyRxDrop(uint32_t node, Ptr<const Packet> /*p*/, WifiPhyRxfailureReason /*r*/)
{
    if (node < g_stat.size()) g_stat[node].phyRxDrops++;
}
static void OnMacQueueDrop(uint32_t node, Ptr<const WifiMpdu> /*mpdu*/)
{
    if (node < g_stat.size()) g_stat[node].macQueueDrops++;
}
static void OnMacTxFinalDataFailed(uint32_t node, Mac48Address /*addr*/)
{
    if (node < g_stat.size()) g_stat[node].maxRetryDrops++;
}
static void OnIpDrop(uint32_t node, const Ipv4Header& /*h*/, Ptr<const Packet> /*p*/,
                     Ipv4L3Protocol::DropReason reason, Ptr<Ipv4> /*ipv4*/, uint32_t /*iface*/)
{
    if (node >= g_stat.size()) return;
    // NB: ns-3's Ipv4L3Protocol::DropReason has NO queue-overflow value in this build --
    // buffer overflow is captured separately via the WifiMac queue Drop traces
    // (g_stat[].macQueueDrops). ip_drop_queue therefore stays 0 from the IP layer.
    switch (reason)
    {
    case Ipv4L3Protocol::DROP_NO_ROUTE:    g_stat[node].ipDropNoRoute++; break;
    case Ipv4L3Protocol::DROP_TTL_EXPIRED: g_stat[node].ipDropTtl++; break;
    case Ipv4L3Protocol::DROP_ROUTE_ERROR: g_stat[node].ipDropRouteErr++; break;
    default:                               g_stat[node].ipDropOther++; break;
    }
}
static void OnUnicastForward(uint32_t node, const Ipv4Header& /*h*/, Ptr<const Packet> /*p*/, uint32_t /*iface*/)
{
    if (node < g_stat.size()) g_stat[node].l3UnicastForward++;
}
static void OnAppTx(uint32_t node, Ptr<const Packet> /*p*/)
{
    if (node < g_stat.size()) g_stat[node].appOriginated++;
}

int
main(int argc, char* argv[])
{
    std::string protocol = "static";     // olsr | static
    uint32_t nSensors = 50;
    std::string trafficLevel = "medium"; // medium | high
    uint32_t seed = 20;
    double simTime = 300.0;
    double appStart = 30.0;
    double areaSize = 250.0;
    double txPowerDbm = 20.0;
    double txRange = 90.0;
    uint32_t packetSize = 512;
    std::string outDir = "analysis/bottleneck-characterisation/data";
    double offeredRateKbps = 0.0;   // 0.0 = unset -> use trafficLevel default (preserves prior behavior)

    CommandLine cmd(__FILE__);
    cmd.AddValue("protocol", "olsr | static", protocol);
    cmd.AddValue("nSensors", "number of IoT sensor nodes", nSensors);
    cmd.AddValue("trafficLevel", "medium | high", trafficLevel);
    cmd.AddValue("offeredRateKbps", "override per-sensor offered rate (kbps); 0=unset, use trafficLevel default", offeredRateKbps);
    cmd.AddValue("seed", "seed for topology and ns-3 RNG", seed);
    cmd.AddValue("simTime", "simulation time (s)", simTime);
    cmd.AddValue("appStart", "application start time (s)", appStart);
    cmd.AddValue("areaSize", "deployment square side (m)", areaSize);
    cmd.AddValue("txPowerDbm", "wifi tx power (dBm)", txPowerDbm);
    cmd.AddValue("txRange", "nominal disk range (m) for static routes / hop distance", txRange);
    cmd.AddValue("packetSize", "application payload size (bytes)", packetSize);
    cmd.AddValue("outDir", "output directory", outDir);
    cmd.Parse(argc, argv);

    if (protocol != "olsr" && protocol != "static")
        NS_FATAL_ERROR("probe supports only --protocol=olsr|static (got '" << protocol << "')");
    if (trafficLevel != "medium" && trafficLevel != "high")
        NS_FATAL_ERROR("probe supports only --trafficLevel=medium|high (got '" << trafficLevel << "')");

    const double defaultRateKbps = (trafficLevel == "high") ? 16.0 : 8.0;
    const double actualRateKbps = (offeredRateKbps > 0.0) ? offeredRateKbps : defaultRateKbps;
    std::ostringstream rateStream;
    rateStream << actualRateKbps << "kbps";   // e.g. "16kbps" -- matches the original literal
    const std::string dataRate = rateStream.str();
    Time::SetResolution(Time::NS);
    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(1);

    NodeContainer sensors;  sensors.Create(nSensors);
    NodeContainer gateway;  gateway.Create(1);
    NodeContainer allNodes; allNodes.Add(sensors); allNodes.Add(gateway);
    const uint32_t gatewayIndex = nSensors;
    const uint32_t n = nSensors + 1;

    // positions -- identical method to iot-network-v3-ext.cc
    std::mt19937 posRng(seed);
    std::uniform_real_distribution<double> coord(0.0, areaSize);
    Ptr<ListPositionAllocator> sensorAlloc = CreateObject<ListPositionAllocator>();
    for (uint32_t i = 0; i < nSensors; ++i)
        sensorAlloc->Add(Vector(coord(posRng), coord(posRng), 0.0));
    MobilityHelper sensorMobility;
    sensorMobility.SetPositionAllocator(sensorAlloc);
    sensorMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel"); // probe is static-mobility only
    sensorMobility.Install(sensors);

    MobilityHelper gwMob;
    Ptr<ListPositionAllocator> gwAlloc = CreateObject<ListPositionAllocator>();
    gwAlloc->Add(Vector(areaSize / 2.0, areaSize / 2.0, 0.0));
    gwMob.SetPositionAllocator(gwAlloc);
    gwMob.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    gwMob.Install(gateway);

    // wifi PHY/MAC -- identical
    Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode", StringValue("DsssRate1Mbps"));
    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211b);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode", StringValue("DsssRate1Mbps"),
                                 "ControlMode", StringValue("DsssRate1Mbps"));
    YansWifiChannelHelper wifiChannel;
    wifiChannel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    wifiChannel.AddPropagationLoss("ns3::LogDistancePropagationLossModel",
                                   "Exponent", DoubleValue(3.0),
                                   "ReferenceDistance", DoubleValue(1.0),
                                   "ReferenceLoss", DoubleValue(40.0));
    YansWifiPhyHelper wifiPhy;
    wifiPhy.SetChannel(wifiChannel.Create());
    wifiPhy.Set("TxPowerStart", DoubleValue(txPowerDbm));
    wifiPhy.Set("TxPowerEnd", DoubleValue(txPowerDbm));
    WifiMacHelper wifiMac;
    wifiMac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(wifiPhy, wifiMac, allNodes);

    g_stat.assign(n, NodeStat());

    // routing
    InternetStackHelper internet;
    OlsrHelper olsr;
    Ipv4ListRoutingHelper list;
    if (protocol == "olsr")
    {
        list.Add(olsr, 10);
        internet.SetRoutingHelper(list);
    }
    internet.Install(allNodes);
    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);
    Ipv4Address gatewayAddr = interfaces.GetAddress(gatewayIndex);

    // disk-connectivity adjacency + BFS from gateway  -> hop distance for every node
    std::vector<Vector> pos(n);
    for (uint32_t i = 0; i < n; ++i)
        pos[i] = allNodes.Get(i)->GetObject<MobilityModel>()->GetPosition();
    std::vector<std::vector<uint32_t>> adj(n);
    for (uint32_t i = 0; i < n; ++i)
        for (uint32_t j = i + 1; j < n; ++j)
            if (CalculateDistance(pos[i], pos[j]) <= txRange)
            {
                adj[i].push_back(j);
                adj[j].push_back(i);
            }
    std::vector<int64_t> hop(n, -1), parent(n, -1);
    {
        std::queue<uint32_t> q;
        hop[gatewayIndex] = 0;
        q.push(gatewayIndex);
        while (!q.empty())
        {
            uint32_t u = q.front();
            q.pop();
            for (uint32_t v : adj[u])
                if (hop[v] < 0)
                {
                    hop[v] = hop[u] + 1;
                    parent[v] = static_cast<int64_t>(u);
                    q.push(v);
                }
        }
    }
    uint32_t unreachable = 0;
    for (uint32_t i = 0; i < nSensors; ++i)
        if (hop[i] < 0) ++unreachable;

    // static routing: install BFS parent tree toward gateway
    if (protocol == "static")
    {
        Ipv4StaticRoutingHelper srh;
        for (uint32_t i = 0; i < nSensors; ++i)
        {
            if (parent[i] < 0) continue;
            Ptr<Ipv4> ipv4 = sensors.Get(i)->GetObject<Ipv4>();
            Ptr<Ipv4StaticRouting> sr = srh.GetStaticRouting(ipv4);
            Ipv4Address nh = interfaces.GetAddress(static_cast<uint32_t>(parent[i]));
            uint32_t iff = ipv4->GetInterfaceForDevice(devices.Get(i));
            sr->AddHostRouteTo(gatewayAddr, nh, iff);
        }
    }

    // ---- instrumentation hookups (per node, bound callbacks) ----
    for (uint32_t i = 0; i < n; ++i)
    {
        std::string base = "/NodeList/" + std::to_string(i) + "/DeviceList/0/$ns3::WifiNetDevice/";
        Config::ConnectWithoutContext(base + "Phy/State/State",
                                      MakeBoundCallback(&OnPhyState, i));
        Config::ConnectWithoutContext(base + "Phy/PhyTxBegin",
                                      MakeBoundCallback(&OnPhyTxBegin, i));
        Config::ConnectWithoutContext(base + "Phy/PhyRxDrop",
                                      MakeBoundCallback(&OnPhyRxDrop, i));
        // adhoc MAC single Txop queue
        Config::ConnectWithoutContext(base + "Mac/$ns3::AdhocWifiMac/Txop/Queue/DropBeforeEnqueue",
                                      MakeBoundCallback(&OnMacQueueDrop, i));
        Config::ConnectWithoutContext(base + "Mac/$ns3::AdhocWifiMac/Txop/Queue/DropAfterDequeue",
                                      MakeBoundCallback(&OnMacQueueDrop, i));
        Config::ConnectWithoutContext(base + "RemoteStationManager/MacTxFinalDataFailed",
                                      MakeBoundCallback(&OnMacTxFinalDataFailed, i));
        Config::ConnectWithoutContext("/NodeList/" + std::to_string(i) + "/$ns3::Ipv4L3Protocol/Drop",
                                      MakeBoundCallback(&OnIpDrop, i));
        Config::ConnectWithoutContext("/NodeList/" + std::to_string(i) + "/$ns3::Ipv4L3Protocol/UnicastForward",
                                      MakeBoundCallback(&OnUnicastForward, i));
    }

    // applications
    uint16_t port = 9;
    PacketSinkHelper sinkHelper("ns3::UdpSocketFactory",
                                InetSocketAddress(Ipv4Address::GetAny(), port));
    ApplicationContainer sinkApp = sinkHelper.Install(gateway.Get(0));
    sinkApp.Start(Seconds(0.0));
    sinkApp.Stop(Seconds(simTime));
    for (uint32_t i = 0; i < nSensors; ++i)
    {
        OnOffHelper onoff("ns3::UdpSocketFactory", InetSocketAddress(gatewayAddr, port));
        onoff.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
        onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
        onoff.SetAttribute("PacketSize", UintegerValue(packetSize));
        onoff.SetAttribute("DataRate", StringValue(dataRate));
        ApplicationContainer app = onoff.Install(sensors.Get(i));
        app.Start(Seconds(appStart));
        app.Stop(Seconds(simTime));
        app.Get(0)->TraceConnectWithoutContext("Tx", MakeBoundCallback(&OnAppTx, i));
    }

    FlowMonitorHelper flowmonHelper;
    Ptr<FlowMonitor> monitor = flowmonHelper.InstallAll();

    Simulator::Stop(Seconds(simTime));
    Simulator::Run();
    monitor->CheckForLostPackets();

    // ---- aggregate FlowMonitor stats (gateway-bound app flows only) ----
    Ptr<Ipv4FlowClassifier> classifier =
        DynamicCast<Ipv4FlowClassifier>(flowmonHelper.GetClassifier());
    uint64_t txPkts = 0, rxPkts = 0, rxBytes = 0, routingOverheadPkts = 0;
    double delaySum = 0.0, jitterSum = 0.0;
    for (const auto& f : monitor->GetFlowStats())
    {
        Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(f.first);
        if (t.destinationPort == 698 || t.sourcePort == 698 || t.destinationPort == 654 ||
            t.sourcePort == 654)
        {
            routingOverheadPkts += f.second.txPackets;
            continue;
        }
        if (t.destinationAddress != gatewayAddr) continue;
        txPkts += f.second.txPackets;
        rxPkts += f.second.rxPackets;
        rxBytes += f.second.rxBytes;
        delaySum += f.second.delaySum.GetSeconds();
        jitterSum += f.second.jitterSum.GetSeconds();
    }
    double pdr = txPkts ? 100.0 * rxPkts / txPkts : 0.0;
    double measWindow = simTime - appStart;
    double thrKbps = measWindow > 0 ? (rxBytes * 8.0) / (measWindow * 1000.0) : 0.0;
    double avgDelay = rxPkts ? delaySum / rxPkts : 0.0;
    double avgJitter = (rxPkts > 1) ? jitterSum / (rxPkts - 1) : 0.0;

    Simulator::Destroy();

    // ---- write per-node CSV ----
    mkdir("analysis", 0755);
    mkdir("analysis/bottleneck-characterisation", 0755);
    mkdir(outDir.c_str(), 0755);
    std::string pndir = outDir + "/pernode";
    mkdir(pndir.c_str(), 0755);

    Vector gwPos(areaSize / 2.0, areaSize / 2.0, 0.0);
    std::ostringstream pn;
    pn << pndir << "/probe_" << protocol << "_" << nSensors << "_" << trafficLevel
       << "_seed" << seed << ".csv";
    std::ofstream pf(pn.str());
    pf << "node_id,is_gateway,x,y,dist_to_gw_m,hop_to_gw,airtime_tx_s,airtime_rx_s,"
          "airtime_ccabusy_s,airtime_busy_frac,phy_tx_pkts,phy_tx_bytes,phy_rx_drops,"
          "mac_queue_drops,max_retry_drops,ip_drop_no_route,ip_drop_ttl,ip_drop_route_error,ip_drop_queue,"
          "ip_drop_other,app_pkts_originated,l3_unicast_forwarded\n";
    double gwBusy = 0.0, ring1BusySum = 0.0, restBusySum = 0.0;
    uint32_t ring1Cnt = 0, restCnt = 0;
    for (uint32_t i = 0; i < n; ++i)
    {
        const NodeStat& s = g_stat[i];
        double busyFrac = (s.txTime + s.rxTime + s.ccaBusyTime) / simTime;
        double d = CalculateDistance(pos[i], gwPos);
        int isGw = (i == gatewayIndex) ? 1 : 0;
        pf << i << "," << isGw << "," << pos[i].x << "," << pos[i].y << "," << d << ","
           << hop[i] << "," << s.txTime << "," << s.rxTime << "," << s.ccaBusyTime << ","
           << busyFrac << "," << s.phyTxPkts << "," << s.phyTxBytes << "," << s.phyRxDrops << ","
           << s.macQueueDrops << "," << s.maxRetryDrops << "," << s.ipDropNoRoute << "," << s.ipDropTtl << ","
           << s.ipDropRouteErr << "," << s.ipDropQueue << "," << s.ipDropOther << ","
           << s.appOriginated << "," << s.l3UnicastForward << "\n";
        if (isGw) gwBusy = busyFrac;
        else if (hop[i] == 1) { ring1BusySum += busyFrac; ring1Cnt++; }
        else { restBusySum += busyFrac; restCnt++; }
    }
    pf.close();

    // ---- append aggregate row ----
    uint64_t totPhyRxDrop = 0, totMacQDrop = 0, totMaxRetryDrop = 0, totNoRoute = 0, totTtl = 0,
             totRouteErr = 0, totQueue = 0, totOther = 0;
    for (uint32_t i = 0; i < n; ++i)
    {
        totPhyRxDrop += g_stat[i].phyRxDrops;
        totMacQDrop += g_stat[i].macQueueDrops;
        totMaxRetryDrop += g_stat[i].maxRetryDrops;
        totNoRoute += g_stat[i].ipDropNoRoute;
        totTtl += g_stat[i].ipDropTtl;
        totRouteErr += g_stat[i].ipDropRouteErr;
        totQueue += g_stat[i].ipDropQueue;
        totOther += g_stat[i].ipDropOther;
    }
    std::string aggPath = outDir + "/probe_aggregate.csv";
    bool writeHeader = true;
    {
        std::ifstream ex(aggPath);
        writeHeader = !ex.good();
    }
    std::ofstream af(aggPath, std::ios::out | std::ios::app);
    if (writeHeader)
        af << "timestamp,protocol,nodes,trafficLevel,offered_rate_kbps,seed,simTime,txPkts,rxPkts,pdr,"
              "throughputKbps,avgDelaySec,avgJitterSec,unreachableSensors,routingOverheadPkts,"
              "total_phy_rx_drops,total_mac_queue_drops,total_max_retry_drops,total_ip_drop_no_route,total_ip_drop_ttl,"
              "total_ip_drop_route_error,total_ip_drop_queue,total_ip_drop_other,"
              "gw_airtime_busy_frac,ring1_airtime_busy_frac_mean,rest_airtime_busy_frac_mean,"
              "ring1_node_count\n";
    af << static_cast<int64_t>(std::time(nullptr)) << "," << protocol << "," << nSensors << ","
       << trafficLevel << "," << actualRateKbps << "," << seed << "," << simTime << "," << txPkts << "," << rxPkts << ","
       << pdr << "," << thrKbps << "," << avgDelay << "," << avgJitter << "," << unreachable << ","
       << routingOverheadPkts << "," << totPhyRxDrop << "," << totMacQDrop << "," << totMaxRetryDrop << "," << totNoRoute << ","
       << totTtl << "," << totRouteErr << "," << totQueue << "," << totOther << "," << gwBusy << ","
       << (ring1Cnt ? ring1BusySum / ring1Cnt : 0.0) << ","
       << (restCnt ? restBusySum / restCnt : 0.0) << "," << ring1Cnt << "\n";
    af.close();

    std::cout << "probe done: " << protocol << " n=" << nSensors << " traffic=" << trafficLevel
              << " rate=" << actualRateKbps << "kbps"
              << " seed=" << seed << "  PDR=" << pdr << "%  thr=" << thrKbps << "kbps"
              << "  unreachable=" << unreachable << "  phyRxDrop=" << totPhyRxDrop
              << "  macQdrop=" << totMacQDrop << "  maxRetryDrop=" << totMaxRetryDrop
              << "  ipDropQueue=" << totQueue
              << "  ipDropNoRoute=" << totNoRoute
              << "  gwBusy=" << gwBusy << "  ring1Busy=" << (ring1Cnt ? ring1BusySum / ring1Cnt : 0.0)
              << "\n";
    return 0;
}
