/*
 * IoT Network Performance Analysis - V3 (sigmoid-metric research extension)
 *
 * A SEPARATE simulation program from scratch/iot-network.cc (V2.7). V2.7 is
 * left byte-for-byte untouched so the binary that produced the 60 existing
 * results CSV rows remains exactly reproducible. This file is a new,
 * independent study: a 15-node heterogeneous topology comparing AODV, OLSR,
 * a "legacy/static" baseline, and a new "sigmoid" routing mode, inspired by
 * (but not a reproduction of) Thaenchaikun, Kanjanasit & Chantara,
 * "Enhancement of Network Performance Using Sigmoid-Based Metrics on a
 * Routing Protocol", ECTI-CON 2025, DOI 10.1109/ECTI-CON64996.2025.11100445
 * -- that paper has not been read by the author of this code; the sigmoid
 * design below is independently derived. See docs/sigmoid-metric.md for the
 * full justification of every design choice made here.
 *
 * ------------------------------------------------------------------------
 * Topology (fixed node roles, never renumbered):
 *   Node 0        Gateway/Sink -- the only node bridging the wireless mesh
 *                 and the wired backhaul to the Server.
 *   Node 1        Server -- reached from the Gateway via a wired
 *                 point-to-point backhaul link, OUTSIDE the wireless mesh.
 *                 It never participates in AODV/OLSR/static/sigmoid routing
 *                 -- this deliberately avoids the "internet gateway" problem
 *                 (OLSR has HNA advertisement for external subnets, AODV's
 *                 ns-3 implementation does not, so giving sensors a route to
 *                 an external Server subnet would require a different,
 *                 non-comparable mechanism per protocol, exactly what V2.7's
 *                 design note already flagged as unfair). The routing
 *                 comparison stays on the sensor-to-Gateway hop only, same
 *                 measurement boundary as V2.7; the Gateway-Server hop is a
 *                 simple, always-on relay, not part of the measured metrics.
 *   Nodes 2-14    13 IoT sensor/relay nodes in 3 clusters at increasing
 *                 distance from the Gateway (near/middle/far), reusing the
 *                 hybrid-clustered design proposed earlier for V2.8.
 *
 * Routing modes, --protocol=:
 *   aodv, olsr    Unchanged from V2.7 -- untouched ns-3 core AODV/OLSR.
 *   static        Same BFS shortest-hop-count approach as V2.7's "static".
 *   sigmoid       Same offline graph/host-route architecture as "static",
 *                 but edges are weighted by a sigmoid composite cost
 *                 (see ComputeEdgeCost() below) and the shortest-COST path
 *                 is found with Dijkstra instead of unweighted BFS.
 *                 IMPORTANT: because routes are computed once, before
 *                 traffic starts (same timing as "static"), the sigmoid's
 *                 inputs cannot be true live-measured delay/jitter/loss --
 *                 they are geometry-derived proxies. This is an "offline
 *                 sigmoid-weighted route selection" baseline, NOT reactive
 *                 adaptive routing. See docs/sigmoid-metric.md.
 *
 * Node positions are drawn from an independent std::mt19937 seeded only by
 * --posSeed (never touched by ns-3's own RNG), exactly as in V2.7, so a
 * given --posSeed produces identical positions regardless of --protocol.
 *
 * Output: appends one CSV row per run to
 *   <outDir>/<protocol>_15_<traffic>.csv
 * -- a directory and naming scheme entirely separate from V2.7's
 * <outDir>/<protocol>_<nSensors>.csv, so nothing here can collide with or
 * overwrite existing V2.7 results.
 */

#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/wifi-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/aodv-module.h"
#include "ns3/olsr-module.h"
#include "ns3/flow-monitor-module.h"

#include <cmath>
#include <fstream>
#include <limits>
#include <queue>
#include <random>
#include <sys/stat.h>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("IotNetworkV3");

