/*
 * IoT Network Performance Analysis - V2
 *
 * Multi-hop wireless IoT network:
 *
 *   IoT sensor nodes --(multi-hop 802.11b ad-hoc mesh)--> Gateway/Sink
 *
 * The Gateway also hosts the destination application (it plays the role of
 * both "Gateway/Sink" and "Server" from the research design). This keeps the
 * comparison focused on the thing actually under study -- routing-protocol
 * behaviour inside the mesh -- instead of on a second, unrelated wired hop
 * that AODV/OLSR/static would each need a different (and non-comparable)
 * mechanism to reach.
 *
 * Three routing modes, selected with --protocol=:
 *   aodv    Ad hoc On-Demand Distance Vector (reactive)
 *   olsr    Optimized Link State Routing (proactive)
 *   static  Fixed host routes computed once, offline, from node positions:
 *           a BFS shortest-hop tree over an assumed disk connectivity
 *           model (--txRange), installed directly as Ipv4StaticRouting
 *           host routes. This deliberately does NOT use ns-3's
 *           Ipv4GlobalRoutingHelper: that helper builds its routing graph
 *           from shared-channel adjacency, so on a single ad-hoc Wifi
 *           channel it treats every node as one hop from every other node
 *           regardless of real radio range, which defeats multi-hop
 *           routing entirely. Static routes never adapt to real-time link
 *           conditions -- that is the point of this baseline.
 *
 * Every run with the same --nSensors and --posSeed places sensors at the
 * exact same positions regardless of --protocol: positions are drawn from a
 * dedicated std::mt19937 that ns-3's own RNG (used internally by Wifi/AODV/
 * OLSR) never touches, so the routing protocol is the only thing that
 * changes between AODV/OLSR/static runs at a given network size.
 *
 * Output: one CSV row per run, appended/created at
 *   <outDir>/<protocol>_<nSensors>.csv
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/wifi-module.h"
#include "ns3/applications-module.h"
#include "ns3/aodv-module.h"
#include "ns3/olsr-module.h"
#include "ns3/flow-monitor-module.h"

#include <fstream>
#include <queue>
#include <random>
#include <sys/stat.h>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("IotNetworkV2");

int
main(int argc, char* argv[])
{
    // ------------------------------------------------------------------
    // Configuration -- identical for every protocol at a given node count.
    // ------------------------------------------------------------------
    uint32_t nSensors = 10;          // number of IoT sensor nodes
    std::string protocol = "aodv";   // aodv | olsr | static
    double simTime = 100.0;          // total simulation time (s)
    double appStart = 30.0;          // app start time (s); lets routing converge first
    double areaSize = 250.0;         // sensors placed in [0, areaSize] x [0, areaSize] (m)
    double txPowerDbm = 20.0;        // Wifi transmit power (dBm)
    uint32_t packetSize = 512;       // application payload size (bytes)
    std::string dataRate = "8kbps";  // per-sensor CBR application rate
    uint32_t posSeed = 1;            // seed for node-position RNG (independent of ns-3's RNG)
    double txRange = 90.0;           // nominal disk range (m) used ONLY for --protocol=static
    std::string outDir = "results";  // output directory for the CSV file

    CommandLine cmd(__FILE__);
    cmd.AddValue("nSensors", "Number of IoT sensor nodes", nSensors);
    cmd.AddValue("protocol", "Routing protocol: aodv | olsr | static", protocol);
    cmd.AddValue("simTime", "Total simulation time (s)", simTime);
    cmd.AddValue("appStart", "Application start time (s)", appStart);
    cmd.AddValue("areaSize", "Side length of the deployment square (m)", areaSize);
    cmd.AddValue("txPowerDbm", "Wifi transmit power (dBm)", txPowerDbm);
    cmd.AddValue("packetSize", "Application packet size (bytes)", packetSize);
    cmd.AddValue("dataRate", "Per-sensor application data rate", dataRate);
    cmd.AddValue("posSeed", "Seed for node-position RNG (topology reproducibility)", posSeed);
    cmd.AddValue("txRange", "Nominal disk range (m) for static route computation", txRange);
    cmd.AddValue("outDir", "Output directory for the result CSV", outDir);
    cmd.Parse(argc, argv);

    if (protocol != "aodv" && protocol != "olsr" && protocol != "static")
    {
        NS_FATAL_ERROR("Unknown --protocol '" << protocol << "': expected aodv | olsr | static");
    }

    Time::SetResolution(Time::NS);

    // ------------------------------------------------------------------
    // Nodes: N sensors + 1 gateway (gateway is the last node / also the
    // application server / sink for this study).
    // ------------------------------------------------------------------
    NodeContainer sensors;
    sensors.Create(nSensors);
    NodeContainer gateway;
    gateway.Create(1);

    NodeContainer allNodes;
    allNodes.Add(sensors);
    allNodes.Add(gateway);
    uint32_t gatewayIndex = nSensors;

    // ------------------------------------------------------------------
    // Positions: fixed, static IoT deployment.
    // Gateway sits at the centre of the field; sensors are placed
    // uniformly at random. Drawn from an independent RNG seeded only by
    // posSeed, so the same --posSeed/--nSensors always yields the same
    // layout no matter which --protocol is selected.
    // ------------------------------------------------------------------
    Ptr<ListPositionAllocator> positionAlloc = CreateObject<ListPositionAllocator>();

    std::mt19937 posRng(posSeed);
    std::uniform_real_distribution<double> coord(0.0, areaSize);
    for (uint32_t i = 0; i < nSensors; ++i)
    {
        positionAlloc->Add(Vector(coord(posRng), coord(posRng), 0.0));
    }
    positionAlloc->Add(Vector(areaSize / 2.0, areaSize / 2.0, 0.0)); // gateway, field centre

    MobilityHelper mobility;
    mobility.SetPositionAllocator(positionAlloc);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel"); // static IoT nodes
    mobility.Install(allNodes);

    // ------------------------------------------------------------------
    // Wireless PHY/MAC: single shared 802.11b ad-hoc channel for the
    // whole mesh. Parameters match ns-3's own canonical MANET routing
    // comparison example (examples/routing/manet-routing-compare.cc),
    // known to produce genuine multi-hop topologies at these ranges.
    // ------------------------------------------------------------------
    // 1 Mbps DSSS: the most robust, longest-range 802.11b mode. Real IoT
    // sensor radios trade throughput for range/robustness, so this is a
    // more representative choice than a high-rate mode for this scenario.
    // NonUnicastMode must be set explicitly to the same mode, otherwise
    // broadcast frames (ARP, and AODV/OLSR hello/control traffic) default
    // to a different rate than unicast data and can fail even when the
    // data link itself would work fine.
    Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode",
                        StringValue("DsssRate1Mbps"));

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211b);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode", StringValue("DsssRate1Mbps"),
                                 "ControlMode", StringValue("DsssRate1Mbps"));

    // Log-distance path loss (not free-space Friis): a sensor field has
    // ground-level obstructions, so attenuation is steeper than free space.
    // This gives a realistic, finite radio range that forces genuine
    // multi-hop relaying instead of most sensors reaching the gateway
    // directly.
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

    // ------------------------------------------------------------------
    // Routing + Internet stack.
    // ------------------------------------------------------------------
    InternetStackHelper internet;

    AodvHelper aodv;
    OlsrHelper olsr;
    Ipv4ListRoutingHelper list;

    if (protocol == "aodv")
    {
        list.Add(aodv, 10);
        internet.SetRoutingHelper(list);
    }
    else if (protocol == "olsr")
    {
        list.Add(olsr, 10);
        internet.SetRoutingHelper(list);
    }
    // "static": leave the default stack (Ipv4StaticRouting); host routes are
    // computed and installed manually below (see the BFS block).

    internet.Install(allNodes);

    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    Ipv4Address gatewayAddr = interfaces.GetAddress(gatewayIndex);

    if (protocol == "static")
    {
        // Build an assumed disk-connectivity graph from node positions
        // (edge if distance <= txRange), then BFS from the gateway to get
        // each sensor's next hop on the shortest path back to it. This is
        // the fixed routing table a "static routing" baseline is meant to
        // represent -- computed once, offline, and never updated again.
        uint32_t n = allNodes.GetN();
        std::vector<Vector> pos(n);
        for (uint32_t i = 0; i < n; ++i)
        {
            pos[i] = allNodes.Get(i)->GetObject<MobilityModel>()->GetPosition();
        }

        std::vector<std::vector<uint32_t>> adjacency(n);
        for (uint32_t i = 0; i < n; ++i)
        {
            for (uint32_t j = i + 1; j < n; ++j)
            {
                if (CalculateDistance(pos[i], pos[j]) <= txRange)
                {
                    adjacency[i].push_back(j);
                    adjacency[j].push_back(i);
                }
            }
        }

        std::vector<bool> visited(n, false);
        std::vector<int64_t> parent(n, -1); // parent[v] = v's next hop toward the gateway
        std::queue<uint32_t> bfsQueue;
        visited[gatewayIndex] = true;
        bfsQueue.push(gatewayIndex);
        while (!bfsQueue.empty())
        {
            uint32_t u = bfsQueue.front();
            bfsQueue.pop();
            for (uint32_t v : adjacency[u])
            {
                if (!visited[v])
                {
                    visited[v] = true;
                    parent[v] = u;
                    bfsQueue.push(v);
                }
            }
        }

        Ipv4StaticRoutingHelper staticRoutingHelper;
        uint32_t unreachable = 0;
        for (uint32_t i = 0; i < nSensors; ++i)
        {
            if (parent[i] == -1)
            {
                ++unreachable;
                continue;
            }
            Ptr<Ipv4> ipv4 = sensors.Get(i)->GetObject<Ipv4>();
            Ptr<Ipv4StaticRouting> staticRouting = staticRoutingHelper.GetStaticRouting(ipv4);
            Ipv4Address nextHopAddr = interfaces.GetAddress(static_cast<uint32_t>(parent[i]));
            uint32_t ifIndex = ipv4->GetInterfaceForDevice(devices.Get(i));
            staticRouting->AddHostRouteTo(gatewayAddr, nextHopAddr, ifIndex);
        }
        if (unreachable > 0)
        {
            std::cout << "  Note: " << unreachable << " sensor(s) have no path to the gateway "
                      << "within the assumed static-route range (txRange=" << txRange
                      << " m) and are unreachable under static routing by construction.\n";
        }
    }

    // ------------------------------------------------------------------
    // Applications: every sensor sends periodic UDP traffic to the
    // gateway. One flow per sensor, so offered load scales with network
    // size, matching how many real reporting sensors would generate.
    // ------------------------------------------------------------------
    uint16_t port = 9;

    PacketSinkHelper sinkHelper("ns3::UdpSocketFactory",
                                 InetSocketAddress(Ipv4Address::GetAny(), port));
    ApplicationContainer sinkApp = sinkHelper.Install(gateway.Get(0));
    sinkApp.Start(Seconds(0.0));
    sinkApp.Stop(Seconds(simTime));

    ApplicationContainer sourceApps;
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
        sourceApps.Add(app);
    }

    // ------------------------------------------------------------------
    // FlowMonitor: aggregate PDR / throughput / delay over all
    // sensor -> gateway flows.
    // ------------------------------------------------------------------
    FlowMonitorHelper flowmonHelper;
    Ptr<FlowMonitor> monitor = flowmonHelper.InstallAll();

    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    monitor->CheckForLostPackets();
    Ptr<Ipv4FlowClassifier> classifier =
        DynamicCast<Ipv4FlowClassifier>(flowmonHelper.GetClassifier());

    uint64_t totalTx = 0;
    uint64_t totalRx = 0;
    uint64_t totalRxBytes = 0;
    double totalDelaySum = 0.0; // seconds, summed over received packets

    for (const auto& flow : monitor->GetFlowStats())
    {
        Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(flow.first);
        if (t.destinationAddress != gatewayAddr)
        {
            continue;
        }
        totalTx += flow.second.txPackets;
        totalRx += flow.second.rxPackets;
        totalRxBytes += flow.second.rxBytes;
        totalDelaySum += flow.second.delaySum.GetSeconds();
    }

    uint64_t lost = (totalTx >= totalRx) ? (totalTx - totalRx) : 0;
    double pdr = (totalTx > 0) ? (100.0 * static_cast<double>(totalRx) / totalTx) : 0.0;
    double avgDelay = (totalRx > 0) ? (totalDelaySum / totalRx) : 0.0;
    double measurementWindow = simTime - appStart;
    double throughputKbps =
        (measurementWindow > 0) ? (totalRxBytes * 8.0 / 1000.0 / measurementWindow) : 0.0;

    std::cout << "========================================\n"
              << "  Protocol   : " << protocol << "\n"
              << "  Sensors    : " << nSensors << "\n"
              << "  Tx packets : " << totalTx << "\n"
              << "  Rx packets : " << totalRx << "\n"
              << "  Packet loss: " << lost << "\n"
              << "  PDR (%)    : " << pdr << "\n"
              << "  Throughput : " << throughputKbps << " kbps\n"
              << "  Avg delay  : " << avgDelay << " s\n"
              << "========================================\n";

    // One row is appended per run. A given (protocol, nSensors) scenario is
    // meant to be run several times with different --posSeed values (see
    // experiments/run_experiments.sh) and averaged during analysis --
    // a single random topology draw is not a statistically meaningful
    // result on its own.
    mkdir(outDir.c_str(), 0755); // no-op if it already exists
    std::string outFile = outDir + "/" + protocol + "_" + std::to_string(nSensors) + ".csv";
    bool writeHeader = true;
    {
        std::ifstream existing(outFile);
        writeHeader = !existing.good();
    }
    std::ofstream out(outFile, std::ios::out | std::ios::app);
    if (writeHeader)
    {
        out << "RoutingProtocol,NumberOfNodes,PosSeed,PacketsSent,PacketsReceived,PacketLoss,PDR,"
               "ThroughputKbps,AverageDelaySec\n";
    }
    out << protocol << "," << nSensors << "," << posSeed << "," << totalTx << "," << totalRx
        << "," << lost << "," << pdr << "," << throughputKbps << "," << avgDelay << "\n";
    out.close();

    Simulator::Destroy();
    return 0;
}
