/*
 * IoT Network Performance Analysis - V3 (expanded experiment matrix)
 *
 * Advisor direction (2026-08): V3 must NOT introduce a new topology yet.
 * "Topology ใช้รูปแบบเดิมไปก่อน" -- keep using V2's own topology-generation
 * method (uniform-random sensor placement + single gateway, see
 * scratch/iot-network.cc), and first widen the experiment matrix and the
 * metric set. Adaptive/Sigmoid routing is a later phase.
 *
 * This file is therefore a superset of iot-network.cc's topology/PHY/MAC
 * model -- line-for-line the same node layout, radio, and static-routing
 * BFS -- with these V3 additions layered on top:
 *
 *   - Node counts up to 100 (unchanged topology method, just more sensors).
 *   - --trafficLevel=low|medium|high (maps to a per-sensor data rate; medium
 *     equals V2's existing 8kbps baseline so the two studies share a
 *     reference point).
 *   - --mobilityMode=static|low|medium (static = identical to V2's
 *     ConstantPositionMobilityModel; low/medium = RandomWaypoint at a
 *     configurable constant speed). The gateway never moves in any mode.
 *   - New metrics: jitter, routing overhead (best-effort; see the honest
 *     limitation noted below), hop count (exact for static, approximate for
 *     AODV/OLSR), path changes (periodic route-table sampling), and
 *     per-neighbor-pair link utilization / MLU.
 *   - --protocol=sigmoid is intentionally NOT implemented here and refuses
 *     to run rather than fabricate results. A separate, already-documented
 *     prototype exists at scratch/iot-network-v3.cc (fixed 15-node clustered
 *     topology, geometry-proxy sigmoid cost) -- kept as a reference/Phase-3
 *     track, not reused here, because it does not satisfy "keep V2's
 *     topology" for this phase.
 *   - --protocol=v4 -- advisor-approved "Sigmoid-Based Adaptive Routing"
 *     (V4), inspired by the advisor's SE-OSPF paper but NOT a reproduction
 *     of it (see docs/v3-experiment-framework.md and the dashboard's V4
 *     section for the full paper-vs-V4 comparison). V4 is implemented as a
 *     4th static-route mode -- same architecture as --protocol=static
 *     (Ipv4StaticRouting host routes, installed once, offline, before
 *     traffic starts) -- with edges weighted by a two-input sigmoid cost
 *     instead of unweighted hop count, and the shortest-COST path found
 *     with Dijkstra instead of BFS. See RunV4() below for the honest
 *     two-pass design this required and why: LoadScore_ij (measured link
 *     utilization) cannot exist before some traffic has actually run, so
 *     V4 first runs one real "baseline" measurement pass (hop-count
 *     routing) to obtain genuine, non-fabricated per-edge byte counts,
 *     computes AdaptiveCost_ij from that real measurement plus topological
 *     structural risk, then runs a second, final pass with V4's own
 *     Dijkstra-computed routes installed -- offline, fixed before that
 *     pass's traffic starts, exactly like Static. No periodic/runtime
 *     route recomputation is implemented.
 *
 * A single --seed drives both the position RNG (independent of ns-3's own
 * RNG, exactly as V2 does) and ns3::RngSeedManager, so mobility waypoints
 * are reproducible per seed. Mobility is installed before the routing stack
 * in every run, so stream-assignment order up to that point is identical
 * regardless of --protocol -- the same --seed therefore yields the same
 * initial layout AND the same mobility trace across all four routing modes,
 * which is what makes a same-seed cross-protocol comparison fair.
 *
 * Output: one CSV row per run, appended/created at
 *   <outDir>/<protocol>_<nSensors>_<trafficLevel>_<mobilityMode>.csv
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
#include <map>
#include <utility>
#include <ctime>
#include <cmath>
#include <algorithm>
#include <limits>
#include <functional>
#include <sys/stat.h>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("IotNetworkV3Ext");

namespace
{

// ------------------------------------------------------------------
// MLU instrumentation: bytes transmitted per (srcNodeIdx, dstNodeIdx)
// unicast MAC pair, observed at the WifiPhy "PhyTxBegin" trace source.
// (WifiMac's own "MacTx" fires too early -- before the WifiMacHeader with
// the destination address is added -- so PhyTxBegin, which carries the
// fully-framed MPDU, is used instead.) Broadcast frames (ARP, AODV RREQ,
// OLSR HELLO/TC) are excluded -- they are not addressed to a single
// neighbour, so they do not represent a "link" in the sense this metric
// means.
// ------------------------------------------------------------------
std::map<Mac48Address, uint32_t> g_macToNode;
std::map<std::pair<uint32_t, uint32_t>, uint64_t> g_linkBytes;

void
OnPhyTxBegin(uint32_t srcIdx, Ptr<const Packet> packet, double /* txPowerW */)
{
    WifiMacHeader hdr;
    if (packet->PeekHeader(hdr) == 0 || !hdr.IsData())
    {
        return;
    }
    Mac48Address dst = hdr.GetAddr1();
    if (dst.IsBroadcast())
    {
        return;
    }
    auto it = g_macToNode.find(dst);
    if (it == g_macToNode.end())
    {
        return;
    }
    g_linkBytes[{srcIdx, it->second}] += packet->GetSize();
}

// ------------------------------------------------------------------
// Path-change instrumentation: every `interval` seconds, ask each
// sensor's routing protocol what next hop it currently holds for the
// gateway address (a passive RouteOutput lookup against whatever route
// is already cached -- by the time sampling starts, real application
// traffic has already been driving this exact lookup continuously, so
// this adds no new class of side effect for AODV/OLSR beyond what the
// data traffic itself already causes). A change in the returned next
// hop between consecutive samples counts as one path change. Static
// routing is expected, and verified, to report zero changes -- the
// route is installed once, offline, and never revisited.
// ------------------------------------------------------------------
const Ipv4Address kNoRoute("255.255.255.255"); // sentinel: no valid route at sample time

struct PathSampler : public SimpleRefCount<PathSampler>
{
    std::vector<Ipv4Address> lastHop;
    std::vector<bool> initialized;
    std::vector<uint32_t> changes;
};

void
SampleRoutesOnce(Ptr<PathSampler> sampler,
                  NodeContainer sensors,
                  Ipv4Address gatewayAddr,
                  double interval,
                  double endTime)
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
                hop = gatewayAddr; // direct (single-hop) route: destination is the next hop
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
        Simulator::Schedule(Seconds(interval),
                             &SampleRoutesOnce,
                             sampler,
                             sensors,
                             gatewayAddr,
                             interval,
                             endTime);
    }
}