namespace
{

double
Sigmoid(double x, double k, double x0)
{
    return 1.0 / (1.0 + std::exp(-k * (x - x0)));
}

/*
 * Two independent, geometrically-justified proxies, not four. A naive
 * expansion to delay/jitter/loss/load would require deriving several
 * "different" inputs from the same pre-simulation distance measurement,
 * which adds no genuine independent information despite superficially
 * matching the reference paper's variable count -- see
 * docs/sigmoid-metric.md for the full reasoning.
 *
 *   linkQuality = distance / txRange   in [0,1]; higher = weaker expected
 *                 link (closer to the edge of range), plausibly correlated
 *                 with higher delay/jitter/loss risk in real RF, all from
 *                 the same underlying physical driver.
 *   load        = average node degree of the edge's two endpoints,
 *                 normalized by the graph's maximum degree; higher = the
 *                 edge sits at a busier relay point, a proxy for expected
 *                 channel contention.
 *
 * Both are already in [0,1], so x0 defaults to 0.5 (the midpoint of that
 * range) unless overridden.
 */
double
ComputeEdgeCost(double distance,
                 double txRange,
                 double degreeI,
                 double degreeJ,
                 double maxDegree,
                 double k,
                 double x0,
                 double wLinkQuality,
                 double wLoad)
{
    double linkQuality = distance / txRange;
    double load = (maxDegree > 0) ? ((degreeI + degreeJ) / 2.0) / maxDegree : 0.0;
    double sLinkQuality = Sigmoid(linkQuality, k, x0);
    double sLoad = Sigmoid(load, k, x0);
    return wLinkQuality * sLinkQuality + wLoad * sLoad;
}

} // namespace

