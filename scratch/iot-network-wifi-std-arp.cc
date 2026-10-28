/*
 * iot-network-wifi-std-arp.cc  --  copy of scratch/iot-network-wifi-std.cc (never edited) + ARP fix/counters
 * (2026-10-16). Only two additions:
 *   --arpPrepopulate (default false): NeighborCacheHelper::PopulateNeighborCache() after address assignment,
 *       so no ARP request is ever needed. Off: behaviour identical to iot-network-wifi-std.cc.
 *   ARP drop counters: ArpL3Protocol "Drop" (dead entry / pending queue full / reply for unknown entry) and
 *       ArpCache "Drop" (pending packets discarded when WaitReply exceeds MaxRetries), per node. Appended as the
 *       LAST columns of wifistd_ext.csv (arp_prepopulate,total_arp_l3_drops,total_arp_cache_drops) and of
 *       the pernode_ext CSV (arp_l3_drops,arp_cache_drops). probe_aggregate.csv, the pernode CSV and stdout unchanged.
 * Original header follows.
 * iot-network-wifi-std.cc  --  Phase I bottleneck study with a selectable Wi-Fi standard
 *
 * A NEW simulator copied from scratch/iot-network-bottleneck-probe.cc (which is never edited).
 * Topology, propagation, traffic, routing and instrumentation are those of the probe:
 * uniform-random sensors from std::mt19937(seed), gateway at the field centre, LogDistance
 * exponent 3.0 / reference loss 40 dB / 20 dBm, 512 B UDP CBR, 300 s, appStart 30 s,
 * AdhocWifiMac, one shared YansWifiChannel, --protocol=aodv|olsr|static, 90 m BFS disk for the
 * Static tree and hop labels. AODV is set up exactly as in scratch/iot-network-v3-ext.cc,
 * including its 5 s path sampler (AODV RouteOutput refreshes route lifetimes, so the sampler
 * is part of the AODV behaviour being reproduced); the sampler runs for AODV only.
 *
 *   --standard=80211b   (default) the probe's PHY/MAC exactly: DSSS 1 Mbps data, control and
 *                       non-unicast. probe_aggregate.csv and pernode/*.csv are byte-identical
 *                       to the probe's (except the wall-clock timestamp column).
 *   --standard=80211ax  HE single-user (OFDMA/MU need an AP: not available in ad hoc).
 *                       Tier A: 2.4 GHz channel 1, 20 MHz, ConstantRate HeMcs<heMcs> (default 0),
 *                       800 ns GI, control and non-unicast ErpOfdmRate6Mbps, A-MPDU/A-MSDU off
 *                       on every AC. --axBand=5 selects 5 GHz channel 42 / 80 MHz with
 *                       OfdmRate6Mbps control (prepared, not used in Tier A).
 * New standards are added as one more entry in StandardConfig().
 *
 * Instrumentation differences for QoS standards (>= 802.11n): no DCF Txop exists
 * (wifi-mac-helper.cc), so the MAC-queue drop traces are hooked on the four EDCA queues
 * (VO/VI/BE/BK_Txop/Queue) with the same DropBeforeEnqueue + DropAfterDequeue semantics.
 * For every standard, WifiMac DroppedMpdu is also counted per MPDU and per reason
 * (failed enqueue / expired lifetime / retry limit / QoS old) into the *_ext files.
 *
 * Configured values only: no attribute is read back from a device. PHY defaults that the
 * program does not set (RxSensitivity, CcaEdThreshold, RxNoiseFigure) are recorded from the
 * TypeId attribute defaults and labelled as such.
 *
 * Output (into --outDir, which should be a fresh directory per run):
 *   probe_aggregate.csv, pernode/probe_<proto>_<n>_<traffic>_seed<s>.csv  -- probe format
 *   wifistd_ext.csv, pernode_ext/wifistd_<proto>_<n>_<traffic>_seed<s>.csv -- new columns
 */
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/wifi-module.h"
#include "ns3/applications-module.h"
#include "ns3/olsr-module.h"
#include "ns3/aodv-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/neighbor-cache-helper.h"
#include "ns3/arp-l3-protocol.h"
#include "ns3/arp-cache.h"

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