// ====================================================================
// V4 -- Sigmoid-Based Adaptive Routing (advisor-approved, PROPOSED design
// implemented here for the first time). See the top-of-file comment and
// docs/v3-experiment-framework.md for the full paper-vs-V4 rationale.
//
// Mathematical model implemented, EXACTLY as approved:
//   RiskScore_ij = max(deg(i), deg(j)) / maxDegree
//   LoadScore_ij = measured link utilization, in [0,1]
//   SigmoidRisk_ij = 1 / (1 + exp(-k_R * (RiskScore_ij - x0_R)))
//   SigmoidLoad_ij = 1 / (1 + exp(-k_L * (LoadScore_ij - x0_L)))
//   AdaptiveCost_ij = w_R * SigmoidRisk_ij + w_L * SigmoidLoad_ij
// Lower AdaptiveCost_ij is preferred (Dijkstra minimizes total path cost).
//
// THE HONEST DEPENDENCY PROBLEM AND HOW IT IS RESOLVED (do not remove this
// comment -- it is the reason this function is shaped the way it is):
// LoadScore_ij requires REAL measured link utilization. Real utilization
// does not exist until traffic has actually been transmitted. But V4's
// approved architecture is "offline-computed weighted-route" -- routes
// must be installed BEFORE traffic starts, same as --protocol=static, with
// no periodic runtime recomputation. Those two requirements are only
// jointly satisfiable with two passes:
//   Pass 1 ("baseline measurement"): a complete, real ns-3 run using
//     ordinary hop-count (BFS) routing -- structurally identical to
//     --protocol=static -- whose only purpose is to obtain genuine,
//     non-fabricated per-edge byte counts (the same PhyTxBegin
//     instrumentation --protocol=static/aodv/olsr already produce
//     AverageLinkUtilization/MaximumLinkUtilization from). This pass's own
//     performance numbers (PDR, delay, etc.) are discarded -- only its
//     measured link bytes are kept.
//   Pass 2 ("V4, reported"): AdaptiveCost_ij is computed from Pass 1's real
//     measurement plus topological structural risk, Dijkstra finds the
//     min-cost tree, those routes are installed offline (before Pass 2's
//     own traffic starts, exactly like Static), and Pass 2's own
//     measurements are what gets written to the output CSV row.
// KNOWN LIMITATION, stated plainly rather than glossed over: Pass 1's
// traffic pattern (which edges carry how many bytes) is itself a product
// of the BASELINE hop-count routing, not of V4's own eventual routes -- so
// LoadScore_ij measures "load under baseline routing," not "load V4 itself
// would produce." This is a real, inherent chicken-and-egg limitation of
// any offline (non-iteratively-converged) load-aware routing scheme, not a
// bug in this implementation. It is not resolved here -- flagged for the
// advisor, same as every other honestly-documented limitation in this
// project.
//
// No value here is ever fabricated: if Pass 1 measures zero bytes on some
// edge (a real, valid outcome -- that edge legitimately carried no
// baseline traffic), LoadScore_ij for that edge is genuinely 0.0, not
// invented.
// ====================================================================

struct V4PassStats
{
    uint64_t totalTx = 0;
    uint64_t totalRx = 0;
    uint64_t totalRxBytes = 0;
    double totalDelaySum = 0.0;
    double totalJitterSum = 0.0;
    uint64_t totalTimesForwarded = 0;
    uint64_t routingOverheadPackets = 0;
    uint64_t totalPathChanges = 0;
    std::map<std::pair<uint32_t, uint32_t>, uint64_t> linkBytes; // this pass's own measurement
};

std::vector<std::vector<uint32_t>>
ComputeAdjacency(const std::vector<Vector>& pos, double txRange)
{
    uint32_t n = pos.size();
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
    return adjacency;
}

std::vector<int64_t>
BfsParent(const std::vector<std::vector<uint32_t>>& adjacency, uint32_t root)
{
    uint32_t n = adjacency.size();
    std::vector<bool> visited(n, false);
    std::vector<int64_t> parent(n, -1);
    std::queue<uint32_t> q;
    visited[root] = true;
    q.push(root);
    while (!q.empty())
    {
        uint32_t u = q.front();
        q.pop();
        for (uint32_t v : adjacency[u])
        {
            if (!visited[v])
            {
                visited[v] = true;
                parent[v] = u;
                q.push(v);
            }
        }
    }
    return parent;
}

// Dijkstra shortest-cost tree rooted at `root`, edge costs from `cost`
// (looked up both directions -- the graph is undirected). Missing edges
// (should not happen for adjacency-derived pairs) default to +infinity.
std::vector<int64_t>
DijkstraParent(const std::vector<std::vector<uint32_t>>& adjacency,
               const std::map<std::pair<uint32_t, uint32_t>, double>& cost,
               uint32_t root)
{
    uint32_t n = adjacency.size();
    const double kInf = std::numeric_limits<double>::infinity();
    std::vector<double> dist(n, kInf);
    std::vector<int64_t> parent(n, -1);
    std::vector<bool> done(n, false);
    dist[root] = 0.0;

    using QueueItem = std::pair<double, uint32_t>; // (dist, node)
    std::priority_queue<QueueItem, std::vector<QueueItem>, std::greater<QueueItem>> pq;
    pq.push({0.0, root});
    while (!pq.empty())
    {
        auto [d, u] = pq.top();
        pq.pop();
        if (done[u])
        {
            continue;
        }
        done[u] = true;
        for (uint32_t v : adjacency[u])
        {
            auto key = (u < v) ? std::make_pair(u, v) : std::make_pair(v, u);
            auto it = cost.find(key);
            double w = (it != cost.end()) ? it->second : kInf;
            if (dist[u] + w < dist[v])
            {
                dist[v] = dist[u] + w;
                parent[v] = static_cast<int64_t>(u);
                pq.push({dist[v], v});
            }
        }
    }
    return parent;
}

