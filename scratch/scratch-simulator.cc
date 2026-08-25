#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include "ns3/applications-module.h"
#include "ns3/aodv-helper.h"
#include "ns3/olsr-helper.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/ipv4-global-routing-helper.h"

#include <vector>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <cstdlib>

using namespace ns3;

int main(int argc, char *argv[]) {
    std::string protocol = "static";
    uint32_t nNodes = 15;
    uint32_t m0 = 3;        // initial fully connected core
    uint32_t m  = 2;        // links added by each new node
    double simTime = 20.0;

    CommandLine cmd;
    cmd.AddValue("protocol", "static | aodv | olsr", protocol);
    cmd.AddValue("nNodes", "Number of nodes", nNodes);
    cmd.AddValue("m0", "Initial connected core size", m0);
    cmd.AddValue("m", "Links created per new node", m);
    cmd.AddValue("simTime", "Simulation time (s)", simTime);
    cmd.Parse(argc, argv);

    NS_ASSERT_MSG(nNodes > m0, "nNodes must be greater than m0");

    Time::SetResolution(Time::NS);

    // -----------------------------
    // Nodes
    // -----------------------------
    NodeContainer nodes;
    nodes.Create(nNodes);

    // -----------------------------
    // Link helper
    // -----------------------------
    PointToPointHelper p2p;
    p2p.SetDeviceAttribute("DataRate", StringValue("1Mbps"));
    p2p.SetChannelAttribute("Delay", StringValue("10ms"));

    // -----------------------------
    // Build BA topology
    // -----------------------------
    std::vector<std::pair<uint32_t, uint32_t>> edges;
    std::vector<uint32_t> degree(nNodes, 0);

    // 1) Initial complete graph among first m0 nodes
    for (uint32_t i = 0; i < m0; ++i) {
        for (uint32_t j = i + 1; j < m0; ++j) {
            edges.push_back({i, j});
            degree[i]++;
            degree[j]++;
        }
    }

    // 2) Add remaining nodes with preferential attachment
    Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();

    for (uint32_t newNode = m0; newNode < nNodes; ++newNode) {
        std::vector<uint32_t> chosen;

        while (chosen.size() < m) {
            uint32_t totalDegree = 0;
            for (uint32_t k = 0; k < newNode; ++k) {
                totalDegree += degree[k];
            }

            double r = uv->GetValue(0.0, totalDegree);
            double acc = 0.0;
            uint32_t selected = 0;

            for (uint32_t k = 0; k < newNode; ++k) {
                acc += degree[k];
                if (r <= acc) {
                    selected = k;
                    break;
                }
            }

            bool alreadyChosen = false;
            for (auto c : chosen) {
                if (c == selected) {
                    alreadyChosen = true;
                    break;
                }
            }

            if (!alreadyChosen) {
                chosen.push_back(selected);
                edges.push_back({newNode, selected});
                degree[newNode]++;
                degree[selected]++;
            }
        }
    }

    // -----------------------------
    // Install devices for each edge
    // -----------------------------
    std::vector<NetDeviceContainer> deviceList;
    for (auto &e : edges) {
        NodeContainer pair(nodes.Get(e.first), nodes.Get(e.second));
        deviceList.push_back(p2p.Install(pair));
    }

    // -----------------------------
    // Routing
    // -----------------------------
    InternetStackHelper stack;

    if (protocol == "aodv") {
        AodvHelper aodv;
        stack.SetRoutingHelper(aodv);
    }
    else if (protocol == "olsr") {
        OlsrHelper olsr;
        stack.SetRoutingHelper(olsr);
    }

    stack.Install(nodes);

    // -----------------------------
    // Assign IP subnets per link
    // two-octet allocation: 10.<hi>.<lo>.0/24, supports ~65k edges
    // -----------------------------
    Ipv4AddressHelper address;
    std::vector<Ipv4InterfaceContainer> interfaceList;

    for (uint32_t i = 0; i < deviceList.size(); ++i) {
        uint32_t hi = (i + 1) / 256;
        uint32_t lo = (i + 1) % 256;
        std::ostringstream subnet;
        subnet << "10." << hi << "." << lo << ".0";
        address.SetBase(subnet.str().c_str(), "255.255.255.0");
        interfaceList.push_back(address.Assign(deviceList[i]));
    }

    if (protocol == "static") {
        Ipv4GlobalRoutingHelper::PopulateRoutingTables();
    }

    // -----------------------------
    // Find IP of sink node (last node, tracks --nNodes)
    // -----------------------------
    uint32_t sinkNodeId = nNodes - 1;
    Ptr<Ipv4> ipv4Sink = nodes.Get(sinkNodeId)->GetObject<Ipv4>();
    Ipv4Address sinkAddr = Ipv4Address::GetZero();

    for (uint32_t i = 1; i < ipv4Sink->GetNInterfaces(); ++i) {
        for (uint32_t j = 0; j < ipv4Sink->GetNAddresses(i); ++j) {
            Ipv4InterfaceAddress ifAddr = ipv4Sink->GetAddress(i, j);
            if (ifAddr.GetLocal() != Ipv4Address("127.0.0.1")) {
                sinkAddr = ifAddr.GetLocal();
                break;
            }
        }
        if (sinkAddr != Ipv4Address::GetZero()) break;
    }
    NS_ASSERT_MSG(sinkAddr != Ipv4Address::GetZero(), "Could not resolve sink address");

    std::string protoUpper = protocol;
    for (auto &c : protoUpper) c = toupper(c);

    std::cout << "\n";
    std::cout << "========================================\n";
    std::cout << "  Protocol : " << protoUpper << "\n";
    std::cout << "  Sink     : Node " << sinkNodeId << " (" << sinkAddr << ")\n";
    std::cout << "========================================\n";

    // -----------------------------
    // Sink app at last node
    // -----------------------------
    uint16_t port = 9;
    PacketSinkHelper sink("ns3::UdpSocketFactory",
        InetSocketAddress(Ipv4Address::GetAny(), port));

    ApplicationContainer sinkApp = sink.Install(nodes.Get(sinkNodeId));
    sinkApp.Start(Seconds(0.0));
    sinkApp.Stop(Seconds(simTime));          // tied to simTime, matches client

    // -----------------------------
    // Source app at Node 0
    // -----------------------------
    OnOffHelper client("ns3::UdpSocketFactory",
        InetSocketAddress(sinkAddr, port));

    client.SetAttribute("DataRate", StringValue("1Mbps"));
    client.SetAttribute("PacketSize", UintegerValue(1024));

    double trafficStart = (protocol == "static") ? 1.0 : std::min(10.0, simTime * 0.3);
    ApplicationContainer clientApp = client.Install(nodes.Get(0));
    clientApp.Start(Seconds(trafficStart));
    clientApp.Stop(Seconds(simTime));        // tied to simTime, matches sink

    // -----------------------------
    // Flow monitor
    // -----------------------------
    FlowMonitorHelper flowmon;
    Ptr<FlowMonitor> monitor = flowmon.InstallAll();

    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    monitor->CheckForLostPackets();

    Ptr<Ipv4FlowClassifier> classifier =
        DynamicCast<Ipv4FlowClassifier>(flowmon.GetClassifier());

    auto stats = monitor->GetFlowStats();

    double avgDelay = 0.0;
    double throughput = 0.0;
    int count = 0;

    for (auto &flow : stats) {
        auto t = classifier->FindFlow(flow.first);

        if (t.destinationAddress == sinkAddr) {
            std::cout << "  Flow      : " << t.sourceAddress
                      << " -> " << t.destinationAddress << "\n";
            std::cout << "  Tx packets: " << flow.second.txPackets << "\n";
            std::cout << "  Rx packets: " << flow.second.rxPackets << "\n";

            if (flow.second.rxPackets > 0) {
                double delay =
                    flow.second.delaySum.GetSeconds() / flow.second.rxPackets;

                double duration = flow.second.timeLastRxPacket.GetSeconds() -
                                   flow.second.timeFirstTxPacket.GetSeconds();
                double thr = (duration > 0)
                                 ? (flow.second.rxBytes * 8.0 / duration / 1000.0)
                                 : 0.0;

                std::cout << "  Delay     : " << delay << " sec\n";
                std::cout << "  Throughput: " << thr << " Kbps\n";

                avgDelay += delay;
                throughput += thr;
                count++;
            }
            std::cout << "========================================\n";
        }
    }

    std::ofstream out("results.csv", std::ios::app);
    out << protocol << "," << nNodes << "," << m0 << "," << m << ","
        << (count > 0 ? avgDelay / count : 0.0) << ","
        << (count > 0 ? throughput / count : 0.0) << "\n";
    out.close();

    // -----------------------------
    // Export topology edges
    // -----------------------------
    std::ofstream topo("topology_edges.txt");
    for (auto &e : edges) {
        topo << e.first << " " << e.second << "\n";
    }
    topo.close();

    // -----------------------------
    // Generate topology image via Python/NetworkX
    // -----------------------------
    {
        std::ofstream py("plot_topology.py");
        py << "import networkx as nx\n"
           << "import matplotlib\n"
           << "matplotlib.use('Agg')\n"
           << "import matplotlib.pyplot as plt\n"
           << "import sys\n\n"
           << "protocol = sys.argv[1] if len(sys.argv) > 1 else 'unknown'\n\n"
           << "G = nx.Graph()\n"
           << "edges = []\n"
           << "with open('topology_edges.txt') as f:\n"
           << "    for line in f:\n"
           << "        a, b = map(int, line.split())\n"
           << "        edges.append((a, b))\n"
           << "G.add_edges_from(edges)\n\n"
           << "n = G.number_of_nodes()\n"
           << "sink = n - 1\n\n"
           << "color_map = []\n"
           << "for node in G.nodes():\n"
           << "    if node == 0:\n"
           << "        color_map.append('green')\n"
           << "    elif node == sink:\n"
           << "        color_map.append('red')\n"
           << "    else:\n"
           << "        color_map.append('skyblue')\n\n"
           << "sizes = [300 + 150 * G.degree(n) for n in G.nodes()]\n\n"
           << "pos = nx.spring_layout(G, seed=42)\n\n"
           << "plt.figure(figsize=(10, 8))\n"
           << "nx.draw_networkx_edges(G, pos, alpha=0.5, width=1.2)\n"
           << "nx.draw_networkx_nodes(G, pos, node_color=color_map,\n"
           << "                       node_size=sizes, alpha=0.9)\n"
           << "nx.draw_networkx_labels(G, pos, font_size=10, font_weight='bold')\n\n"
           << "for node in G.nodes():\n"
           << "    x, y = pos[node]\n"
           << "    plt.text(x, y - 0.08, f'deg={G.degree(node)}',\n"
           << "             ha='center', va='top', fontsize=7, color='dimgray')\n\n"
           << "from matplotlib.patches import Patch\n"
           << "legend = [\n"
           << "    Patch(color='green',  label='Sensor Node (Node 0)'),\n"
           << "    Patch(color='red',    label=f'CPS Server (Node {sink})'),\n"
           << "    Patch(color='skyblue',label='Gateway Mesh Nodes'),\n"
           << "]\n"
           << "plt.legend(handles=legend, loc='upper right', fontsize=9)\n\n"
           << "plt.title(f'NS-3 IoT/CPS Topology — {n} nodes | Protocol: {protocol}',\n"
           << "          fontsize=13, fontweight='bold')\n"
           << "plt.axis('off')\n"
           << "plt.tight_layout()\n\n"
           << "fname = f'topology_{protocol}.png'\n"
           << "plt.savefig(fname, dpi=150)\n"
           << "print(f'Topology image saved: {fname}')\n";
        py.close();

        std::string plotCmd = "python3 plot_topology.py " + protocol;
        int ret = std::system(plotCmd.c_str());
        if (ret != 0) {
            std::cerr << "Warning: plot_topology.py failed (is matplotlib/networkx installed?)\n";
        }
    }

    Simulator::Destroy();
    return 0;
}