NS_LOG_COMPONENT_DEFINE("IotWifiStd");

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
    uint64_t droppedMpdu[4] = {0, 0, 0, 0}; // WifiMac DroppedMpdu, by WifiMacDropReason (per MPDU)
    uint64_t arpL3Drops = 0, arpCacheDrops = 0;
};
static std::vector<NodeStat> g_stat;
static uint64_t g_appRx = 0; // packets received by the gateway PacketSink (Rx trace)

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
static void OnArpL3Drop(uint32_t node, Ptr<const Packet> /*p*/)
{
    if (node < g_stat.size()) g_stat[node].arpL3Drops++;
}
static void OnArpCacheDrop(uint32_t node, Ptr<const Packet> /*p*/)
{
    if (node < g_stat.size()) g_stat[node].arpCacheDrops++;
}
static void OnDroppedMpdu(uint32_t node, WifiMacDropReason reason, Ptr<const WifiMpdu> /*mpdu*/)
{
    // WifiMacDropReason has exactly four values (wifi-mac.h): FAILED_ENQUEUE, EXPIRED_LIFETIME,
    // REACHED_RETRY_LIMIT, QOS_OLD_PACKET.
    if (node < g_stat.size() && static_cast<uint8_t>(reason) < 4)
        g_stat[node].droppedMpdu[static_cast<uint8_t>(reason)]++;
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
static void OnSinkRx(Ptr<const Packet> /*p*/, const Address& /*from*/)
{
    ++g_appRx;
}

// ------------------------------------------------------------------ AODV path sampler
// Copied from scratch/iot-network-v3-ext.cc (SampleRoutesOnce), unchanged in effect.
const Ipv4Address kNoRoute("255.255.255.255");
struct PathSampler : public SimpleRefCount<PathSampler>
{
    std::vector<Ipv4Address> lastHop;
    std::vector<bool> initialized;
    std::vector<uint32_t> changes;
};
static void SampleRoutesOnce(Ptr<PathSampler> sampler, NodeContainer sensors, Ipv4Address gatewayAddr,
                             double interval, double endTime)
{
    for (uint32_t i = 0; i < sensors.GetN(); ++i)
    {
        Ptr<Ipv4> ipv4 = sensors.Get(i)->GetObject<Ipv4>();
        Ptr<Ipv4RoutingProtocol> rp = ipv4->GetRoutingProtocol();
        Ipv4Header ipHdr;
        ipHdr.SetDestination(gatewayAddr);
        Socket::SocketErrno sockerr = Socket::ERROR_NOTERROR;
        Ptr<Packet> dummy = Create<Packet>(0);
        Ptr<Ipv4Route> route = rp->RouteOutput(dummy, ipHdr, nullptr, sockerr);
        Ipv4Address hop = kNoRoute;
        if (route)
        {
            hop = route->GetGateway();
            if (hop == Ipv4Address::GetZero())
            {
                hop = gatewayAddr;
            }
        }
        if (!sampler->initialized[i])
        {
            sampler->lastHop[i] = hop;
            sampler->initialized[i] = true;
        }
        else if (hop != sampler->lastHop[i])
        {
            sampler->changes[i]++;
            sampler->lastHop[i] = hop;
        }
    }
    if (Simulator::Now().GetSeconds() + interval < endTime)
    {
        Simulator::Schedule(Seconds(interval), &SampleRoutesOnce, sampler, sensors, gatewayAddr, interval, endTime);
    }
}

// ------------------------------------------------------------------ standard configurations
struct StdConfig
{
    std::string name;            // value of --standard
    WifiStandard standard;
    bool qos;                    // >= 802.11n: EDCA queues instead of the DCF Txop
    std::string channelSettings; // "" = leave the PHY default (802.11b, as in the probe)
    std::string dataMode, controlMode, nonUnicastMode;
};

static StdConfig StandardConfig(const std::string& name, uint32_t heMcs, uint32_t axBand)
{
    if (name == "80211b")
        return {name, WIFI_STANDARD_80211b, false, "", "DsssRate1Mbps", "DsssRate1Mbps", "DsssRate1Mbps"};
    if (name == "80211ax")
    {
        const std::string mcs = "HeMcs" + std::to_string(heMcs);
        if (axBand == 5)
            return {name, WIFI_STANDARD_80211ax, true, "{42, 80, BAND_5GHZ, 0}", mcs, "OfdmRate6Mbps", "OfdmRate6Mbps"};
        return {name, WIFI_STANDARD_80211ax, true, "{1, 20, BAND_2_4GHZ, 0}", mcs, "ErpOfdmRate6Mbps", "ErpOfdmRate6Mbps"};
    }
    NS_FATAL_ERROR("--standard must be 80211b or 80211ax (got '" << name << "')");
    return {};
}

// Attribute default from the TypeId (what a newly created object starts from); never read
// back from an installed device.
static std::string TypeIdDefault(const std::string& tid, const std::string& attr)
{
    TypeId::AttributeInformation info;
    NS_ABORT_MSG_IF(!TypeId::LookupByName(tid).LookupAttributeByName(attr, &info),
                    "attribute " << tid << "::" << attr << " not found");
    return info.initialValue->SerializeToString(info.checker);
}

static void MakeDirs(const std::string& path)
{
    std::string cur;
    std::istringstream ss(path);
    std::string part;
    if (!path.empty() && path[0] == '/') cur = "/";
    while (std::getline(ss, part, '/'))
    {
        if (part.empty()) continue;
        cur += part + "/";
        mkdir(cur.c_str(), 0755);
    }
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
    std::string outDir = "results/wifi-std/default";
    double offeredRateKbps = 0.0;   // 0.0 = unset -> use trafficLevel default (preserves prior behavior)
    std::string standardName = "80211b";
    uint32_t heMcs = 0;
    uint32_t axBand = 24;           // 24 = 2.4 GHz / 20 MHz (Tier A); 5 = 5 GHz / 80 MHz
    bool aggregation = false;       // A-MPDU/A-MSDU for QoS standards (Tier A: off)

    CommandLine cmd(__FILE__);
    cmd.AddValue("protocol", "aodv | olsr | static", protocol);
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
    cmd.AddValue("outDir", "output directory (use a fresh one per run)", outDir);
    cmd.AddValue("standard", "80211b | 80211ax", standardName);
    cmd.AddValue("heMcs", "80211ax: constant HE MCS for data (0..11)", heMcs);
    cmd.AddValue("axBand", "80211ax: 24 = 2.4 GHz ch 1 / 20 MHz (Tier A); 5 = 5 GHz ch 42 / 80 MHz", axBand);
    bool arpPrepopulate = false;
    cmd.AddValue("arpPrepopulate", "fill every ARP cache before start (NeighborCacheHelper); default false", arpPrepopulate);
    cmd.AddValue("aggregation", "80211ax: enable A-MPDU/A-MSDU (Tier A: false)", aggregation);
    cmd.Parse(argc, argv);

    if (protocol != "aodv" && protocol != "olsr" && protocol != "static")
        NS_FATAL_ERROR("--protocol must be aodv|olsr|static (got '" << protocol << "')");
    if (trafficLevel != "medium" && trafficLevel != "high")
        NS_FATAL_ERROR("probe supports only --trafficLevel=medium|high (got '" << trafficLevel << "')");
    NS_ABORT_MSG_IF(axBand != 24 && axBand != 5, "--axBand must be 24 or 5");
    NS_ABORT_MSG_IF(heMcs > 11, "--heMcs must be 0..11");
    const StdConfig sc = StandardConfig(standardName, heMcs, axBand);
    NS_ABORT_MSG_IF(!sc.qos && (aggregation || heMcs != 0 || axBand != 24),
                    "--heMcs/--axBand/--aggregation apply to 80211ax only");

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
    sensorMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel"); // static mobility only
    sensorMobility.Install(sensors);

    MobilityHelper gwMob;
    Ptr<ListPositionAllocator> gwAlloc = CreateObject<ListPositionAllocator>();
    gwAlloc->Add(Vector(areaSize / 2.0, areaSize / 2.0, 0.0));
    gwMob.SetPositionAllocator(gwAlloc);
    gwMob.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    gwMob.Install(gateway);

    // wifi PHY/MAC -- 80211b is the probe's configuration statement for statement
    Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode", StringValue(sc.nonUnicastMode));
    if (sc.standard == WIFI_STANDARD_80211ax)
        Config::SetDefault("ns3::HeConfiguration::GuardInterval", TimeValue(NanoSeconds(800)));
    WifiHelper wifi;
    wifi.SetStandard(sc.standard);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode", StringValue(sc.dataMode),
                                 "ControlMode", StringValue(sc.controlMode));
    YansWifiChannelHelper wifiChannel;
    wifiChannel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    wifiChannel.AddPropagationLoss("ns3::LogDistancePropagationLossModel",
                                   "Exponent", DoubleValue(3.0),
                                   "ReferenceDistance", DoubleValue(1.0),
                                   "ReferenceLoss", DoubleValue(40.0));
    YansWifiPhyHelper wifiPhy;
    wifiPhy.SetChannel(wifiChannel.Create());
    if (!sc.channelSettings.empty())
        wifiPhy.Set("ChannelSettings", StringValue(sc.channelSettings));
    wifiPhy.Set("TxPowerStart", DoubleValue(txPowerDbm));
    wifiPhy.Set("TxPowerEnd", DoubleValue(txPowerDbm));
    WifiMacHelper wifiMac;
    const uint32_t ampdu = aggregation ? 65535 : 0;
    const uint32_t amsdu = aggregation ? 7935 : 0;
    if (!sc.qos)
        wifiMac.SetType("ns3::AdhocWifiMac");
    else
        wifiMac.SetType("ns3::AdhocWifiMac",
                        "BE_MaxAmpduSize", UintegerValue(ampdu), "BK_MaxAmpduSize", UintegerValue(ampdu),
                        "VI_MaxAmpduSize", UintegerValue(ampdu), "VO_MaxAmpduSize", UintegerValue(ampdu),
                        "BE_MaxAmsduSize", UintegerValue(amsdu), "BK_MaxAmsduSize", UintegerValue(amsdu),
                        "VI_MaxAmsduSize", UintegerValue(amsdu), "VO_MaxAmsduSize", UintegerValue(amsdu));
    NetDeviceContainer devices = wifi.Install(wifiPhy, wifiMac, allNodes);

    g_stat.assign(n, NodeStat());

    // routing
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
    internet.Install(allNodes);
    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);
    if (arpPrepopulate)
    {
        NeighborCacheHelper neighborCache;
        neighborCache.PopulateNeighborCache();
    }
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
    // Config::ConnectWithoutContext aborts if a path matches nothing (config.cc), so a missing
    // queue can never silently leave a counter at zero.
    for (uint32_t i = 0; i < n; ++i)
    {
        std::string base = "/NodeList/" + std::to_string(i) + "/DeviceList/0/$ns3::WifiNetDevice/";
        Config::ConnectWithoutContext(base + "Phy/State/State",
                                      MakeBoundCallback(&OnPhyState, i));
        Config::ConnectWithoutContext(base + "Phy/PhyTxBegin",
                                      MakeBoundCallback(&OnPhyTxBegin, i));
        Config::ConnectWithoutContext(base + "Phy/PhyRxDrop",
                                      MakeBoundCallback(&OnPhyRxDrop, i));
        if (!sc.qos)
        {
            // adhoc MAC single Txop queue
            Config::ConnectWithoutContext(base + "Mac/$ns3::AdhocWifiMac/Txop/Queue/DropBeforeEnqueue",
                                          MakeBoundCallback(&OnMacQueueDrop, i));
            Config::ConnectWithoutContext(base + "Mac/$ns3::AdhocWifiMac/Txop/Queue/DropAfterDequeue",
                                          MakeBoundCallback(&OnMacQueueDrop, i));
        }
        else
        {
            // QoS: no DCF Txop; the same two traces on each EDCA queue
            for (const char* ac : {"VO_Txop", "VI_Txop", "BE_Txop", "BK_Txop"})
            {
                Config::ConnectWithoutContext(base + "Mac/$ns3::AdhocWifiMac/" + ac + "/Queue/DropBeforeEnqueue",
                                              MakeBoundCallback(&OnMacQueueDrop, i));
                Config::ConnectWithoutContext(base + "Mac/$ns3::AdhocWifiMac/" + ac + "/Queue/DropAfterDequeue",
                                              MakeBoundCallback(&OnMacQueueDrop, i));
            }
        }
        Config::ConnectWithoutContext(base + "RemoteStationManager/MacTxFinalDataFailed",
                                      MakeBoundCallback(&OnMacTxFinalDataFailed, i));
        Config::ConnectWithoutContext(base + "Mac/DroppedMpdu",
                                      MakeBoundCallback(&OnDroppedMpdu, i));
        Config::ConnectWithoutContext("/NodeList/" + std::to_string(i) + "/$ns3::Ipv4L3Protocol/Drop",
                                      MakeBoundCallback(&OnIpDrop, i));
        Config::ConnectWithoutContext("/NodeList/" + std::to_string(i) + "/$ns3::Ipv4L3Protocol/UnicastForward",
                                      MakeBoundCallback(&OnUnicastForward, i));
        {
            Ptr<Node> nd = allNodes.Get(i);
            Ptr<ArpL3Protocol> arp = nd->GetObject<ArpL3Protocol>();
            NS_ABORT_MSG_IF(!arp || !arp->TraceConnectWithoutContext("Drop", MakeBoundCallback(&OnArpL3Drop, i)),
                            "ArpL3Protocol Drop trace not connected on node " << i);
            Ptr<Ipv4L3Protocol> ip = nd->GetObject<Ipv4L3Protocol>();
            Ptr<ArpCache> cache = ip->GetInterface(1)->GetArpCache();
            NS_ABORT_MSG_IF(!cache || !cache->TraceConnectWithoutContext("Drop", MakeBoundCallback(&OnArpCacheDrop, i)),
                            "ArpCache Drop trace not connected on node " << i);
        }
    }

    // applications
    uint16_t port = 9;
    PacketSinkHelper sinkHelper("ns3::UdpSocketFactory",
                                InetSocketAddress(Ipv4Address::GetAny(), port));
    ApplicationContainer sinkApp = sinkHelper.Install(gateway.Get(0));
    sinkApp.Start(Seconds(0.0));
    sinkApp.Stop(Seconds(simTime));
    sinkApp.Get(0)->TraceConnectWithoutContext("Rx", MakeCallback(&OnSinkRx));
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

    // AODV only: the v3-ext path sampler (first sample at appStart + 5 s, then every 5 s)
    const double pathSampleInterval = 5.0;
    Ptr<PathSampler> pathSampler = Create<PathSampler>();
    pathSampler->lastHop.assign(nSensors, kNoRoute);
    pathSampler->initialized.assign(nSensors, false);
    pathSampler->changes.assign(nSensors, 0);
    if (protocol == "aodv" && appStart + pathSampleInterval < simTime)
        Simulator::Schedule(Seconds(appStart + pathSampleInterval), &SampleRoutesOnce, pathSampler, sensors,
                            gatewayAddr, pathSampleInterval, simTime);

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
    uint64_t timesForwarded = 0;
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
        timesForwarded += f.second.timesForwarded;
    }
    double pdr = txPkts ? 100.0 * rxPkts / txPkts : 0.0;
    double measWindow = simTime - appStart;
    double thrKbps = measWindow > 0 ? (rxBytes * 8.0) / (measWindow * 1000.0) : 0.0;
    double avgDelay = rxPkts ? delaySum / rxPkts : 0.0;
    double avgJitter = (rxPkts > 1) ? jitterSum / (rxPkts - 1) : 0.0;

    Simulator::Destroy();

    // ---- write per-node CSV (probe format) ----
    MakeDirs(outDir);
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

    // ---- append aggregate row (probe format) ----
    uint64_t totPhyRxDrop = 0, totMacQDrop = 0, totMaxRetryDrop = 0, totNoRoute = 0, totTtl = 0,
             totRouteErr = 0, totQueue = 0, totOther = 0;
    uint64_t totDropped[4] = {0, 0, 0, 0};
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
        for (int r = 0; r < 4; ++r) totDropped[r] += g_stat[i].droppedMpdu[r];
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

    // ---- new outputs (never mixed into the probe-format files) ----
    std::string pedir = outDir + "/pernode_ext";
    mkdir(pedir.c_str(), 0755);
    std::ostringstream pe;
    pe << pedir << "/wifistd_" << protocol << "_" << nSensors << "_" << trafficLevel << "_seed" << seed << ".csv";
    std::ofstream ef(pe.str());
    ef << "node_id,hop_to_gw,dropped_mpdu_failed_enqueue,dropped_mpdu_expired_lifetime,"
          "dropped_mpdu_retry_limit,dropped_mpdu_qos_old,arp_l3_drops,arp_cache_drops\n";
    for (uint32_t i = 0; i < n; ++i)
    {
        const NodeStat& s = g_stat[i];
        ef << i << "," << hop[i] << "," << s.droppedMpdu[0] << "," << s.droppedMpdu[1] << ","
           << s.droppedMpdu[2] << "," << s.droppedMpdu[3] << "," << s.arpL3Drops << "," << s.arpCacheDrops << "\n";
    }
    ef.close();

    uint64_t appTx = 0;
    uint64_t totArpL3 = 0, totArpCache = 0;
    for (uint32_t i = 0; i < n; ++i) { totArpL3 += g_stat[i].arpL3Drops; totArpCache += g_stat[i].arpCacheDrops; }
    for (uint32_t i = 0; i < nSensors; ++i) appTx += g_stat[i].appOriginated;
    // V3 hop count: exact BFS depth mean for Static (reachable sensors), 1 + timesForwarded/rx otherwise
    double hopV3 = 0.0;
    std::string hopMethod;
    if (protocol == "static")
    {
        hopMethod = "exact";
        uint32_t counted = 0;
        for (uint32_t i = 0; i < nSensors; ++i)
            if (hop[i] >= 0) { hopV3 += static_cast<double>(hop[i]); ++counted; }
        hopV3 = counted ? hopV3 / counted : 0.0;
    }
    else
    {
        hopMethod = "approx_timesForwarded";
        hopV3 = rxPkts ? 1.0 + static_cast<double>(timesForwarded) / rxPkts : 0.0;
    }
    uint64_t pathChanges = 0;
    for (uint32_t c : pathSampler->changes) pathChanges += c;

    std::string extPath = outDir + "/wifistd_ext.csv";
    bool extHeader = true;
    {
        std::ifstream ex(extPath);
        extHeader = !ex.good();
    }
    std::ofstream xf(extPath, std::ios::out | std::ios::app);
    if (extHeader)
        xf << "standard,protocol,nodes,trafficLevel,offered_rate_kbps,seed,data_mode,control_mode,"
              "non_unicast_mode,channel_settings,he_guard_interval_ns,max_ampdu_bytes,max_amsdu_bytes,"
              "tx_power_dbm,propagation,phy_model,rx_sensitivity_dbm,cca_ed_threshold_dbm,"
              "rx_noise_figure_db,values_source,total_dropped_mpdu_failed_enqueue,"
              "total_dropped_mpdu_expired_lifetime,total_dropped_mpdu_retry_limit,total_dropped_mpdu_qos_old,"
              "app_tx_pkts,app_rx_pkts,app_pdr,fm_tx_pkts,fm_rx_pkts,fm_pdr,jitter_v3_sec,"
              "avg_hop_count_v3,hop_count_method,path_changes,arp_prepopulate,total_arp_l3_drops,"
              "total_arp_cache_drops\n";
    xf << sc.name << "," << protocol << "," << nSensors << "," << trafficLevel << "," << actualRateKbps << ","
       << seed << "," << sc.dataMode << "," << sc.controlMode << "," << sc.nonUnicastMode << ",\""
       << (sc.channelSettings.empty() ? "ns-3 default for 802.11b" : sc.channelSettings) << "\","
       << (sc.qos ? "800" : "NA") << "," << (sc.qos ? std::to_string(ampdu) : "NA") << ","
       << (sc.qos ? std::to_string(amsdu) : "NA") << "," << txPowerDbm << ","
       << "\"LogDistance exp=3.0 ref=1m loss=40dB\",YansWifiPhy,"
       << TypeIdDefault("ns3::WifiPhy", "RxSensitivity") << ","
       << TypeIdDefault("ns3::WifiPhy", "CcaEdThreshold") << ","
       << TypeIdDefault("ns3::WifiPhy", "RxNoiseFigure") << ","
       << "\"configured values; rx_sensitivity/cca_ed/noise_figure are ns-3 attribute defaults (not set, not read back)\","
       << totDropped[0] << "," << totDropped[1] << "," << totDropped[2] << "," << totDropped[3] << ","
       << appTx << "," << g_appRx << "," << (appTx ? 100.0 * g_appRx / appTx : 0.0) << ","
       << txPkts << "," << rxPkts << "," << pdr << "," << (rxPkts ? jitterSum / rxPkts : 0.0) << ","
       << hopV3 << "," << hopMethod << "," << pathChanges << "," << (arpPrepopulate ? 1 : 0) << ","
       << totArpL3 << "," << totArpCache << "\n";
    xf.close();

    std::cout << "wifi-std done: standard=" << sc.name << " " << protocol << " n=" << nSensors
              << " traffic=" << trafficLevel << " rate=" << actualRateKbps << "kbps"
              << " seed=" << seed << "  PDR=" << pdr << "%  thr=" << thrKbps << "kbps"
              << "  unreachable=" << unreachable << "  phyRxDrop=" << totPhyRxDrop
              << "  macQdrop=" << totMacQDrop << "  maxRetryDrop=" << totMaxRetryDrop
              << "  droppedMpdu(enq/exp/retry/old)=" << totDropped[0] << "/" << totDropped[1] << "/"
              << totDropped[2] << "/" << totDropped[3]
              << "  gwBusy=" << gwBusy << "  ring1Busy=" << (ring1Cnt ? ring1BusySum / ring1Cnt : 0.0)
              << "\n";
    return 0;
}