// Builds one complete, real ns-3 topology (nodes/mobility/PHY/MAC/Internet
// stack/apps/FlowMonitor) -- identical positions and mobility trace for a
// given seed regardless of which pass this is -- installs static host
// routes to the gateway following the caller-supplied `parent` tree
// (architecturally identical to --protocol=static, just fed an externally
// computed tree instead of computing its own BFS), runs for `simTime`, and
// returns the real measured stats. Used for both V4 passes.
V4PassStats
RunV4Pass(uint32_t nSensors,
          double simTime,
          double appStart,
          double areaSize,
          double txPowerDbm,
          uint32_t packetSize,
          uint32_t seed,
          const std::string& trafficLevel,
          const std::string& mobilityMode,
          double mobilitySpeedLow,
          double mobilitySpeedMedium,
          double pathSampleInterval,
          const std::vector<int64_t>& parent,
          uint32_t gatewayIndex,
          uint32_t& unreachableOut)
{
    std::string dataRate = (trafficLevel == "low")    ? "4kbps"
                            : (trafficLevel == "high") ? "16kbps"
                                                        : "8kbps";
    double mobilitySpeed = (mobilityMode == "low")      ? mobilitySpeedLow
                           : (mobilityMode == "medium") ? mobilitySpeedMedium
                                                          : 0.0;

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(1);

    NodeContainer sensors;
    sensors.Create(nSensors);
    NodeContainer gateway;
    gateway.Create(1);
    NodeContainer allNodes;
    allNodes.Add(sensors);
    allNodes.Add(gateway);

    std::mt19937 posRng(seed);
    std::uniform_real_distribution<double> coord(0.0, areaSize);
    Ptr<ListPositionAllocator> gatewayAlloc = CreateObject<ListPositionAllocator>();
    gatewayAlloc->Add(Vector(areaSize / 2.0, areaSize / 2.0, 0.0));
    MobilityHelper gatewayMobility;
    gatewayMobility.SetPositionAllocator(gatewayAlloc);
    gatewayMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    gatewayMobility.Install(gateway);

    Ptr<ListPositionAllocator> sensorAlloc = CreateObject<ListPositionAllocator>();
    std::mt19937 posRng2(seed);
    for (uint32_t i = 0; i < nSensors; ++i)
    {
        sensorAlloc->Add(Vector(coord(posRng2), coord(posRng2), 0.0));
    }
    MobilityHelper sensorMobility;
    sensorMobility.SetPositionAllocator(sensorAlloc);
    if (mobilityMode == "static")
    {
        sensorMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    }
    else
    {
        Ptr<RandomBoxPositionAllocator> waypointAlloc = CreateObject<RandomBoxPositionAllocator>();
        Ptr<UniformRandomVariable> xVar = CreateObject<UniformRandomVariable>();
        xVar->SetAttribute("Min", DoubleValue(0.0));
        xVar->SetAttribute("Max", DoubleValue(areaSize));
        Ptr<UniformRandomVariable> yVar = CreateObject<UniformRandomVariable>();
        yVar->SetAttribute("Min", DoubleValue(0.0));
        yVar->SetAttribute("Max", DoubleValue(areaSize));
        waypointAlloc->SetX(xVar);
        waypointAlloc->SetY(yVar);
        waypointAlloc->SetZ(CreateObject<ConstantRandomVariable>());
        std::ostringstream speedStr;
        speedStr << "ns3::ConstantRandomVariable[Constant=" << mobilitySpeed << "]";
        sensorMobility.SetMobilityModel("ns3::RandomWaypointMobilityModel",
                                         "Speed", StringValue(speedStr.str()),
                                         "Pause", StringValue("ns3::ConstantRandomVariable[Constant=2.0]"),
                                         "PositionAllocator", PointerValue(waypointAlloc));
    }
    sensorMobility.Install(sensors);

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

    const double kNominalPhyBps = 1.0e6;
    g_macToNode.clear();
    g_linkBytes.clear();
    for (uint32_t i = 0; i < devices.GetN(); ++i)
    {
        Mac48Address addr = Mac48Address::ConvertFrom(devices.Get(i)->GetAddress());
        g_macToNode[addr] = i;
        Ptr<WifiNetDevice> wifiDev = DynamicCast<WifiNetDevice>(devices.Get(i));
        wifiDev->GetPhy()->TraceConnectWithoutContext("PhyTxBegin", MakeBoundCallback(&OnPhyTxBegin, i));
    }

    InternetStackHelper internet;
    internet.Install(allNodes);
    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);
    Ipv4Address gatewayAddr = interfaces.GetAddress(gatewayIndex);

    unreachableOut = 0;
    Ipv4StaticRoutingHelper staticRoutingHelper;
    for (uint32_t i = 0; i < nSensors; ++i)
    {
        if (parent[i] == -1)
        {
            ++unreachableOut;
            continue;
        }
        Ptr<Ipv4> ipv4 = sensors.Get(i)->GetObject<Ipv4>();
        Ptr<Ipv4StaticRouting> staticRouting = staticRoutingHelper.GetStaticRouting(ipv4);
        Ipv4Address nextHopAddr = interfaces.GetAddress(static_cast<uint32_t>(parent[i]));
        uint32_t ifIndex = ipv4->GetInterfaceForDevice(devices.Get(i));
        staticRouting->AddHostRouteTo(gatewayAddr, nextHopAddr, ifIndex);
    }

    uint16_t port = 9;
    PacketSinkHelper sinkHelper("ns3::UdpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), port));
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
    }

    Ptr<PathSampler> pathSampler = Create<PathSampler>();
    pathSampler->lastHop.assign(nSensors, kNoRoute);
    pathSampler->initialized.assign(nSensors, false);
    pathSampler->changes.assign(nSensors, 0);
    double firstSample = appStart + pathSampleInterval;
    if (firstSample < simTime)
    {
        Simulator::Schedule(Seconds(firstSample), &SampleRoutesOnce, pathSampler, sensors,
                             gatewayAddr, pathSampleInterval, simTime);
    }

    FlowMonitorHelper flowmonHelper;
    Ptr<FlowMonitor> monitor = flowmonHelper.InstallAll();

    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    monitor->CheckForLostPackets();
    Ptr<Ipv4FlowClassifier> classifier = DynamicCast<Ipv4FlowClassifier>(flowmonHelper.GetClassifier());

    V4PassStats stats;
    for (const auto& flow : monitor->GetFlowStats())
    {
        Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(flow.first);
        if (t.destinationPort == 654 || t.sourcePort == 654 || t.destinationPort == 698 ||
            t.sourcePort == 698)
        {
            stats.routingOverheadPackets += flow.second.txPackets;
            continue;
        }
        if (t.destinationAddress != gatewayAddr)
        {
            continue;
        }
        stats.totalTx += flow.second.txPackets;
        stats.totalRx += flow.second.rxPackets;
        stats.totalRxBytes += flow.second.rxBytes;
        stats.totalDelaySum += flow.second.delaySum.GetSeconds();
        stats.totalJitterSum += flow.second.jitterSum.GetSeconds();
        stats.totalTimesForwarded += flow.second.timesForwarded;
    }
    for (uint32_t c : pathSampler->changes)
    {
        stats.totalPathChanges += c;
    }
    stats.linkBytes = g_linkBytes; // this pass's real measurement, copied out before teardown
    (void)kNominalPhyBps;          // used by the caller when deriving LoadScore_ij

    Simulator::Destroy();
    return stats;
}