int
main(int argc, char* argv[])
{
    // ------------------------------------------------------------------
    // Configuration -- identical across protocols for a given seed/traffic.
    // ------------------------------------------------------------------
    uint32_t nRelayNodes = 13;        // Nodes 2..14: sensor/relay nodes
    std::string protocol = "aodv";    // aodv | olsr | static | sigmoid
    std::string trafficCondition = "medium"; // low | medium | high (label only; --dataRate is authoritative)
    double simTime = 100.0;
    double appStart = 30.0;
    double areaSize = 250.0;
    double txPowerDbm = 20.0;
    uint32_t packetSize = 512;
    std::string dataRate = "8kbps";   // per-sensor CBR rate; see experiments/ for low/medium/high presets
    uint32_t posSeed = 1;
    double txRange = 90.0;            // nominal disk range for static/sigmoid route computation
    std::string outDir = "results/v3";

    // Sigmoid parameters (only used when --protocol=sigmoid)
    double sigmoidK = 0.2;
    double sigmoidX0 = 0.5;
    double sigmoidWLinkQuality = 0.5;
    double sigmoidWLoad = 0.5;

    CommandLine cmd(__FILE__);
    cmd.AddValue("nRelayNodes", "Number of sensor/relay nodes (Nodes 2..N+1)", nRelayNodes);
    cmd.AddValue("protocol", "Routing protocol: aodv | olsr | static | sigmoid", protocol);
    cmd.AddValue("trafficCondition", "Traffic condition label: low | medium | high (informational; set --dataRate to match)", trafficCondition);
    cmd.AddValue("simTime", "Total simulation time (s)", simTime);
    cmd.AddValue("appStart", "Application start time (s)", appStart);
    cmd.AddValue("areaSize", "Side length of the deployment square (m)", areaSize);
    cmd.AddValue("txPowerDbm", "Wifi transmit power (dBm)", txPowerDbm);
    cmd.AddValue("packetSize", "Application packet size (bytes)", packetSize);
    cmd.AddValue("dataRate", "Per-sensor application data rate", dataRate);
    cmd.AddValue("posSeed", "Seed for node-position RNG (topology reproducibility)", posSeed);
    cmd.AddValue("txRange", "Nominal disk range (m) for static/sigmoid route computation", txRange);
    cmd.AddValue("outDir", "Output directory for the result CSV (kept separate from V2.7's results/)", outDir);
    cmd.AddValue("sigmoidK", "Sigmoid steepness k (protocol=sigmoid only)", sigmoidK);
    cmd.AddValue("sigmoidX0", "Sigmoid inflection point x0 (protocol=sigmoid only)", sigmoidX0);
    cmd.AddValue("sigmoidWLinkQuality", "Weight for the link-quality proxy (protocol=sigmoid only)", sigmoidWLinkQuality);
    cmd.AddValue("sigmoidWLoad", "Weight for the load proxy (protocol=sigmoid only)", sigmoidWLoad);
    cmd.Parse(argc, argv);

    if (protocol != "aodv" && protocol != "olsr" && protocol != "static" && protocol != "sigmoid")
    {
        NS_FATAL_ERROR("Unknown --protocol '" << protocol << "': expected aodv | olsr | static | sigmoid");
    }

    Time::SetResolution(Time::NS);

    // ------------------------------------------------------------------
    // Nodes: fixed roles, never renumbered.
    //   Node 0            Gateway
    //   Node 1            Server
    //   Node 2..14        13 sensor/relay nodes
    // ------------------------------------------------------------------
    NodeContainer gateway;
    gateway.Create(1);
    NodeContainer server;
    server.Create(1);
    NodeContainer sensors;
    sensors.Create(nRelayNodes);

    NodeContainer meshNodes; // wireless mesh participants: gateway + sensors
    meshNodes.Add(gateway);
    meshNodes.Add(sensors);
    uint32_t gatewayMeshIndex = 0;

    NodeContainer allNodes; // for global bookkeeping (positions, indices 0..14)
    allNodes.Add(gateway);  // global index 0
    allNodes.Add(server);   // global index 1
    allNodes.Add(sensors);  // global index 2..14

    // ------------------------------------------------------------------
    // Positions: 3 clusters at increasing distance from the Gateway corner,
    // reusing the hybrid-clustered layout proposed for V2.8. Drawn from an
    // independent RNG seeded only by posSeed, so the same posSeed always
    // yields the same layout regardless of --protocol.
    // ------------------------------------------------------------------
    Vector gatewayPos(20.0, 20.0, 0.0);
    Vector serverPos(35.0, 20.0, 0.0); // beside the gateway; reached only via the wired p2p link

    struct Cluster
    {
        Vector center;
        uint32_t count;
        double radius;
    };
    std::vector<Cluster> clusters = {
        {Vector(69.5, 69.5, 0.0), 4, 22.0},  // near cluster: Nodes 2-5
        {Vector(145.0, 105.0, 0.0), 4, 22.0}, // middle cluster: Nodes 6-9
        {Vector(195.0, 175.0, 0.0), 5, 22.0}, // far cluster: Nodes 10-14
    };

    Ptr<ListPositionAllocator> positionAlloc = CreateObject<ListPositionAllocator>();
    positionAlloc->Add(gatewayPos);
    positionAlloc->Add(serverPos);

    std::mt19937 posRng(posSeed);
    std::uniform_real_distribution<double> unit(-1.0, 1.0);
    uint32_t placed = 0;
    for (const auto& c : clusters)
    {
        for (uint32_t i = 0; i < c.count && placed < nRelayNodes; ++i, ++placed)
        {
            double x = c.center.x + unit(posRng) * c.radius;
            double y = c.center.y + unit(posRng) * c.radius;
            positionAlloc->Add(Vector(x, y, 0.0));
        }
    }
    // If nRelayNodes differs from the sum of cluster counts (13), place any
    // remainder uniformly across the field so the program still runs for
    // other node counts, clearly outside the documented 15-node design.
    for (; placed < nRelayNodes; ++placed)
    {
        std::uniform_real_distribution<double> coord(0.0, areaSize);
        positionAlloc->Add(Vector(coord(posRng), coord(posRng), 0.0));
    }

    MobilityHelper mobility;
    mobility.SetPositionAllocator(positionAlloc);
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(allNodes);

    // ------------------------------------------------------------------
    // Wireless PHY/MAC: identical parameters to V2.7, installed only on
    // the mesh participants (Gateway + sensors). The Server has no wifi
    // device at all -- it is reached only via the wired backhaul below.
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

    NetDeviceContainer meshDevices = wifi.Install(wifiPhy, wifiMac, meshNodes);

    // ------------------------------------------------------------------
    // Wired Gateway<->Server backhaul: outside the wireless mesh, outside
    // the routing-protocol comparison. A simple, always-reliable hop.
    // ------------------------------------------------------------------
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("10Mbps"));
    p2p.SetChannelAttribute("Delay", StringValue("2ms"));
    NetDeviceContainer backhaulDevices = p2p.Install(gateway.Get(0), server.Get(0));

    // ------------------------------------------------------------------
    // Routing + Internet stack.
    // ------------------------------------------------------------------
    InternetStackHelper internet;

    AodvHelper aodv;
    OlsrHelper olsr;
    Ipv4StaticRoutingHelper staticRoutingHelper;
    Ipv4ListRoutingHelper list;

    if (protocol == "aodv")
    {
        list.Add(staticRoutingHelper, 0); // low priority: only used for the Gateway's backhaul subnet
        list.Add(aodv, 10);
        internet.SetRoutingHelper(list);
    }
    else if (protocol == "olsr")
    {
        list.Add(staticRoutingHelper, 0);
        list.Add(olsr, 10);
        internet.SetRoutingHelper(list);
    }
    // "static"/"sigmoid": leave the default stack (Ipv4StaticRouting only);
    // host routes for the mesh are computed and installed manually below.

    internet.Install(allNodes);

    Ipv4AddressHelper meshAddress;
    meshAddress.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer meshInterfaces = meshAddress.Assign(meshDevices);

    Ipv4AddressHelper backhaulAddress;
    backhaulAddress.SetBase("10.2.1.0", "255.255.255.252"); // /30: gateway + server only
    Ipv4InterfaceContainer backhaulInterfaces = backhaulAddress.Assign(backhaulDevices);

    Ipv4Address gatewayMeshAddr = meshInterfaces.GetAddress(gatewayMeshIndex);
    Ipv4Address serverAddr = backhaulInterfaces.GetAddress(1);

    // ------------------------------------------------------------------
    // Static / Sigmoid: build the mesh connectivity graph from node
    // positions (edge if distance <= txRange) once, offline. "static" uses
    // unweighted BFS (shortest hop count); "sigmoid" uses Dijkstra over
    // ComputeEdgeCost() weights. Both install the result as
    // Ipv4StaticRouting host routes -- this is real route computation that
    // determines what path packets actually take, not a cosmetic label.
    // ------------------------------------------------------------------
    std::string routeComputationLog;
    uint32_t unreachableSensors = 0;
    double avgHopCountExact = 0.0;

    if (protocol == "static" || protocol == "sigmoid")
    {
        uint32_t n = meshNodes.GetN(); // gateway + sensors only
        std::vector<Vector> pos(n);
        for (uint32_t i = 0; i < n; ++i)
        {
            pos[i] = meshNodes.Get(i)->GetObject<MobilityModel>()->GetPosition();
        }

        std::vector<std::vector<uint32_t>> adjacency(n);
        std::vector<std::vector<double>> distance(n, std::vector<double>(n, 0.0));
        for (uint32_t i = 0; i < n; ++i)
        {
            for (uint32_t j = i + 1; j < n; ++j)
            {
                double d = CalculateDistance(pos[i], pos[j]);
                if (d <= txRange)
                {
                    adjacency[i].push_back(j);
                    adjacency[j].push_back(i);
                    distance[i][j] = distance[j][i] = d;
                }
            }
        }

        std::vector<uint32_t> degree(n);
        uint32_t maxDegree = 0;
        for (uint32_t i = 0; i < n; ++i)
        {
            degree[i] = adjacency[i].size();
            maxDegree = std::max(maxDegree, degree[i]);
        }

        std::vector<int64_t> parent(n, -1);
        std::vector<uint32_t> hopCount(n, 0);

        if (protocol == "static")
        {
            std::vector<bool> visited(n, false);
            std::queue<uint32_t> bfsQueue;
            visited[gatewayMeshIndex] = true;
            bfsQueue.push(gatewayMeshIndex);
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
                        hopCount[v] = hopCount[u] + 1;
                        bfsQueue.push(v);
                    }
                }
            }
        }
        else // sigmoid: Dijkstra over ComputeEdgeCost() weights
        {
            std::vector<double> costToNode(n, std::numeric_limits<double>::infinity());
            std::vector<bool> settled(n, false);
            costToNode[gatewayMeshIndex] = 0.0;
            using PQEntry = std::pair<double, uint32_t>;
            std::priority_queue<PQEntry, std::vector<PQEntry>, std::greater<PQEntry>> pq;
            pq.push({0.0, gatewayMeshIndex});
            while (!pq.empty())
            {
                auto [cost, u] = pq.top();
                pq.pop();
                if (settled[u])
                {
                    continue;
                }
                settled[u] = true;
                for (uint32_t v : adjacency[u])
                {
                    double edgeCost = ComputeEdgeCost(distance[u][v], txRange, degree[u], degree[v],
                                                       maxDegree, sigmoidK, sigmoidX0,
                                                       sigmoidWLinkQuality, sigmoidWLoad);
                    double newCost = costToNode[u] + edgeCost;
                    if (newCost < costToNode[v])
                    {
                        costToNode[v] = newCost;
                        parent[v] = u;
                        hopCount[v] = hopCount[u] + 1;
                        pq.push({newCost, v});
                    }
                }
            }
        }

        uint32_t reachableCount = 0;
        for (uint32_t i = 0; i < nRelayNodes; ++i)
        {
            uint32_t meshIdx = i + 1; // sensor i is meshNodes index i+1 (0 is gateway)
            if (parent[meshIdx] == -1)
            {
                ++unreachableSensors;
                continue;
            }
            Ptr<Ipv4> ipv4 = sensors.Get(i)->GetObject<Ipv4>();
            Ptr<Ipv4StaticRouting> sr = staticRoutingHelper.GetStaticRouting(ipv4);
            Ipv4Address nextHopAddr = meshInterfaces.GetAddress(static_cast<uint32_t>(parent[meshIdx]));
            uint32_t ifIndex = ipv4->GetInterfaceForDevice(meshDevices.Get(meshIdx));
            sr->AddHostRouteTo(gatewayMeshAddr, nextHopAddr, ifIndex);
            avgHopCountExact += hopCount[meshIdx];
            ++reachableCount;
        }
        if (reachableCount > 0)
        {
            avgHopCountExact /= reachableCount;
        }
        if (unreachableSensors > 0)
        {
            std::cout << "  Note: " << unreachableSensors << " sensor(s) unreachable within txRange="
                      << txRange << " m under " << protocol << " routing.\n";
        }
    }

    // Gateway <-> Server backhaul route (always present, any protocol):
    // both ends already have a direct/on-link route to the /30 subnet
    // automatically via Ipv4StaticRouting's interface-address tracking --
    // no extra route needed for that hop itself.

    // ------------------------------------------------------------------
    // Applications.
    //  - Sensors -> Gateway: the measured routing-comparison traffic,
    //    identical in kind to V2.7 (one UDP CBR flow per sensor).
    //  - Gateway -> Server: a simple periodic backhaul relay over the
    //    wired link, to make the topology's Node 1 (Server) real and
    //    functional. NOT part of the routing-protocol comparison metrics.
    // ------------------------------------------------------------------
    uint16_t sensorPort = 9;

    PacketSinkHelper gatewaySink("ns3::UdpSocketFactory",
                                  InetSocketAddress(Ipv4Address::GetAny(), sensorPort));
    ApplicationContainer gatewaySinkApp = gatewaySink.Install(gateway.Get(0));
    gatewaySinkApp.Start(Seconds(0.0));
    gatewaySinkApp.Stop(Seconds(simTime));

    ApplicationContainer sourceApps;
    for (uint32_t i = 0; i < nRelayNodes; ++i)
    {
        OnOffHelper onoff("ns3::UdpSocketFactory", InetSocketAddress(gatewayMeshAddr, sensorPort));
        onoff.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
        onoff.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
        onoff.SetAttribute("PacketSize", UintegerValue(packetSize));
        onoff.SetAttribute("DataRate", StringValue(dataRate));

        ApplicationContainer app = onoff.Install(sensors.Get(i));
        app.Start(Seconds(appStart));
        app.Stop(Seconds(simTime));
        sourceApps.Add(app);
    }

    uint16_t backhaulPort = 10;
    PacketSinkHelper serverSink("ns3::UdpSocketFactory",
                                 InetSocketAddress(Ipv4Address::GetAny(), backhaulPort));
    ApplicationContainer serverSinkApp = serverSink.Install(server.Get(0));
    serverSinkApp.Start(Seconds(0.0));
    serverSinkApp.Stop(Seconds(simTime));

    OnOffHelper backhaulRelay("ns3::UdpSocketFactory", InetSocketAddress(serverAddr, backhaulPort));
    backhaulRelay.SetAttribute("OnTime", StringValue("ns3::ConstantRandomVariable[Constant=1]"));
    backhaulRelay.SetAttribute("OffTime", StringValue("ns3::ConstantRandomVariable[Constant=0]"));
    backhaulRelay.SetAttribute("PacketSize", UintegerValue(64));
    backhaulRelay.SetAttribute("DataRate", StringValue("1kbps"));
    ApplicationContainer backhaulApp = backhaulRelay.Install(gateway.Get(0));
    backhaulApp.Start(Seconds(appStart));
    backhaulApp.Stop(Seconds(simTime));

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
    uint64_t totalForwards = 0;    // for AODV/OLSR hop-count approximation
    uint64_t overheadPackets = 0;  // AODV (port 654) / OLSR (port 698) control traffic

    for (const auto& flow : monitor->GetFlowStats())
    {
        Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(flow.first);

        if (t.destinationPort == 654 || t.destinationPort == 698 ||
            t.sourcePort == 654 || t.sourcePort == 698)
        {
            overheadPackets += flow.second.txPackets;
            continue;
        }
        if (t.destinationAddress != gatewayMeshAddr || t.destinationPort != sensorPort)
        {
            continue;
        }
        totalTx += flow.second.txPackets;
        totalRx += flow.second.rxPackets;
        totalRxBytes += flow.second.rxBytes;
        totalDelaySum += flow.second.delaySum.GetSeconds();
        totalJitterSum += flow.second.jitterSum.GetSeconds();
        totalForwards += flow.second.timesForwarded;
    }

    uint64_t lost = (totalTx >= totalRx) ? (totalTx - totalRx) : 0;
    double pdr = (totalTx > 0) ? (100.0 * static_cast<double>(totalRx) / totalTx) : 0.0;
    double avgDelay = (totalRx > 0) ? (totalDelaySum / totalRx) : 0.0;
    double avgJitter = (totalRx > 1) ? (totalJitterSum / static_cast<double>(totalRx - 1)) : 0.0;
    double measurementWindow = simTime - appStart;
    double throughputKbps =
        (measurementWindow > 0) ? (totalRxBytes * 8.0 / 1000.0 / measurementWindow) : 0.0;

    bool hopCountIsExact = (protocol == "static" || protocol == "sigmoid");
    double avgHopCount = hopCountIsExact
        ? avgHopCountExact
        : (totalRx > 0 ? (1.0 + static_cast<double>(totalForwards) / totalRx) : 0.0);
    std::string hopCountMethod = hopCountIsExact ? "exact" : "approx_timesForwarded";

    std::cout << "========================================\n"
              << "  Protocol   : " << protocol << "\n"
              << "  Traffic    : " << trafficCondition << " (" << dataRate << ")\n"
              << "  Sensors    : " << nRelayNodes << "\n"
              << "  Tx packets : " << totalTx << "\n"
              << "  Rx packets : " << totalRx << "\n"
              << "  Packet loss: " << lost << "\n"
              << "  PDR (%)    : " << pdr << "\n"
              << "  Throughput : " << throughputKbps << " kbps\n"
              << "  Avg delay  : " << avgDelay << " s\n"
              << "  Avg jitter : " << avgJitter << " s\n"
              << "  Hop count  : " << avgHopCount << " (" << hopCountMethod << ")\n"
              << "  Overhead   : " << overheadPackets << " control packets\n"
              << "========================================\n";

    mkdir(outDir.c_str(), 0755);
    std::string outFile = outDir + "/" + protocol + "_15_" + trafficCondition + ".csv";
    bool writeHeader = true;
    {
        std::ifstream existing(outFile);
        writeHeader = !existing.good();
    }
    std::ofstream out(outFile, std::ios::out | std::ios::app);
    if (writeHeader)
    {
        out << "protocol,seed,nodes,traffic_condition,data_rate,packets_sent,packets_received,"
               "packet_loss,pdr,throughput_kbps,delay_sec,jitter_sec,hop_count,hop_count_method,"
               "routing_overhead_packets,unreachable_sensors,sigmoid_k,sigmoid_x0,"
               "sigmoid_w_link_quality,sigmoid_w_load\n";
    }
    out << protocol << "," << posSeed << "," << (nRelayNodes + 2) << "," << trafficCondition << ","
        << dataRate << "," << totalTx << "," << totalRx << "," << lost << "," << pdr << ","
        << throughputKbps << "," << avgDelay << "," << avgJitter << "," << avgHopCount << ","
        << hopCountMethod << "," << overheadPackets << "," << unreachableSensors << ",";
    if (protocol == "sigmoid")
    {
        out << sigmoidK << "," << sigmoidX0 << "," << sigmoidWLinkQuality << "," << sigmoidWLoad;
    }
    else
    {
        out << ",,,"; // NA for non-sigmoid protocols -- not applicable, not zero
    }
    out << "\n";
    out.close();

    Simulator::Destroy();
    return 0;
}