// Top-level V4 orchestrator: computes structural risk (topology-only, no
// traffic dependency), runs Pass 1 to obtain real measured load, computes
// AdaptiveCost_ij, runs Pass 2 with the resulting Dijkstra routes, and
// writes the reported (Pass 2) row to results/v3-ext/v4_*.csv.
void
RunV4(uint32_t nSensors,
      double simTime,
      double appStart,
      double areaSize,
      double txPowerDbm,
      uint32_t packetSize,
      uint32_t seed,
      double txRange,
      const std::string& outDir,
      const std::string& trafficLevel,
      const std::string& mobilityMode,
      double mobilitySpeedLow,
      double mobilitySpeedMedium,
      double pathSampleInterval,
      double kRisk,
      double x0Risk,
      double kLoad,
      double x0Load,
      double wRisk,
      double wLoad)
{
    // Full parameter-bound validation, before anything else (including Pass
    // 1) runs. Rejects rather than clamping/normalizing -- an invalid
    // research-parameter value is a configuration error to surface, not a
    // number to silently repair. Hardening addition only; the model these
    // bounds gate (RiskScore/LoadScore/Sigmoid/AdaptiveCost below) is
    // unchanged.
    {
        std::vector<std::string> errors;
        if (!(kRisk > 0.0))
        {
            std::ostringstream m; m << "k_R must satisfy k_R > 0 (got " << kRisk << ")";
            errors.push_back(m.str());
        }
        if (!(kLoad > 0.0))
        {
            std::ostringstream m; m << "k_L must satisfy k_L > 0 (got " << kLoad << ")";
            errors.push_back(m.str());
        }
        if (!(x0Risk > 0.0 && x0Risk < 1.0))
        {
            std::ostringstream m; m << "x0_R must satisfy 0 < x0_R < 1 (got " << x0Risk << ")";
            errors.push_back(m.str());
        }
        if (!(x0Load > 0.0 && x0Load < 1.0))
        {
            std::ostringstream m; m << "x0_L must satisfy 0 < x0_L < 1 (got " << x0Load << ")";
            errors.push_back(m.str());
        }
        if (!(wRisk >= 0.0 && wRisk <= 1.0))
        {
            std::ostringstream m; m << "w_R must satisfy 0 <= w_R <= 1 (got " << wRisk << ")";
            errors.push_back(m.str());
        }
        if (!(wLoad >= 0.0 && wLoad <= 1.0))
        {
            std::ostringstream m; m << "w_L must satisfy 0 <= w_L <= 1 (got " << wLoad << ")";
            errors.push_back(m.str());
        }
        if (std::abs((wRisk + wLoad) - 1.0) > 1e-6)
        {
            std::ostringstream m; m << "w_R + w_L must equal 1.0 (got " << wRisk << " + " << wLoad
                                     << " = " << (wRisk + wLoad) << ")";
            errors.push_back(m.str());
        }
        if (!errors.empty())
        {
            std::ostringstream all;
            all << "Invalid V4 parameter configuration -- refusing to start (nothing was run):\n";
            for (const auto& e : errors)
            {
                all << "  " << e << "\n";
            }
            NS_FATAL_ERROR(all.str());
        }
    }

    // Auditability: print the exact configuration BEFORE Pass 1 launches --
    // not only in the end-of-run summary -- so a crash or hang during Pass
    // 1/2 still leaves a record of what was attempted.
    std::cout << "========================================\n"
              << "  Protocol      : V4 (Sigmoid-Based Adaptive Routing)\n"
              << "  Nodes         : " << nSensors << "\n"
              << "  Seed          : " << seed << "\n"
              << "  Traffic       : " << trafficLevel << "\n"
              << "  Mobility      : " << mobilityMode << "\n"
              << "  k_R           : " << kRisk << "\n"
              << "  x0_R          : " << x0Risk << "\n"
              << "  k_L           : " << kLoad << "\n"
              << "  x0_L          : " << x0Load << "\n"
              << "  w_R           : " << wRisk << "\n"
              << "  w_L           : " << wLoad << "\n"
              << "  Area          : " << areaSize << "x" << areaSize << " m\n"
              << "  txRange       : " << txRange << " m\n"
              << "  Duration      : " << simTime << " s\n"
              << "  Output dir    : " << outDir << "\n"
              << "========================================\n";

    uint32_t gatewayIndex = nSensors;
    uint32_t n = nSensors + 1;

    // Topology-only positions -- same method/seed as the rest of this file,
    // available with zero traffic dependency.
    std::mt19937 posRng(seed);
    std::uniform_real_distribution<double> coord(0.0, areaSize);
    std::vector<Vector> pos(n);
    for (uint32_t i = 0; i < nSensors; ++i)
    {
        pos[i] = Vector(coord(posRng), coord(posRng), 0.0);
    }
    pos[gatewayIndex] = Vector(areaSize / 2.0, areaSize / 2.0, 0.0);

    std::vector<std::vector<uint32_t>> adjacency = ComputeAdjacency(pos, txRange);

    std::vector<uint32_t> degree(n);
    uint32_t maxDegree = 0;
    for (uint32_t i = 0; i < n; ++i)
    {
        degree[i] = static_cast<uint32_t>(adjacency[i].size());
        maxDegree = std::max(maxDegree, degree[i]);
    }

    // RiskScore_ij = max(deg(i), deg(j)) / maxDegree, per approved model.
    std::map<std::pair<uint32_t, uint32_t>, double> riskScore;
    for (uint32_t i = 0; i < n; ++i)
    {
        for (uint32_t j : adjacency[i])
        {
            if (i < j)
            {
                double r = (maxDegree > 0)
                               ? static_cast<double>(std::max(degree[i], degree[j])) / maxDegree
                               : 0.0;
                riskScore[{i, j}] = r;
            }
        }
    }

    std::cout << "  [V4 Pass 1/2] baseline hop-count measurement run (results discarded, "
                 "only real link-byte counts kept)...\n";
    std::vector<int64_t> parent1 = BfsParent(adjacency, gatewayIndex);
    uint32_t unreachablePass1 = 0;
    V4PassStats pass1 = RunV4Pass(nSensors, simTime, appStart, areaSize, txPowerDbm, packetSize,
                                   seed, trafficLevel, mobilityMode, mobilitySpeedLow,
                                   mobilitySpeedMedium, pathSampleInterval, parent1, gatewayIndex,
                                   unreachablePass1);

    // LoadScore_ij: REAL measured bytes from Pass 1 (both directions summed
    // -- a shared wireless channel, either direction consumes the same
    // airtime), normalized the same way MaximumLinkUtilization already is
    // elsewhere in this file. An edge Pass 1 never used genuinely measures
    // 0.0 here -- never fabricated.
    const double kNominalPhyBps = 1.0e6;
    std::map<std::pair<uint32_t, uint32_t>, double> loadScore;
    std::map<std::pair<uint32_t, uint32_t>, double> adaptiveCost;
    for (const auto& kv : riskScore)
    {
        uint32_t i = kv.first.first;
        uint32_t j = kv.first.second;
        uint64_t bytesIJ = 0;
        auto it1 = pass1.linkBytes.find({i, j});
        if (it1 != pass1.linkBytes.end())
        {
            bytesIJ += it1->second;
        }
        auto it2 = pass1.linkBytes.find({j, i});
        if (it2 != pass1.linkBytes.end())
        {
            bytesIJ += it2->second;
        }
        double load = (bytesIJ * 8.0) / (kNominalPhyBps * simTime);
        load = std::min(1.0, std::max(0.0, load)); // clamp into [0,1] per the approved model
        loadScore[{i, j}] = load;

        double sigmoidRisk = 1.0 / (1.0 + std::exp(-kRisk * (kv.second - x0Risk)));
        double sigmoidLoad = 1.0 / (1.0 + std::exp(-kLoad * (load - x0Load)));
        double cost = wRisk * sigmoidRisk + wLoad * sigmoidLoad;
        if (!std::isfinite(cost))
        {
            NS_FATAL_ERROR("AdaptiveCost_ij produced a non-finite value for edge (" << i << ","
                                                                                     << j << ")");
        }
        adaptiveCost[{i, j}] = cost;
    }

    std::cout << "  [V4 Pass 2/2] AdaptiveCost-weighted Dijkstra routes installed, final "
                 "measurement run (this is the reported row)...\n";
    std::vector<int64_t> parent2 = DijkstraParent(adjacency, adaptiveCost, gatewayIndex);
    uint32_t unreachable = 0;
    V4PassStats pass2 = RunV4Pass(nSensors, simTime, appStart, areaSize, txPowerDbm, packetSize,
                                   seed, trafficLevel, mobilityMode, mobilitySpeedLow,
                                   mobilitySpeedMedium, pathSampleInterval, parent2, gatewayIndex,
                                   unreachable);
    if (unreachablePass1 != unreachable)
    {
        std::cout << "  Note: Pass 1 (baseline) had " << unreachablePass1
                  << " unreachable sensor(s); Pass 2 (V4) has " << unreachable
                  << " -- both walk the same adjacency graph so this should not normally differ; "
                     "investigate if it does.\n";
    }

    std::string dataRate = (trafficLevel == "low")    ? "4kbps"
                            : (trafficLevel == "high") ? "16kbps"
                                                        : "8kbps";
    double mobilitySpeed = (mobilityMode == "low")      ? mobilitySpeedLow
                           : (mobilityMode == "medium") ? mobilitySpeedMedium
                                                          : 0.0;

    uint64_t lost = (pass2.totalTx >= pass2.totalRx) ? (pass2.totalTx - pass2.totalRx) : 0;
    double pdr = (pass2.totalTx > 0) ? (100.0 * static_cast<double>(pass2.totalRx) / pass2.totalTx) : 0.0;
    double avgDelay = (pass2.totalRx > 0) ? (pass2.totalDelaySum / pass2.totalRx) : 0.0;
    double avgJitter = (pass2.totalRx > 0) ? (pass2.totalJitterSum / pass2.totalRx) : 0.0;
    double measurementWindow = simTime - appStart;
    double throughputKbps =
        (measurementWindow > 0) ? (pass2.totalRxBytes * 8.0 / 1000.0 / measurementWindow) : 0.0;

    // Hop count: exact, walked from each sensor up its Pass-2 Dijkstra
    // parent chain to the gateway -- same "exact" method Static uses, just
    // over the cost-tree instead of the BFS tree.
    double avgHopCount = 0.0;
    uint32_t hopCounted = 0;
    for (uint32_t i = 0; i < nSensors; ++i)
    {
        if (parent2[i] == -1)
        {
            continue;
        }
        uint32_t hops = 0;
        int64_t cur = static_cast<int64_t>(i);
        while (cur != static_cast<int64_t>(gatewayIndex) && cur != -1)
        {
            cur = parent2[static_cast<uint32_t>(cur)];
            ++hops;
        }
        avgHopCount += hops;
        ++hopCounted;
    }
    avgHopCount = (hopCounted > 0) ? (avgHopCount / hopCounted) : 0.0;

    double maxLinkUtilization = 0.0;
    double sumLinkUtilization = 0.0;
    uint32_t activeLinks = 0;
    for (const auto& kv : pass2.linkBytes)
    {
        double util = (kv.second * 8.0) / (kNominalPhyBps * simTime);
        maxLinkUtilization = std::max(maxLinkUtilization, util);
        sumLinkUtilization += util;
        ++activeLinks;
    }
    double avgLinkUtilization = (activeLinks > 0) ? (sumLinkUtilization / activeLinks) : 0.0;

    // NaN/Inf guard on every reported metric before writing the CSV row --
    // "verify no NaN/Inf/invalid routing metrics" is a hard requirement,
    // not just a smoke-test afterthought. Named (not a bare array) so a
    // failure report can say exactly which metric was invalid, plus the
    // full configuration and seed that produced it -- never silently
    // replaces NaN with 0 or Inf with a large number; the run is aborted
    // and nothing is written.
    std::vector<std::pair<std::string, double>> namedMetrics = {
        {"PDR", pdr},
        {"ThroughputKbps", throughputKbps},
        {"AverageDelaySec", avgDelay},
        {"AverageJitterSec", avgJitter},
        {"AverageHopCount", avgHopCount},
        {"AverageLinkUtilization", avgLinkUtilization},
        {"MaximumLinkUtilization", maxLinkUtilization},
    };
    for (const auto& nm : namedMetrics)
    {
        if (!std::isfinite(nm.second))
        {
            NS_FATAL_ERROR("V4 produced a non-finite (NaN/Inf) metric -- refusing to write a "
                            "result row.\n"
                            "  Failed metric : " << nm.first << " = " << nm.second << "\n"
                            "  Configuration : nodes=" << nSensors << " seed=" << seed
                            << " traffic=" << trafficLevel << " mobility=" << mobilityMode << "\n"
                            "  V4 parameters : k_R=" << kRisk << " x0_R=" << x0Risk
                            << " k_L=" << kLoad << " x0_L=" << x0Load << " w_R=" << wRisk
                            << " w_L=" << wLoad);
        }
    }

    std::cout << "========================================\n"
              << "  Protocol      : v4 (Sigmoid-Based Adaptive Routing)\n"
              << "  Sensors       : " << nSensors << "\n"
              << "  Traffic level : " << trafficLevel << " (" << dataRate << "/sensor)\n"
              << "  Mobility mode : " << mobilityMode;
    if (mobilityMode != "static")
    {
        std::cout << " (" << mobilitySpeed << " m/s)";
    }
    std::cout << "\n"
              << "  Seed          : " << seed << "\n"
              << "  V4 params     : k_R=" << kRisk << " x0_R=" << x0Risk << " k_L=" << kLoad
              << " x0_L=" << x0Load << " w_R=" << wRisk << " w_L=" << wLoad << "\n"
              << "  Tx packets    : " << pass2.totalTx << "\n"
              << "  Rx packets    : " << pass2.totalRx << "\n"
              << "  Packet loss   : " << lost << "\n"
              << "  PDR (%)       : " << pdr << "\n"
              << "  Throughput    : " << throughputKbps << " kbps\n"
              << "  Avg delay     : " << avgDelay << " s\n"
              << "  Avg jitter    : " << avgJitter << " s\n"
              << "  Routing ovhd  : " << pass2.routingOverheadPackets << " packets (best-effort)\n"
              << "  Avg hop count : " << avgHopCount << " (exact, V4 cost-tree)\n"
              << "  Path changes  : " << pass2.totalPathChanges << "\n"
              << "  Avg link util : " << avgLinkUtilization << "\n"
              << "  Max link util : " << maxLinkUtilization << "\n"
              << "  Unreachable   : " << unreachable << "\n"
              << "========================================\n";

    mkdir("results", 0755);
    mkdir(outDir.c_str(), 0755);
    std::string outFile =
        outDir + "/v4_" + std::to_string(nSensors) + "_" + trafficLevel + "_" + mobilityMode + ".csv";
    bool writeHeader = true;
    {
        std::ifstream existing(outFile);
        writeHeader = !existing.good();
    }
    std::ofstream out(outFile, std::ios::out | std::ios::app);
    if (writeHeader)
    {
        out << "Timestamp,Version,RoutingProtocol,NumberOfNodes,TrafficLevel,DataRate,"
               "MobilityMode,MobilitySpeed,Seed,Duration,PacketsSent,PacketsReceived,PacketLoss,"
               "PDR,ThroughputKbps,AverageDelaySec,AverageJitterSec,RoutingOverheadPackets,"
               "AverageHopCount,HopCountMethod,PathChanges,AverageLinkUtilization,"
               "MaximumLinkUtilization,UnreachableSensors,SigmoidKRisk,SigmoidX0Risk,"
               "SigmoidKLoad,SigmoidX0Load,WeightRisk,WeightLoad\n";
    }
    out << static_cast<int64_t>(std::time(nullptr)) << ",v4,v4," << nSensors << "," << trafficLevel
        << "," << dataRate << "," << mobilityMode << "," << mobilitySpeed << "," << seed << ","
        << simTime << "," << pass2.totalTx << "," << pass2.totalRx << "," << lost << "," << pdr
        << "," << throughputKbps << "," << avgDelay << "," << avgJitter << ","
        << pass2.routingOverheadPackets << "," << avgHopCount << ",exact," << pass2.totalPathChanges
        << "," << avgLinkUtilization << "," << maxLinkUtilization << "," << unreachable << ","
        << kRisk << "," << x0Risk << "," << kLoad << "," << x0Load << "," << wRisk << "," << wLoad
        << "\n";
    out.close();
}

} // namespace

int
main(int argc, char* argv[])
{
    // ------------------------------------------------------------------
    // Configuration.
    // ------------------------------------------------------------------
    uint32_t nSensors = 10;             // number of IoT sensor nodes (10..100 supported)
    std::string protocol = "aodv";      // aodv | olsr | static  ("sigmoid" refuses to run)
    double simTime = 300.0;             // total simulation time (s); 300-600 recommended
    double appStart = 30.0;             // app start time (s); lets routing converge first
    double areaSize = 250.0;            // sensors placed in [0, areaSize] x [0, areaSize] (m)
    double txPowerDbm = 20.0;           // Wifi transmit power (dBm)
    uint32_t packetSize = 512;          // application payload size (bytes)
    uint32_t seed = 1;                  // drives BOTH the position RNG and ns3::RngSeedManager
    double txRange = 90.0;              // nominal disk range (m) used for --protocol=static
    // NOTE: "results/v3" is already claimed by scratch/iot-network-v3.cc (a
    // different, pre-existing research track -- see docs/v3-experiment-framework.md's
    // "Three tracks" table). This program uses "results/v3-ext" instead so the
    // two can never collide even if both are run against the same results/ tree.
    std::string outDir = "results/v3-ext"; // output directory for the CSV file
    std::string trafficLevel = "medium"; // low | medium | high
    std::string mobilityMode = "static"; // static | low | medium
    double mobilitySpeedLow = 1.0;      // m/s, used when --mobilityMode=low
    double mobilitySpeedMedium = 5.0;   // m/s, used when --mobilityMode=medium
    double pathSampleInterval = 5.0;    // seconds between path-change samples

    // V4 -- Sigmoid-Based Adaptive Routing parameters, only used when
    // --protocol=v4. x0_R/x0_L default to 0.5 (the approved model's
    // documented starting point -- the midpoint of the [0,1] range both
    // RiskScore_ij and LoadScore_ij already live in, deliberately NOT
    // inheriting the paper's ambiguous 0-100-ish x0={30,50,70} since V4's
    // own inputs are explicitly normalized to [0,1]). k_R/k_L default to a
    // moderate, clearly-provisional value (2.0) pending the Stage-1
    // parameter sensitivity study called for in the approved design -- see
    // docs/v3-experiment-framework.md. w_R/w_L default to 0.5/0.5 (equal
    // weighting), also a documented starting point, not a validated value.
    double v4KRisk = 2.0;
    double v4X0Risk = 0.5;
    double v4KLoad = 2.0;
    double v4X0Load = 0.5;
    double v4WRisk = 0.5;
    double v4WLoad = 0.5;

    CommandLine cmd(__FILE__);
    cmd.AddValue("nSensors", "Number of IoT sensor nodes", nSensors);
    cmd.AddValue("protocol", "Routing protocol: aodv | olsr | static (sigmoid not implemented here)",
                 protocol);
    cmd.AddValue("simTime", "Total simulation time (s), 300-600 recommended", simTime);
    cmd.AddValue("appStart", "Application start time (s)", appStart);
    cmd.AddValue("areaSize", "Side length of the deployment square (m)", areaSize);
    cmd.AddValue("txPowerDbm", "Wifi transmit power (dBm)", txPowerDbm);
    cmd.AddValue("packetSize", "Application packet size (bytes)", packetSize);
    cmd.AddValue("seed", "Seed for topology, mobility and ns-3 RNG (reproducibility)", seed);
    cmd.AddValue("txRange", "Nominal disk range (m) for static route computation", txRange);
    cmd.AddValue("outDir", "Output directory for the result CSV", outDir);
    cmd.AddValue("trafficLevel", "Traffic level: low | medium | high", trafficLevel);
    cmd.AddValue("mobilityMode", "Mobility mode: static | low | medium", mobilityMode);
    cmd.AddValue("mobilitySpeedLow", "Constant speed (m/s) for mobilityMode=low", mobilitySpeedLow);
    cmd.AddValue("mobilitySpeedMedium", "Constant speed (m/s) for mobilityMode=medium",
                 mobilitySpeedMedium);
    cmd.AddValue("pathSampleInterval", "Seconds between path-change samples", pathSampleInterval);
    cmd.AddValue("v4KRisk", "V4: risk sigmoid steepness k_R", v4KRisk);
    cmd.AddValue("v4X0Risk", "V4: risk sigmoid midpoint x0_R (input is normalized to [0,1])",
                 v4X0Risk);
    cmd.AddValue("v4KLoad", "V4: load sigmoid steepness k_L", v4KLoad);
    cmd.AddValue("v4X0Load", "V4: load sigmoid midpoint x0_L (input is normalized to [0,1])",
                 v4X0Load);
    cmd.AddValue("v4WRisk", "V4: risk weight w_R (w_R + w_L must equal 1.0)", v4WRisk);
    cmd.AddValue("v4WLoad", "V4: load weight w_L (w_R + w_L must equal 1.0)", v4WLoad);
    cmd.Parse(argc, argv);

    if (protocol == "sigmoid")
    {
        std::cerr
            << "--protocol=sigmoid is NOT implemented in iot-network-v3-ext (this is the "
               "expanded-experiment-matrix / V2-topology-preserving track). Refusing to run "
               "rather than fabricate a result.\n"
               "A documented Sigmoid prototype exists at scratch/iot-network-v3.cc (fixed "
               "15-node clustered topology, geometry-proxy cost) -- kept as a separate, "
               "already-validated reference track. See docs/v3-experiment-framework.md for the "
               "planned Phase 2/3 path to a real adaptive/sigmoid metric on this topology. For "
               "the advisor-approved implementation, use --protocol=v4.\n";
        return 1;
    }
    if (protocol != "aodv" && protocol != "olsr" && protocol != "static" && protocol != "v4")
    {
        NS_FATAL_ERROR("Unknown --protocol '" << protocol
                                               << "': expected aodv | olsr | static | v4");
    }
    if (trafficLevel != "low" && trafficLevel != "medium" && trafficLevel != "high")
    {
        NS_FATAL_ERROR("Unknown --trafficLevel '" << trafficLevel
                                                   << "': expected low | medium | high");
    }
    if (mobilityMode != "static" && mobilityMode != "low" && mobilityMode != "medium")
    {
        NS_FATAL_ERROR("Unknown --mobilityMode '" << mobilityMode
                                                   << "': expected static | low | medium");
    }

    // V4 is dispatched here, completely separately from the AODV/OLSR/Static
    // code path below -- it builds and runs its own topology (twice; see
    // RunV4's own comment) and returns, so nothing below this block ever
    // executes for --protocol=v4. This guarantees V4 cannot change
    // AODV/OLSR/Static's existing behavior, by construction.
    if (protocol == "v4")
    {
        RunV4(nSensors, simTime, appStart, areaSize, txPowerDbm, packetSize, seed, txRange,
              outDir, trafficLevel, mobilityMode, mobilitySpeedLow, mobilitySpeedMedium,
              pathSampleInterval, v4KRisk, v4X0Risk, v4KLoad, v4X0Load, v4WRisk, v4WLoad);
        return 0;
    }

    // Traffic level -> per-sensor data rate. "medium" intentionally matches
    // V2's existing 8kbps baseline so V2 and V3 share a reference point; low
    // and high are +/-1 octave around it, matching the values already used
    // in docs/experiment-design.md's V3 traffic table.
    std::string dataRate = (trafficLevel == "low")    ? "4kbps"
                            : (trafficLevel == "high") ? "16kbps"
                                                        : "8kbps";

    double mobilitySpeed = (mobilityMode == "low")      ? mobilitySpeedLow
                           : (mobilityMode == "medium") ? mobilitySpeedMedium
                                                          : 0.0;

    Time::SetResolution(Time::NS);

    // A single seed drives both this program's independent position RNG
    // (as in V2) and ns-3's own RNG (which drives mobility waypoints,
    // AODV/OLSR jitter timers, etc). Mobility is installed (below) before
    // the routing stack in every run, so object-creation order up to that
    // point never depends on --protocol -- the mobility trace is therefore
    // identical across protocols for a given seed.
    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(1);

    // ------------------------------------------------------------------
    // Nodes: N sensors + 1 gateway (gateway is the last node / also the
    // application server / sink), exactly as in V2.
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
    // Positions: same method as V2 -- gateway at field centre, sensors
    // uniform-random, drawn from an independent RNG seeded only by --seed
    // (never touched by ns-3's own RNG), so the same --seed/--nSensors
    // always yields the same layout no matter which --protocol is
    // selected.
    // ------------------------------------------------------------------
    Ptr<ListPositionAllocator> positionAlloc = CreateObject<ListPositionAllocator>();

    std::mt19937 posRng(seed);
    std::uniform_real_distribution<double> coord(0.0, areaSize);
    for (uint32_t i = 0; i < nSensors; ++i)
    {
        positionAlloc->Add(Vector(coord(posRng), coord(posRng), 0.0));
    }
    positionAlloc->Add(Vector(areaSize / 2.0, areaSize / 2.0, 0.0)); // gateway, field centre

    // Gateway: always stationary, in every mobility mode.
    MobilityHelper gatewayMobility;
    Ptr<ListPositionAllocator> gatewayAlloc = CreateObject<ListPositionAllocator>();
    gatewayAlloc->Add(Vector(areaSize / 2.0, areaSize / 2.0, 0.0));
    gatewayMobility.SetPositionAllocator(gatewayAlloc);
    gatewayMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    gatewayMobility.Install(gateway);

    // Sensors: same initial layout in every mode (t=0 positions never
    // depend on --mobilityMode); static keeps them fixed for the whole
    // run, low/medium let them roam via RandomWaypoint at a constant
    // configured speed.
    Ptr<ListPositionAllocator> sensorAlloc = CreateObject<ListPositionAllocator>();
    std::mt19937 posRng2(seed);
    for (uint32_t i = 0; i < nSensors; ++i)
    {
        sensorAlloc->Add(Vector(coord(posRng2), coord(posRng2), 0.0));
    }

    MobilityHelper sensorMobility;
    sensorMobility.SetPositionAllocator(sensorAlloc);
    if (mobilityMode == "static")
    {
        sensorMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    }
    else
    {
        Ptr<RandomBoxPositionAllocator> waypointAlloc = CreateObject<RandomBoxPositionAllocator>();
        Ptr<UniformRandomVariable> xVar = CreateObject<UniformRandomVariable>();
        xVar->SetAttribute("Min", DoubleValue(0.0));
        xVar->SetAttribute("Max", DoubleValue(areaSize));
        Ptr<UniformRandomVariable> yVar = CreateObject<UniformRandomVariable>();
        yVar->SetAttribute("Min", DoubleValue(0.0));
        yVar->SetAttribute("Max", DoubleValue(areaSize));
        waypointAlloc->SetX(xVar);
        waypointAlloc->SetY(yVar);
        waypointAlloc->SetZ(CreateObject<ConstantRandomVariable>()); // default Constant=0.0

        std::ostringstream speedStr;
        speedStr << "ns3::ConstantRandomVariable[Constant=" << mobilitySpeed << "]";
        sensorMobility.SetMobilityModel("ns3::RandomWaypointMobilityModel",
                                         "Speed", StringValue(speedStr.str()),
                                         "Pause", StringValue("ns3::ConstantRandomVariable[Constant=2.0]"),
                                         "PositionAllocator", PointerValue(waypointAlloc));
    }
    sensorMobility.Install(sensors);

    // ------------------------------------------------------------------
    // Wireless PHY/MAC: identical to V2 -- single shared 802.11b ad-hoc
    // channel, 1 Mbps DSSS, log-distance path loss.
    // ------------------------------------------------------------------
    Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode",
                        StringValue("DsssRate1Mbps"));

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

    // Build the MAC-address -> node-index map used by the MLU trace, and
    // hook every device's PhyTxBegin trace source now, before any traffic
    // runs.
    const double kNominalPhyBps = 1.0e6; // DsssRate1Mbps nominal air rate
    for (uint32_t i = 0; i < devices.GetN(); ++i)
    {
        Mac48Address addr = Mac48Address::ConvertFrom(devices.Get(i)->GetAddress());
        g_macToNode[addr] = i;
        Ptr<WifiNetDevice> wifiDev = DynamicCast<WifiNetDevice>(devices.Get(i));
        wifiDev->GetPhy()->TraceConnectWithoutContext("PhyTxBegin", MakeBoundCallback(&OnPhyTxBegin, i));
    }

    // ------------------------------------------------------------------
    // Routing + Internet stack -- identical mechanism to V2.
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

    internet.Install(allNodes);

    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    Ipv4Address gatewayAddr = interfaces.GetAddress(gatewayIndex);

    // hopCount[i]: exact BFS depth for static routing; unused (left at -1)
    // for AODV/OLSR, which use the FlowMonitor-based approximation instead.
    std::vector<int64_t> exactHopCount(nSensors, -1);
    uint32_t unreachable = 0;

    if (protocol == "static")
    {
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
        std::vector<int64_t> parent(n, -1);
        std::vector<int64_t> depth(n, -1);
        std::queue<uint32_t> bfsQueue;
        visited[gatewayIndex] = true;
        depth[gatewayIndex] = 0;
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
                    depth[v] = depth[u] + 1;
                    bfsQueue.push(v);
                }
            }
        }

        Ipv4StaticRoutingHelper staticRoutingHelper;
        for (uint32_t i = 0; i < nSensors; ++i)
        {
            if (parent[i] == -1)
            {
                ++unreachable;
                continue;
            }
            exactHopCount[i] = depth[i];
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
    // gateway, exactly as V2, at the rate implied by --trafficLevel.
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
    // Path-change sampling: starts a little after appStart so that, for
    // AODV, the first sample lands on an already-converged route rather
    // than racing the very first route discovery.
    // ------------------------------------------------------------------
    Ptr<PathSampler> pathSampler = Create<PathSampler>();
    pathSampler->lastHop.assign(nSensors, kNoRoute);
    pathSampler->initialized.assign(nSensors, false);
    pathSampler->changes.assign(nSensors, 0);
    double firstSample = appStart + pathSampleInterval;
    if (firstSample < simTime)
    {
        Simulator::Schedule(Seconds(firstSample),
                             &SampleRoutesOnce,
                             pathSampler,
                             sensors,
                             gatewayAddr,
                             pathSampleInterval,
                             simTime);
    }

    // ------------------------------------------------------------------
    // FlowMonitor.
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
    double totalDelaySum = 0.0;
    double totalJitterSum = 0.0;
    uint64_t totalTimesForwarded = 0;
    uint64_t routingOverheadPackets = 0; // best-effort; see docs/v3-experiment-framework.md

    for (const auto& flow : monitor->GetFlowStats())
    {
        Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(flow.first);

        // AODV control traffic: UDP port 654. OLSR control traffic: UDP
        // port 698. FlowMonitor's SendOutgoing trace skips non-unicast
        // destinations, so broadcast HELLO/TC/RREQ frames are NOT counted
        // here -- this undercounts true routing overhead for AODV/OLSR
        // (see docs/v3-experiment-framework.md for the full explanation,
        // carried over unchanged from the existing V3 sigmoid-prototype's
        // methodology.md finding). Static has zero *runtime* control
        // overhead by construction, which is correctly captured.
        if (t.destinationPort == 654 || t.sourcePort == 654 || t.destinationPort == 698 ||
            t.sourcePort == 698)
        {
            routingOverheadPackets += flow.second.txPackets;
            continue;
        }

        if (t.destinationAddress != gatewayAddr)
        {
            continue;
        }
        totalTx += flow.second.txPackets;
        totalRx += flow.second.rxPackets;
        totalRxBytes += flow.second.rxBytes;
        totalDelaySum += flow.second.delaySum.GetSeconds();
        totalJitterSum += flow.second.jitterSum.GetSeconds();
        totalTimesForwarded += flow.second.timesForwarded;
    }

    uint64_t lost = (totalTx >= totalRx) ? (totalTx - totalRx) : 0;
    double pdr = (totalTx > 0) ? (100.0 * static_cast<double>(totalRx) / totalTx) : 0.0;
    double avgDelay = (totalRx > 0) ? (totalDelaySum / totalRx) : 0.0;
    double avgJitter = (totalRx > 0) ? (totalJitterSum / totalRx) : 0.0;
    double measurementWindow = simTime - appStart;
    double throughputKbps =
        (measurementWindow > 0) ? (totalRxBytes * 8.0 / 1000.0 / measurementWindow) : 0.0;

    // Hop count: exact for static (from the BFS tree), approximate for
    // AODV/OLSR (1 + timesForwarded/rxPackets, averaged over received
    // packets -- see docs/v3-experiment-framework.md).
    double avgHopCount = 0.0;
    std::string hopCountMethod;
    if (protocol == "static")
    {
        hopCountMethod = "exact";
        uint32_t counted = 0;
        for (uint32_t i = 0; i < nSensors; ++i)
        {
            if (exactHopCount[i] >= 0)
            {
                avgHopCount += static_cast<double>(exactHopCount[i]);
                ++counted;
            }
        }
        avgHopCount = (counted > 0) ? (avgHopCount / counted) : 0.0;
    }
    else
    {
        hopCountMethod = "approx_timesForwarded";
        avgHopCount = (totalRx > 0) ? (1.0 + static_cast<double>(totalTimesForwarded) / totalRx)
                                    : 0.0;
    }

    // Path changes: sum across sensors of observed next-hop transitions.
    uint64_t totalPathChanges = 0;
    for (uint32_t c : pathSampler->changes)
    {
        totalPathChanges += c;
    }

    // Link utilization: per (src,dst) unicast MAC pair, bytes*8 / (nominal
    // PHY bit rate * simTime). This is an offered-load proxy on a shared
    // random-access channel, not a measured channel-busy fraction -- see
    // docs/v3-experiment-framework.md for the honest limitation.
    double maxLinkUtilization = 0.0;
    double sumLinkUtilization = 0.0;
    uint32_t activeLinks = 0;
    for (const auto& kv : g_linkBytes)
    {
        double util = (kv.second * 8.0) / (kNominalPhyBps * simTime);
        maxLinkUtilization = std::max(maxLinkUtilization, util);
        sumLinkUtilization += util;
        ++activeLinks;
    }
    double avgLinkUtilization = (activeLinks > 0) ? (sumLinkUtilization / activeLinks) : 0.0;

    std::cout << "========================================\n"
              << "  Protocol      : " << protocol << "\n"
              << "  Sensors       : " << nSensors << "\n"
              << "  Traffic level : " << trafficLevel << " (" << dataRate << "/sensor)\n"
              << "  Mobility mode : " << mobilityMode;
    if (mobilityMode != "static")
    {
        std::cout << " (" << mobilitySpeed << " m/s)";
    }
    std::cout << "\n"
              << "  Seed          : " << seed << "\n"
              << "  Tx packets    : " << totalTx << "\n"
              << "  Rx packets    : " << totalRx << "\n"
              << "  Packet loss   : " << lost << "\n"
              << "  PDR (%)       : " << pdr << "\n"
              << "  Throughput    : " << throughputKbps << " kbps\n"
              << "  Avg delay     : " << avgDelay << " s\n"
              << "  Avg jitter    : " << avgJitter << " s\n"
              << "  Routing ovhd  : " << routingOverheadPackets << " packets (best-effort)\n"
              << "  Avg hop count : " << avgHopCount << " (" << hopCountMethod << ")\n"
              << "  Path changes  : " << totalPathChanges << "\n"
              << "  Avg link util : " << avgLinkUtilization << "\n"
              << "  Max link util : " << maxLinkUtilization << "\n"
              << "========================================\n";

    mkdir("results", 0755);
    mkdir(outDir.c_str(), 0755);
    std::string outFile =
        outDir + "/" + protocol + "_" + std::to_string(nSensors) + "_" + trafficLevel + "_" +
        mobilityMode + ".csv";
    bool writeHeader = true;
    {
        std::ifstream existing(outFile);
        writeHeader = !existing.good();
    }
    std::ofstream out(outFile, std::ios::out | std::ios::app);
    if (writeHeader)
    {
        out << "Timestamp,Version,RoutingProtocol,NumberOfNodes,TrafficLevel,DataRate,"
               "MobilityMode,MobilitySpeed,Seed,Duration,PacketsSent,PacketsReceived,PacketLoss,"
               "PDR,ThroughputKbps,AverageDelaySec,AverageJitterSec,RoutingOverheadPackets,"
               "AverageHopCount,HopCountMethod,PathChanges,AverageLinkUtilization,"
               "MaximumLinkUtilization,UnreachableSensors\n";
    }
    out << static_cast<int64_t>(std::time(nullptr)) << ",v3," << protocol << "," << nSensors
        << "," << trafficLevel << "," << dataRate << "," << mobilityMode << "," << mobilitySpeed
        << "," << seed << "," << simTime << "," << totalTx << "," << totalRx << "," << lost << ","
        << pdr << "," << throughputKbps << "," << avgDelay << "," << avgJitter << ","
        << routingOverheadPackets << "," << avgHopCount << "," << hopCountMethod << ","
        << totalPathChanges << "," << avgLinkUtilization << "," << maxLinkUtilization << ","
        << unreachable << "\n";
    out.close();

    Simulator::Destroy();
    return 0;
}
