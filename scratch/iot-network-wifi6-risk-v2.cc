/*
 * iot-network-wifi6-risk-v2.cc  --  risk-v2 (2026-10-21). Copy of scratch/iot-network-wifi6-risk.cc (risk-v1, never
 * edited) + one fix, --baSsnFix (default true; false = identical to risk-v1).
 *
 * Problem fixed (confirmed by trace, results/wifi6-risk/diag-delay-20261021/): ns-3 sets up a Block Ack agreement
 * for every VHT/HE pair (ht-frame-exchange-manager.cc:131-136, regardless of A-MPDU size). The ADDBA Request
 * advertises SSN = sequence number of the first queued MPDU. If that MPDU is discarded (retry limit) while the
 * handshake is in NO_REPLY state, QosTxop::GotAddBaResponse (qos-txop.cc:700-707) starts the ORIGINATOR window at
 * the next sequence number, while the RECIPIENT starts its reorder window at the advertised SSN. No BlockAckReq is
 * sent, so the recipient buffers every later MPDU until one arrives with SN >= SSN + buffer size (256 for HE):
 * at 16 kbps (3.9 pkt/s) about 65 s of delay.
 * Fix: record the SSN of each ADDBA Request a node transmits; when that node's originator agreement becomes
 * ESTABLISHED with a starting sequence different from the advertised SSN, schedule (ScheduleNow, after the state
 * change completes) a BlockAckReq carrying the originator's starting sequence -- the 802.11 mechanism that moves
 * the recipient's window (QosTxop::PrepareBlockAckRequest + BlockAckManager::ScheduleBar, public ns-3 API).
 * Counted in ba_ssn_fix.csv. Original header follows.
 * iot-network-wifi6-risk.cc  --  risk-v1 (2026-10-21). Copy of scratch/iot-network-wifi-std-uid.cc (never
 * edited), which is iot-network-wifi-std-arp.cc + --uidAccounting. One master flag is added: --riskStudy
 * (default false). With --riskStudy=0 nothing new is connected, installed or written, so every output is
 * identical to iot-network-wifi-std-uid.cc / iot-network-wifi-std-arp.cc for the same arguments.
 *
 * With --riskStudy=1:
 *   Node risk states. Every sensor is LOW_RISK or HIGH_RISK; the gateway is never risky. Each state has a
 *     forwarding-loss probability (--lowRiskDropProb, default 0; --highRiskDropProb, default 0.5), which is
 *     also the node's risk score r_i used by risk-aware routing. ASSUMPTION (pending advisor approval):
 *     risk acts only on TRANSIT application data (UDP to the gateway's sink port that the node forwards);
 *     a node's own packets and all control/ARP/broadcast frames are never affected.
 *   High-risk assignment (deterministic, independent of --protocol): --numHighRisk = 0..3 relays chosen
 *     from the reachable sensors that relay for >= 1 other sensor in the BFS (hop-count) tree on the
 *     --txRange disk graph. --riskSelect = subtree (most BFS descendants, then degree, then lower id;
 *     default) | degree (degree, then descendants, then id) | random (SplitMix64(--riskSelectSeed, id),
 *     then id) | ids (--highRiskIds=a,b,c, validated). Sets are nested: k=1 is a subset of k=2 of k=3.
 *   Risk drop: RiskDropFilter (an Ipv4RoutingProtocol at list priority 1000, only on nodes with p > 0)
 *     consumes an eligible transit data packet iff U < p, U = SplitMix64-hash(--riskDropSeed, node, src,
 *     seq) in [0,1), where (src, seq) is the application's own packet number (recorded at the OnOff Tx
 *     trace, before the packet can reach any relay). No ns-3 random stream is used, and the same logical
 *     packet gets the same decision at the same node under every routing protocol.
 *   --protocol=riskaware: a NEW, separately named routing mode. aodv / olsr / static are unchanged.
 *     Offline Dijkstra tree toward the gateway on the same disk graph as static; entering transit node v
 *     costs 1 + riskBeta * tau_v, tau_v = -ln(1 - r_v) (tau_gateway = 0); installed as Ipv4StaticRouting
 *     host routes before traffic, like static. Ties are broken so that with all r_v = 0 the tree is
 *     exactly static's BFS tree (priority queue keyed by (cost, order of first assignment)).
 *     Routing has perfect knowledge of the risk states (an upper bound on the benefit).
 *   Path traces (read-only Ipv4L3Protocol UnicastForward / PacketSink Rx sinks) and new outputs:
 *     risk_nodes.csv, routes_planned.csv, path_summary.csv, risk_drops.csv, risk_summary.csv,
 *     wifi_readback.csv (Wi-Fi settings read back from every device), wifi_txvector_counts.csv (TXVECTORs
 *     of transmitted PSDUs), and with --perPacketTrace=1 packet_paths.csv (one row per data packet).
 *   With --uidAccounting=1 a risk drop is a terminal fate of its own (drop_risk).
 * Mobility: static only (inherited). Original header follows.
 * iot-network-wifi-std-uid.cc  --  copy of scratch/iot-network-wifi-std-arp.cc (never edited) + per-packet (UID)
 * loss accounting (2026-10-21). Only addition: --uidAccounting (default false).
 *   Off: no extra trace sink is connected and no extra file is written -> identical to iot-network-wifi-std-arp.cc.
 *   On : read-only trace sinks (no RNG, no Simulator::Schedule, no change to any packet or object) follow every
 *        application data packet by its Packet UID and write uid_summary.csv and uid_pernode/*.csv. All other
 *        outputs are unchanged.
 *   Population: UIDs reported by the sensors' OnOffApplication "Tx" trace. Because that trace fires after
 *        Socket::Send() returns, a packet is first recognised at Ipv4L3Protocol Tx/Drop from its headers
 *        (UDP, destination = gateway address, destination port = sink port); only UIDs later confirmed by
 *        the application Tx trace are counted. OLSR/AODV control, ARP and broadcast frames are never counted.
 *   Fate of each UID, in this order: delivered (PacketSink Rx; extra receptions counted as duplicates) >
 *        dropped (the FIRST drop event, by kind and node) > pending at the end (ARP pending, queue disc,
 *        MAC queue incl. MPDUs awaiting ACK, in flight) > unaccounted (last stage recorded). Conflicts
 *        (delivered and dropped; more than one drop event; drop at a node that no longer holds the packet)
 *        are counted separately. Nothing is forced to close the account.
 *   Pending is inferred from the last stage of the node currently holding the packet (Ipv4 Tx -> ARP; queue disc
 *        Enqueue/Requeue; MAC queue Enqueue), because ArpCache has no read-only accessor for its pending queue.
 *   The default FqCoDel queue disc that Ipv4AddressHelper::Assign installs on the Wi-Fi device
 *        (ipv4-address-helper.cc:155-174) is followed as well (Enqueue/Dequeue/Requeue/DropBeforeEnqueue/
 *        DropAfterDequeue) together with TrafficControlLayer TcDrop.
 * Original header follows.
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
#include "ns3/traffic-control-module.h"
#include "ns3/udp-header.h"

#include <fstream>
#include <sstream>
#include <queue>
#include <random>
#include <map>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <iomanip>
#include <limits>
#include <array>
#include <tuple>
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

// ------------------------------------------------------------------ per-UID accounting (--uidAccounting)
// Every sink below only reads its arguments and writes to g_uid*; none uses an RNG, schedules an event or
// modifies a packet (header parsing is done on a private copy).
enum UidDropKind : int8_t
{
    UD_MACQ_BEFORE_ENQ, UD_MACQ_AFTER_DEQ, UD_MPDU_FAILED_ENQ, UD_MPDU_EXPIRED, UD_MPDU_RETRY, UD_MPDU_QOS_OLD,
    UD_IP_NO_ROUTE, UD_IP_TTL, UD_IP_ROUTE_ERR, UD_IP_OTHER, UD_ARP_L3, UD_ARP_CACHE, UD_QDISC_BEFORE_ENQ,
    UD_QDISC_AFTER_DEQ, UD_TC_DROP, UD_RISK, UD_N
};
static const char* kUidDropName[UD_N] = {
    "drop_macq_before_enqueue", "drop_macq_after_dequeue", "drop_mpdu_failed_enqueue", "drop_mpdu_expired_lifetime",
    "drop_mpdu_retry_limit", "drop_mpdu_qos_old", "drop_ip_no_route", "drop_ip_ttl", "drop_ip_route_error",
    "drop_ip_other", "drop_arp_l3", "drop_arp_cache", "drop_qdisc_before_enqueue", "drop_qdisc_after_dequeue",
    "drop_tc", "drop_risk"};
enum UidStage : uint8_t
{
    US_NONE, US_IP_TX, US_LOOPBACK, US_QDISC, US_DEV_HANDOFF, US_MACQ, US_SENT, US_IP_RX
};
struct UidRec
{
    int32_t src = -1;           // set by the application Tx trace (confirms the UID as application data)
    uint32_t rx = 0;            // PacketSink receptions
    int8_t firstDrop = -1;
    int32_t firstDropNode = -1;
    uint32_t dropEvents = 0;    // distinct (node, time) drop events
    int32_t lastDropNode = -1;
    int64_t lastDropTs = -1;
    bool dropAtNonHolder = false;
    int32_t holder = -1;        // node that currently holds the packet
    uint8_t stage = US_NONE;
    int64_t lastTs = 0;         // time (ns) of the last stage change
};
static bool g_uidOn = false;
static std::unordered_map<uint64_t, UidRec> g_uid;
static Ipv4Address g_uidGw;
static uint16_t g_uidPort = 0;
static uint32_t g_uidPayload = 0;        // application payload bytes
static uint64_t g_uidSinkUnknown = 0;    // sink receptions of a UID never seen as data (expected 0)

static bool UidIsDataHeader(const Ipv4Header& h)
{
    return h.GetProtocol() == UdpL4Protocol::PROT_NUMBER && h.GetDestination() == g_uidGw &&
           h.GetPayloadSize() == g_uidPayload + 8;
}
static bool UidUdpPortIsSink(Ptr<const Packet> udpFirst)
{
    if (udpFirst->GetSize() < 8) return false;
    UdpHeader u;
    udpFirst->PeekHeader(u);
    return u.GetDestinationPort() == g_uidPort;
}
static UidRec* UidFind(uint64_t uid)
{
    auto it = g_uid.find(uid);
    return it == g_uid.end() ? nullptr : &it->second;
}
static void UidStageAt(UidRec* r, uint32_t node, uint8_t stage, bool takeHolder)
{
    if (takeHolder) r->holder = static_cast<int32_t>(node);
    else if (r->holder != static_cast<int32_t>(node)) return;   // a previous hop finishing its copy
    r->stage = stage;
    r->lastTs = Simulator::Now().GetNanoSeconds();
}
static void UidDrop(UidRec* r, uint32_t node, int8_t kind)
{
    const int64_t ts = Simulator::Now().GetNanoSeconds();
    if (r->lastDropNode == static_cast<int32_t>(node) && r->lastDropTs == ts) return;  // same event, 2nd trace
    r->lastDropNode = static_cast<int32_t>(node);
    r->lastDropTs = ts;
    r->dropEvents++;
    if (r->holder >= 0 && r->holder != static_cast<int32_t>(node)) r->dropAtNonHolder = true;
    if (r->firstDrop < 0) { r->firstDrop = kind; r->firstDropNode = static_cast<int32_t>(node); }
}
static void OnUidIpTx(uint32_t node, Ptr<const Packet> p, Ptr<Ipv4> /*ipv4*/, uint32_t iface)
{
    UidRec* r = UidFind(p->GetUid());
    if (!r)
    {
        Ptr<Packet> c = p->Copy();
        Ipv4Header h;
        c->RemoveHeader(h);
        if (!UidIsDataHeader(h) || !UidUdpPortIsSink(c)) return;
        r = &g_uid[p->GetUid()];
    }
    UidStageAt(r, node, iface == 0 ? US_LOOPBACK : US_IP_TX, true);
}
static void OnUidIpRx(uint32_t node, Ptr<const Packet> p, Ptr<Ipv4> /*ipv4*/, uint32_t iface)
{
    if (UidRec* r = UidFind(p->GetUid())) UidStageAt(r, node, iface == 0 ? US_LOOPBACK : US_IP_RX, true);
}
static void OnUidIpDrop(uint32_t node, const Ipv4Header& h, Ptr<const Packet> p, Ipv4L3Protocol::DropReason reason,
                        Ptr<Ipv4> /*ipv4*/, uint32_t /*iface*/)
{
    UidRec* r = UidFind(p->GetUid());
    if (!r)
    {
        if (!UidIsDataHeader(h)) return;
        Ptr<Packet> c = p->Copy();
        if (c->GetSize() == g_uidPayload + 8 + h.GetSerializedSize())   // packet still carries the IP header
        {
            Ipv4Header inner;
            c->RemoveHeader(inner);
        }
        if (c->GetSize() != g_uidPayload + 8 || !UidUdpPortIsSink(c)) return;
        r = &g_uid[p->GetUid()];
        r->holder = static_cast<int32_t>(node);
    }
    int8_t k = reason == Ipv4L3Protocol::DROP_NO_ROUTE      ? UD_IP_NO_ROUTE
               : reason == Ipv4L3Protocol::DROP_TTL_EXPIRED ? UD_IP_TTL
               : reason == Ipv4L3Protocol::DROP_ROUTE_ERROR ? UD_IP_ROUTE_ERR
                                                            : UD_IP_OTHER;
    UidDrop(r, node, k);
}
static void OnUidArpL3Drop(uint32_t node, Ptr<const Packet> p)
{
    if (UidRec* r = UidFind(p->GetUid())) UidDrop(r, node, UD_ARP_L3);
}
static void OnUidArpCacheDrop(uint32_t node, Ptr<const Packet> p)
{
    if (UidRec* r = UidFind(p->GetUid())) UidDrop(r, node, UD_ARP_CACHE);
}
static void OnUidQdiscEnq(uint32_t node, Ptr<const QueueDiscItem> it)
{
    if (UidRec* r = UidFind(it->GetPacket()->GetUid())) UidStageAt(r, node, US_QDISC, false);
}
static void OnUidQdiscDeq(uint32_t node, Ptr<const QueueDiscItem> it)
{
    if (UidRec* r = UidFind(it->GetPacket()->GetUid())) UidStageAt(r, node, US_DEV_HANDOFF, false);
}
static void OnUidQdiscDropBefore(uint32_t node, Ptr<const QueueDiscItem> it, const char* /*why*/)
{
    if (UidRec* r = UidFind(it->GetPacket()->GetUid())) UidDrop(r, node, UD_QDISC_BEFORE_ENQ);
}
static void OnUidQdiscDropAfter(uint32_t node, Ptr<const QueueDiscItem> it, const char* /*why*/)
{
    if (UidRec* r = UidFind(it->GetPacket()->GetUid())) UidDrop(r, node, UD_QDISC_AFTER_DEQ);
}
static void OnUidTcDrop(uint32_t node, Ptr<const Packet> p)
{
    if (UidRec* r = UidFind(p->GetUid())) UidDrop(r, node, UD_TC_DROP);
}
static void OnUidMacEnq(uint32_t node, Ptr<const WifiMpdu> m)
{
    if (UidRec* r = UidFind(m->GetPacket()->GetUid())) UidStageAt(r, node, US_MACQ, false);
}
static void OnUidMacDeq(uint32_t node, Ptr<const WifiMpdu> m)
{
    if (UidRec* r = UidFind(m->GetPacket()->GetUid())) UidStageAt(r, node, US_SENT, false);
}
static void OnUidMacDropBefore(uint32_t node, Ptr<const WifiMpdu> m)
{
    if (UidRec* r = UidFind(m->GetPacket()->GetUid())) UidDrop(r, node, UD_MACQ_BEFORE_ENQ);
}
static void OnUidMacDropAfter(uint32_t node, Ptr<const WifiMpdu> m)
{
    if (UidRec* r = UidFind(m->GetPacket()->GetUid())) UidDrop(r, node, UD_MACQ_AFTER_DEQ);
}
static void OnUidDroppedMpdu(uint32_t node, WifiMacDropReason reason, Ptr<const WifiMpdu> m)
{
    if (static_cast<uint8_t>(reason) >= 4) return;
    if (UidRec* r = UidFind(m->GetPacket()->GetUid()))
        UidDrop(r, node, static_cast<int8_t>(UD_MPDU_FAILED_ENQ + static_cast<uint8_t>(reason)));
}
static void OnUidAppTx(uint32_t node, Ptr<const Packet> p)
{
    // Socket::Send() has already run synchronously, so the record normally exists; create it otherwise.
    UidRec& r = g_uid[p->GetUid()];
    r.src = static_cast<int32_t>(node);
}
static void OnUidSinkRx(Ptr<const Packet> p, const Address& /*from*/)
{
    if (UidRec* r = UidFind(p->GetUid())) r->rx++;
    else ++g_uidSinkUnknown;
}


// ------------------------------------------------------------------ risk study (--riskStudy)
enum RiskState : uint8_t
{
    LOW_RISK = 0,
    HIGH_RISK = 1
};
static bool g_riskOn = false;
static std::vector<uint8_t> g_riskState;        // per node (gateway: LOW_RISK, never selectable)
static std::vector<double> g_riskP;             // per node forwarding-loss probability = risk score r_i
static uint64_t g_riskDropSeed = 1;
static Ipv4Address g_riskGw;
static uint16_t g_riskPort = 0;
struct AppKey
{
    uint32_t src;
    uint32_t seq;
};
static std::unordered_map<uint64_t, AppKey> g_appKey;   // packet UID -> (source sensor, application seq)
static std::vector<uint32_t> g_appSeq;                  // next seq per sensor
struct PathRec
{
    uint32_t src = 0;
    uint32_t seq = 0;
    int64_t txNs = 0;
    std::vector<uint32_t> relays;   // nodes that forwarded (or risk-dropped) the packet, in order
    uint32_t rx = 0;                // PacketSink receptions
    int64_t rxNs = -1;              // time of the first PacketSink reception
    int32_t riskDropNode = -1;
};
static std::unordered_map<uint64_t, PathRec> g_path;
struct RiskDropRec
{
    uint32_t node, src, seq;
    uint64_t uid;
    int64_t ns;
    double u;
};
static std::vector<RiskDropRec> g_riskDropLog;
static std::vector<uint64_t> g_riskEligible, g_riskDropped, g_riskPassed;
static uint64_t g_riskKeyMissing = 0, g_riskLocalSource = 0;
static std::map<std::string, uint64_t> g_txvCounts;

static uint64_t SplitMix64(uint64_t x)
{
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}
static double RiskUniform(uint64_t seed, uint32_t node, uint32_t src, uint32_t seq)
{
    uint64_t h = SplitMix64(SplitMix64(SplitMix64(SplitMix64(seed) ^ node) ^ src) ^ seq);
    return static_cast<double>(h >> 11) * (1.0 / 9007199254740992.0);   // 2^-53
}

// Consumes an eligible transit data packet with probability p. Ipv4ListRouting delivers packets addressed
// to this node before asking any child protocol (ipv4-list-routing.cc), and a node's own packets use
// RouteOutput, so RouteInput sees transit packets only; own-source packets are excluded explicitly too.
class RiskDropFilter : public Ipv4RoutingProtocol
{
  public:
    static TypeId GetTypeId()
    {
        static TypeId tid =
            TypeId("ns3::IotWifi6RiskDropFilter").SetParent<Ipv4RoutingProtocol>().SetGroupName("Internet");
        return tid;
    }
    void Configure(uint32_t node, double p)
    {
        m_node = node;
        m_p = p;
    }
    bool RouteInput(Ptr<const Packet> p, const Ipv4Header& h, Ptr<const NetDevice> /*idev*/,
                    const UnicastForwardCallback& /*ucb*/, const MulticastForwardCallback& /*mcb*/,
                    const LocalDeliverCallback& /*lcb*/, const ErrorCallback& /*ecb*/) override
    {
        if (h.GetDestination() != g_riskGw || h.GetProtocol() != UdpL4Protocol::PROT_NUMBER) return false;
        if (p->GetSize() < 8) return false;
        UdpHeader u;
        p->PeekHeader(u);
        if (u.GetDestinationPort() != g_riskPort) return false;
        if (m_ipv4->GetInterfaceForAddress(h.GetSource()) >= 0) { ++g_riskLocalSource; return false; }
        auto it = g_appKey.find(p->GetUid());
        if (it == g_appKey.end()) { ++g_riskKeyMissing; return false; }
        ++g_riskEligible[m_node];
        const double x = RiskUniform(g_riskDropSeed, m_node, it->second.src, it->second.seq);
        if (x < m_p)
        {
            ++g_riskDropped[m_node];
            g_riskDropLog.push_back({m_node, it->second.src, it->second.seq, p->GetUid(),
                                     Simulator::Now().GetNanoSeconds(), x});
            auto pr = g_path.find(p->GetUid());
            if (pr != g_path.end())
            {
                pr->second.relays.push_back(m_node);
                if (pr->second.riskDropNode < 0) pr->second.riskDropNode = static_cast<int32_t>(m_node);
            }
            if (g_uidOn)
                if (UidRec* r = UidFind(p->GetUid())) UidDrop(r, m_node, UD_RISK);
            return true;   // consumed: no callback, no further routing protocol
        }
        ++g_riskPassed[m_node];
        return false;
    }
    Ptr<Ipv4Route> RouteOutput(Ptr<Packet>, const Ipv4Header&, Ptr<NetDevice>, Socket::SocketErrno& e) override
    {
        e = Socket::ERROR_NOROUTETOHOST;
        return nullptr;
    }
    void NotifyInterfaceUp(uint32_t) override {}
    void NotifyInterfaceDown(uint32_t) override {}
    void NotifyAddAddress(uint32_t, Ipv4InterfaceAddress) override {}
    void NotifyRemoveAddress(uint32_t, Ipv4InterfaceAddress) override {}
    void SetIpv4(Ptr<Ipv4> ipv4) override { m_ipv4 = ipv4; }
    void PrintRoutingTable(Ptr<OutputStreamWrapper> s, Time::Unit) const override
    {
        *s->GetStream() << "RiskDropFilter node " << m_node << " p=" << m_p << "\n";
    }

  private:
    Ptr<Ipv4> m_ipv4;
    uint32_t m_node = 0;
    double m_p = 0.0;
};

static void OnRiskAppTx(uint32_t node, Ptr<const Packet> p)
{
    const uint32_t seq = g_appSeq[node]++;
    g_appKey[p->GetUid()] = {node, seq};
    PathRec& r = g_path[p->GetUid()];
    r.src = node;
    r.seq = seq;
    r.txNs = Simulator::Now().GetNanoSeconds();
}
static void OnRiskForward(uint32_t node, const Ipv4Header& /*h*/, Ptr<const Packet> p, uint32_t /*iface*/)
{
    auto it = g_path.find(p->GetUid());
    if (it == g_path.end() || it->second.src == node) return;   // not app data, or AODV deferred send at source
    it->second.relays.push_back(node);
}
static void OnRiskSinkRx(Ptr<const Packet> p, const Address& /*from*/)
{
    auto it = g_path.find(p->GetUid());
    if (it != g_path.end())
    {
        if (it->second.rx++ == 0) it->second.rxNs = Simulator::Now().GetNanoSeconds();
    }
}
static void OnRiskPsdu(uint32_t /*node*/, WifiConstPsduMap psdus, WifiTxVector txv, double /*w*/)
{
    for (const auto& kv : psdus)
    {
        const WifiMacHeader& mh = kv.second->GetHeader(0);
        const char* cls = mh.IsData() ? (mh.GetAddr1().IsGroup() ? "data_group" : "data_unicast")
                          : mh.IsCtl() ? "ctl" : mh.IsMgt() ? "mgt" : "other";
        std::ostringstream k;
        k << cls << "," << mh.GetTypeString() << "," << txv.GetPreambleType() << "," << txv.GetModulationClass() << ","
          << txv.GetMode(kv.first).GetUniqueName() << "," << txv.GetChannelWidth() << ","
          << (txv.GetModulationClass() >= WIFI_MOD_CLASS_HT ? std::to_string(txv.GetGuardInterval().GetNanoSeconds())
                                                            : std::string("NA"));
        g_txvCounts[k.str()]++;
    }
}


// ------------------------------------------------------------------ Block Ack SSN fix (--baSsnFix)
static std::map<std::tuple<uint32_t, Mac48Address, uint8_t>, uint16_t> g_addbaSsn;   // (node, recipient, tid) -> SSN
struct BaFixRec
{
    int64_t ns;
    uint32_t node;
    Mac48Address recipient;
    uint8_t tid;
    uint16_t advertised, originatorStart;
};
static std::vector<BaFixRec> g_baFixLog;
static std::vector<Ptr<WifiMac>> g_baFixMac;
static void OnBaFixPsdu(uint32_t node, WifiConstPsduMap psdus, WifiTxVector, double)
{
    for (const auto& kv : psdus)
        for (const auto& m : *kv.second)
        {
            if (!m->GetHeader().IsAction()) continue;
            Ptr<Packet> c = m->GetPacket()->Copy();
            WifiActionHeader act;
            c->RemoveHeader(act);
            if (act.GetCategory() != WifiActionHeader::BLOCK_ACK ||
                act.GetAction().blockAck != WifiActionHeader::BLOCK_ACK_ADDBA_REQUEST)
                continue;
            MgtAddBaRequestHeader req;
            c->RemoveHeader(req);
            g_addbaSsn[{node, m->GetHeader().GetAddr1(), req.GetTid()}] = req.GetStartingSequence();
        }
}
static void BaFixSendBar(uint32_t node, uint8_t ac, Mac48Address rec, uint8_t tid)
{
    Ptr<QosTxop> txop = g_baFixMac[node]->GetQosTxop(static_cast<AcIndex>(ac));
    auto agr = txop->GetBaManager()->GetAgreementAsOriginator(rec, tid);
    if (!agr || !agr->get().IsEstablished()) return;
    auto [reqHdr, hdr] = txop->PrepareBlockAckRequest(rec, tid);
    const bool had = txop->HasFramesToTransmit(0);
    txop->GetBaManager()->ScheduleBar(reqHdr, hdr);
    txop->StartAccessAfterEvent(0, had, Txop::CHECK_MEDIUM_BUSY);
}
static void OnBaFixState(uint32_t node, uint8_t ac, Time, Mac48Address rec, uint8_t tid, OriginatorBlockAckAgreement::State s)
{
    if (s != OriginatorBlockAckAgreement::ESTABLISHED) return;
    auto it = g_addbaSsn.find({node, rec, tid});
    if (it == g_addbaSsn.end()) return;
    auto agr = g_baFixMac[node]->GetQosTxop(static_cast<AcIndex>(ac))->GetBaManager()->GetAgreementAsOriginator(rec, tid);
    if (!agr) return;
    const uint16_t start = agr->get().GetStartingSequence();   // already set (block-ack-manager.cc UpdateOriginatorAgreement)
    if (start == it->second) return;
    g_baFixLog.push_back({Simulator::Now().GetNanoSeconds(), node, rec, tid, it->second, start});
    Simulator::ScheduleNow(&BaFixSendBar, node, ac, rec, tid);
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
    bool uidAccounting = false;
    cmd.AddValue("uidAccounting", "per-packet (UID) loss accounting, read-only trace sinks; default false", uidAccounting);
    bool riskStudy = false;
    uint32_t numHighRisk = 0;
    std::string riskSelect = "subtree";
    std::string highRiskIds = "";
    uint64_t riskSelectSeed = 1;
    double highRiskDropProb = 0.5;
    double lowRiskDropProb = 0.0;
    double riskBeta = 10.0;
    uint64_t riskDropSeed = 1;
    bool perPacketTrace = false;
    bool baSsnFix = true;
    cmd.AddValue("baSsnFix", "risk-v2: send a BlockAckReq when an agreement is established with a starting sequence "
                 "different from the advertised ADDBA SSN (QoS standards only); default true", baSsnFix);
    cmd.AddValue("riskStudy", "risk-v1: node risk states, riskaware routing, path traces; default false", riskStudy);
    cmd.AddValue("numHighRisk", "riskStudy: number of HIGH_RISK relay nodes (0..3)", numHighRisk);
    cmd.AddValue("riskSelect", "riskStudy: subtree | degree | random | ids", riskSelect);
    cmd.AddValue("highRiskIds", "riskStudy, riskSelect=ids: comma-separated sensor ids", highRiskIds);
    cmd.AddValue("riskSelectSeed", "riskStudy, riskSelect=random: hash seed", riskSelectSeed);
    cmd.AddValue("highRiskDropProb", "riskStudy: transit-data loss probability (risk score) of HIGH_RISK nodes", highRiskDropProb);
    cmd.AddValue("lowRiskDropProb", "riskStudy: transit-data loss probability (risk score) of LOW_RISK nodes", lowRiskDropProb);
    cmd.AddValue("riskBeta", "riskaware: hops charged per unit of -ln(1-r) at a transit node", riskBeta);
    cmd.AddValue("riskDropSeed", "riskStudy: hash seed of the risk-drop decisions", riskDropSeed);
    cmd.AddValue("perPacketTrace", "riskStudy: also write packet_paths.csv (one row per data packet)", perPacketTrace);
    cmd.Parse(argc, argv);

    if (protocol != "aodv" && protocol != "olsr" && protocol != "static" && protocol != "riskaware")
        NS_FATAL_ERROR("--protocol must be aodv|olsr|static|riskaware (got '" << protocol << "')");
    NS_ABORT_MSG_IF(protocol == "riskaware" && !riskStudy, "--protocol=riskaware needs --riskStudy=1");
    NS_ABORT_MSG_IF(!riskStudy && (numHighRisk != 0 || perPacketTrace), "--numHighRisk/--perPacketTrace need --riskStudy=1");
    NS_ABORT_MSG_IF(numHighRisk > 3, "--numHighRisk must be 0..3");
    NS_ABORT_MSG_IF(riskSelect != "subtree" && riskSelect != "degree" && riskSelect != "random" && riskSelect != "ids",
                    "--riskSelect must be subtree|degree|random|ids");
    NS_ABORT_MSG_IF(!(highRiskDropProb >= 0.0 && highRiskDropProb < 1.0) || !(lowRiskDropProb >= 0.0 && lowRiskDropProb < 1.0),
                    "--highRiskDropProb/--lowRiskDropProb must be in [0, 1)");
    NS_ABORT_MSG_IF(lowRiskDropProb > highRiskDropProb, "--lowRiskDropProb must not exceed --highRiskDropProb");
    NS_ABORT_MSG_IF(!(riskBeta >= 0.0), "--riskBeta must be >= 0");
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


    // ---- risk study: state assignment and the riskaware routing tree (only with --riskStudy) ----
    std::vector<uint32_t> degree(n, 0), descendants(n, 0), highIds;
    std::vector<int64_t> raParent(n, -1);
    std::vector<double> raDist(n, std::numeric_limits<double>::infinity()), tau(n, 0.0);
    std::vector<int32_t> highRank(n, -1);
    std::vector<uint32_t> ranking;      // candidate relays in selection order
    if (riskStudy)
    {
        g_riskOn = true;
        g_riskGw = gatewayAddr;
        for (uint32_t i = 0; i < n; ++i) degree[i] = static_cast<uint32_t>(adj[i].size());
        for (uint32_t i = 0; i < nSensors; ++i)
            for (int64_t a = parent[i]; a >= 0 && a != static_cast<int64_t>(gatewayIndex); a = parent[a])
                descendants[a]++;
        std::vector<uint32_t> cand;
        for (uint32_t i = 0; i < nSensors; ++i)
            if (hop[i] >= 1 && descendants[i] >= 1) cand.push_back(i);
        if (riskSelect == "ids")
        {
            std::istringstream ss(highRiskIds);
            std::string tok;
            while (std::getline(ss, tok, ','))
            {
                if (tok.empty()) continue;
                uint32_t id = static_cast<uint32_t>(std::stoul(tok));
                NS_ABORT_MSG_IF(id >= nSensors, "--highRiskIds: " << id << " is not a sensor id");
                NS_ABORT_MSG_IF(std::find(ranking.begin(), ranking.end(), id) != ranking.end(),
                                "--highRiskIds: duplicate id " << id);
                ranking.push_back(id);
            }
            NS_ABORT_MSG_IF(ranking.size() != numHighRisk, "--highRiskIds must list exactly --numHighRisk ids");
        }
        else
        {
            ranking = cand;
            auto key = [&](uint32_t i) {
                if (riskSelect == "subtree") return std::make_tuple(-static_cast<int64_t>(descendants[i]),
                                                                     -static_cast<int64_t>(degree[i]), uint64_t(0), i);
                if (riskSelect == "degree") return std::make_tuple(-static_cast<int64_t>(degree[i]),
                                                                    -static_cast<int64_t>(descendants[i]), uint64_t(0), i);
                return std::make_tuple(int64_t(0), int64_t(0), SplitMix64(SplitMix64(riskSelectSeed) ^ i), i);
            };
            std::sort(ranking.begin(), ranking.end(), [&](uint32_t a, uint32_t b) { return key(a) < key(b); });
            NS_ABORT_MSG_IF(ranking.size() < numHighRisk,
                            "only " << ranking.size() << " relay candidates for --numHighRisk=" << numHighRisk);
        }
        g_riskState.assign(n, LOW_RISK);
        g_riskP.assign(n, 0.0);
        for (uint32_t i = 0; i < nSensors; ++i) g_riskP[i] = lowRiskDropProb;
        for (uint32_t k = 0; k < numHighRisk; ++k)
        {
            g_riskState[ranking[k]] = HIGH_RISK;
            g_riskP[ranking[k]] = highRiskDropProb;
            highRank[ranking[k]] = static_cast<int32_t>(k + 1);
            highIds.push_back(ranking[k]);
        }
        for (uint32_t i = 0; i < nSensors; ++i) tau[i] = -std::log1p(-g_riskP[i]);

        // riskaware tree: Dijkstra from the gateway; key (cost, order of assignment) reproduces BFS on ties.
        using QE = std::tuple<double, uint64_t, uint32_t>;
        std::priority_queue<QE, std::vector<QE>, std::greater<QE>> pq;
        std::vector<bool> done(n, false);
        uint64_t order = 0;
        raDist[gatewayIndex] = 0.0;
        pq.emplace(0.0, order++, gatewayIndex);
        while (!pq.empty())
        {
            auto [d, o, v] = pq.top();
            pq.pop();
            if (done[v]) continue;
            done[v] = true;
            const double w = 1.0 + riskBeta * (v == gatewayIndex ? 0.0 : tau[v]);
            for (uint32_t u : adj[v])
            {
                if (done[u]) continue;
                const double nd = d + w;
                if (nd < raDist[u])
                {
                    raDist[u] = nd;
                    raParent[u] = static_cast<int64_t>(v);
                    pq.emplace(nd, order++, u);
                }
            }
        }
        if (protocol == "riskaware")
        {
            Ipv4StaticRoutingHelper srh;
            for (uint32_t i = 0; i < nSensors; ++i)
            {
                if (raParent[i] < 0) continue;
                Ptr<Ipv4> ipv4 = sensors.Get(i)->GetObject<Ipv4>();
                Ptr<Ipv4StaticRouting> sr = srh.GetStaticRouting(ipv4);
                Ipv4Address nh = interfaces.GetAddress(static_cast<uint32_t>(raParent[i]));
                uint32_t iff = ipv4->GetInterfaceForDevice(devices.Get(i));
                sr->AddHostRouteTo(gatewayAddr, nh, iff);
            }
        }
        // risk drop filters, only where p > 0
        g_riskEligible.assign(n, 0);
        g_riskDropped.assign(n, 0);
        g_riskPassed.assign(n, 0);
        g_riskDropSeed = riskDropSeed;
        for (uint32_t i = 0; i < nSensors; ++i)
        {
            if (g_riskP[i] <= 0.0) continue;
            Ptr<Ipv4ListRouting> list = DynamicCast<Ipv4ListRouting>(sensors.Get(i)->GetObject<Ipv4>()->GetRoutingProtocol());
            NS_ABORT_MSG_IF(!list, "risk: node " << i << " has no Ipv4ListRouting");
            Ptr<RiskDropFilter> f = CreateObject<RiskDropFilter>();
            f->Configure(i, g_riskP[i]);
            list->AddRoutingProtocol(f, 1000);
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

    // ---- per-UID accounting hookups (only with --uidAccounting; every connection is checked) ----
    if (uidAccounting)
    {
        g_uidOn = true;
        g_uidGw = gatewayAddr;
        g_uidPort = port;
        g_uidPayload = packetSize;
        for (uint32_t i = 0; i < n; ++i)
        {
            Ptr<Node> nd = allNodes.Get(i);
            std::string base = "/NodeList/" + std::to_string(i) + "/DeviceList/0/$ns3::WifiNetDevice/";
            std::string ipb = "/NodeList/" + std::to_string(i) + "/$ns3::Ipv4L3Protocol/";
            Config::ConnectWithoutContext(ipb + "Tx", MakeBoundCallback(&OnUidIpTx, i));
            Config::ConnectWithoutContext(ipb + "Rx", MakeBoundCallback(&OnUidIpRx, i));
            Config::ConnectWithoutContext(ipb + "Drop", MakeBoundCallback(&OnUidIpDrop, i));
            std::vector<std::string> qs;
            if (!sc.qos) qs.push_back("Txop");
            else qs = {"VO_Txop", "VI_Txop", "BE_Txop", "BK_Txop"};
            for (const std::string& q : qs)
            {
                std::string qp = base + "Mac/$ns3::AdhocWifiMac/" + q + "/Queue/";
                Config::ConnectWithoutContext(qp + "Enqueue", MakeBoundCallback(&OnUidMacEnq, i));
                Config::ConnectWithoutContext(qp + "Dequeue", MakeBoundCallback(&OnUidMacDeq, i));
                Config::ConnectWithoutContext(qp + "DropBeforeEnqueue", MakeBoundCallback(&OnUidMacDropBefore, i));
                Config::ConnectWithoutContext(qp + "DropAfterDequeue", MakeBoundCallback(&OnUidMacDropAfter, i));
            }
            Config::ConnectWithoutContext(base + "Mac/DroppedMpdu", MakeBoundCallback(&OnUidDroppedMpdu, i));
            Ptr<ArpL3Protocol> arp = nd->GetObject<ArpL3Protocol>();
            NS_ABORT_MSG_IF(!arp->TraceConnectWithoutContext("Drop", MakeBoundCallback(&OnUidArpL3Drop, i)),
                            "uid: ArpL3Protocol Drop not connected on node " << i);
            Ptr<ArpCache> cache = nd->GetObject<Ipv4L3Protocol>()->GetInterface(1)->GetArpCache();
            NS_ABORT_MSG_IF(!cache->TraceConnectWithoutContext("Drop", MakeBoundCallback(&OnUidArpCacheDrop, i)),
                            "uid: ArpCache Drop not connected on node " << i);
            Ptr<TrafficControlLayer> tc = nd->GetObject<TrafficControlLayer>();
            NS_ABORT_MSG_IF(!tc || !tc->TraceConnectWithoutContext("TcDrop", MakeBoundCallback(&OnUidTcDrop, i)),
                            "uid: TrafficControlLayer TcDrop not connected on node " << i);
            Ptr<QueueDisc> qd = tc->GetRootQueueDiscOnDevice(devices.Get(i));
            NS_ABORT_MSG_IF(!qd, "uid: no root queue disc on the Wi-Fi device of node " << i);
            bool ok = qd->TraceConnectWithoutContext("Enqueue", MakeBoundCallback(&OnUidQdiscEnq, i)) &&
                      qd->TraceConnectWithoutContext("Requeue", MakeBoundCallback(&OnUidQdiscEnq, i)) &&
                      qd->TraceConnectWithoutContext("Dequeue", MakeBoundCallback(&OnUidQdiscDeq, i)) &&
                      qd->TraceConnectWithoutContext("DropBeforeEnqueue", MakeBoundCallback(&OnUidQdiscDropBefore, i)) &&
                      qd->TraceConnectWithoutContext("DropAfterDequeue", MakeBoundCallback(&OnUidQdiscDropAfter, i));
            NS_ABORT_MSG_IF(!ok, "uid: queue disc traces not connected on node " << i);
        }
        NS_ABORT_MSG_IF(!sinkApp.Get(0)->TraceConnectWithoutContext("Rx", MakeCallback(&OnUidSinkRx)),
                        "uid: sink Rx not connected");
        for (uint32_t i = 0; i < nSensors; ++i)
            NS_ABORT_MSG_IF(!sensors.Get(i)->GetApplication(0)->TraceConnectWithoutContext(
                                "Tx", MakeBoundCallback(&OnUidAppTx, i)),
                            "uid: app Tx not connected on sensor " << i);
    }

    // ---- risk study hookups (only with --riskStudy; read-only except RiskDropFilter above) ----
    if (riskStudy)
    {
        g_riskPort = port;
        g_appSeq.assign(nSensors, 0);
        for (uint32_t i = 0; i < n; ++i)
        {
            Config::ConnectWithoutContext("/NodeList/" + std::to_string(i) + "/$ns3::Ipv4L3Protocol/UnicastForward",
                                          MakeBoundCallback(&OnRiskForward, i));
            Config::ConnectWithoutContext("/NodeList/" + std::to_string(i) +
                                              "/DeviceList/0/$ns3::WifiNetDevice/Phy/PhyTxPsduBegin",
                                          MakeBoundCallback(&OnRiskPsdu, i));
        }
        NS_ABORT_MSG_IF(!sinkApp.Get(0)->TraceConnectWithoutContext("Rx", MakeCallback(&OnRiskSinkRx)),
                        "risk: sink Rx not connected");
        for (uint32_t i = 0; i < nSensors; ++i)
            NS_ABORT_MSG_IF(!sensors.Get(i)->GetApplication(0)->TraceConnectWithoutContext(
                                "Tx", MakeBoundCallback(&OnRiskAppTx, i)),
                            "risk: app Tx not connected on sensor " << i);
    }

    // ---- Block Ack SSN fix hookups (QoS standards only) ----
    if (baSsnFix && sc.qos)
    {
        for (uint32_t i = 0; i < n; ++i)
        {
            Ptr<WifiNetDevice> dev = DynamicCast<WifiNetDevice>(devices.Get(i));
            g_baFixMac.push_back(dev->GetMac());
            NS_ABORT_MSG_IF(!dev->GetPhy()->TraceConnectWithoutContext("PhyTxPsduBegin", MakeBoundCallback(&OnBaFixPsdu, i)),
                            "baSsnFix: PhyTxPsduBegin not connected on node " << i);
            for (uint8_t ac = 0; ac < 4; ++ac)
                NS_ABORT_MSG_IF(!dev->GetMac()->GetQosTxop(static_cast<AcIndex>(ac))->GetBaManager()->TraceConnectWithoutContext(
                                    "AgreementState", MakeBoundCallback(&OnBaFixState, i, ac)),
                                "baSsnFix: AgreementState not connected on node " << i);
        }
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

    // ---- risk study: Wi-Fi settings read back from the installed devices (before Destroy) ----
    std::ostringstream wifiReadback;
    if (riskStudy)
    {
        wifiReadback << "node_id,standard,band,channel_number,channel_width_mhz,he_configuration,he_guard_interval_ns,"
                        "data_mode,control_mode,be_max_ampdu_bytes,be_max_amsdu_bytes\n";
        for (uint32_t i = 0; i < n; ++i)
        {
            Ptr<WifiNetDevice> dev = DynamicCast<WifiNetDevice>(devices.Get(i));
            Ptr<WifiPhy> phy = dev->GetPhy();
            const WifiPhyOperatingChannel& ch = phy->GetOperatingChannel();
            Ptr<HeConfiguration> he = dev->GetHeConfiguration();
            WifiModeValue dm, cm;
            dev->GetRemoteStationManager()->GetAttribute("DataMode", dm);
            dev->GetRemoteStationManager()->GetAttribute("ControlMode", cm);
            UintegerValue ampduBe, amsduBe;
            dev->GetMac()->GetAttribute("BE_MaxAmpduSize", ampduBe);
            dev->GetMac()->GetAttribute("BE_MaxAmsduSize", amsduBe);
            wifiReadback << i << "," << phy->GetStandard() << "," << phy->GetPhyBand() << ","
                         << +ch.GetNumber() << "," << ch.GetWidth() << "," << (he ? 1 : 0) << ","
                         << (he ? std::to_string(he->GetGuardInterval().GetNanoSeconds()) : std::string("NA")) << ","
                         << dm.Get().GetUniqueName() << "," << cm.Get().GetUniqueName() << "," << ampduBe.Get()
                         << "," << amsduBe.Get() << "\n";
        }
    }

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

    // ---- per-UID accounting output (only with --uidAccounting; new files only) ----
    if (uidAccounting)
    {
        const int64_t endNs = static_cast<int64_t>(simTime * 1e9);
        const int64_t inflightNs = 100000000;   // 0.1 s: last MAC dequeue this close to the end = in flight
        enum { P_ARP, P_QDISC, P_MACQ, P_INFLIGHT, P_N };
        static const char* kPend[P_N] = {"pending_arp", "pending_qdisc", "pending_macq", "pending_in_flight"};
        enum { X_SENT_OLD, X_IP_RX, X_LOOPBACK, X_DEV_HANDOFF, X_NONE, X_N };
        static const char* kUnac[X_N] = {"unacc_mac_sent_not_received", "unacc_ip_rx_not_forwarded",
                                         "unacc_loopback_deferred", "unacc_qdisc_dequeued_not_in_mac",
                                         "unacc_no_stage"};
        struct PerNode
        {
            uint64_t originated = 0, delivered = 0;
            uint64_t drop[UD_N] = {};
            uint64_t pend[P_N] = {};
            uint64_t unac[X_N] = {};
        };
        std::vector<PerNode> pnU(n);
        uint64_t appTxU = 0, deliveredU = 0, dups = 0, sinkRx = 0, drops[UD_N] = {}, pend[P_N] = {}, unac[X_N] = {};
        uint64_t confDelDrop = 0, multiDrop = 0, nonHolder = 0, noAppTx = 0;
        for (const auto& kv : g_uid)
        {
            const UidRec& r = kv.second;
            sinkRx += r.rx;
            if (r.src < 0) { ++noAppTx; continue; }
            ++appTxU;
            pnU[r.src].originated++;
            if (r.dropEvents > 1) ++multiDrop;
            if (r.dropAtNonHolder) ++nonHolder;
            if (r.rx > 0)
            {
                ++deliveredU;
                dups += r.rx - 1;
                pnU[r.src].delivered++;
                if (r.dropEvents > 0) ++confDelDrop;
                continue;
            }
            if (r.firstDrop >= 0)
            {
                drops[r.firstDrop]++;
                pnU[r.firstDropNode].drop[r.firstDrop]++;
                continue;
            }
            const uint32_t at = r.holder >= 0 ? static_cast<uint32_t>(r.holder) : static_cast<uint32_t>(r.src);
            int p = -1, x = -1;
            switch (r.stage)
            {
            case US_IP_TX: p = P_ARP; break;
            case US_QDISC: p = P_QDISC; break;
            case US_MACQ: p = P_MACQ; break;
            case US_SENT: if (endNs - r.lastTs <= inflightNs) p = P_INFLIGHT; else x = X_SENT_OLD; break;
            case US_IP_RX: x = X_IP_RX; break;
            case US_LOOPBACK: x = X_LOOPBACK; break;
            case US_DEV_HANDOFF: x = X_DEV_HANDOFF; break;
            default: x = X_NONE; break;
            }
            if (p >= 0) { pend[p]++; pnU[at].pend[p]++; }
            else { unac[x]++; pnU[at].unac[x]++; }
        }
        uint64_t dropTot = 0, pendTot = 0, unacTot = 0;
        for (int k = 0; k < UD_N; ++k) dropTot += drops[k];
        for (int k = 0; k < P_N; ++k) pendTot += pend[k];
        for (int k = 0; k < X_N; ++k) unacTot += unac[k];

        std::string udir = outDir + "/uid_pernode";
        mkdir(udir.c_str(), 0755);
        std::ostringstream up;
        up << udir << "/uid_" << protocol << "_" << nSensors << "_" << trafficLevel << "_seed" << seed << ".csv";
        std::ofstream uf(up.str());
        uf << "node_id,is_gateway,hop_to_gw,originated,delivered";
        for (int k = 0; k < UD_N; ++k) uf << "," << kUidDropName[k];
        for (int k = 0; k < P_N; ++k) uf << "," << kPend[k];
        for (int k = 0; k < X_N; ++k) uf << "," << kUnac[k];
        uf << "\n";
        for (uint32_t i = 0; i < n; ++i)
        {
            const PerNode& q = pnU[i];
            uf << i << "," << (i == gatewayIndex ? 1 : 0) << "," << hop[i] << "," << q.originated << "," << q.delivered;
            for (int k = 0; k < UD_N; ++k) uf << "," << q.drop[k];
            for (int k = 0; k < P_N; ++k) uf << "," << q.pend[k];
            for (int k = 0; k < X_N; ++k) uf << "," << q.unac[k];
            uf << "\n";
        }
        uf.close();

        std::ofstream sf(outDir + "/uid_summary.csv");
        sf << "protocol,nodes,trafficLevel,offered_rate_kbps,seed,arp_prepopulate,app_tx_uids,app_tx_counter,"
              "sink_rx_counter,sink_rx_uid_sum,sink_rx_unknown_uid,fm_tx_pkts,fm_rx_pkts,delivered_unique,duplicates";
        for (int k = 0; k < UD_N; ++k) sf << "," << kUidDropName[k];
        sf << ",dropped_total";
        for (int k = 0; k < P_N; ++k) sf << "," << kPend[k];
        sf << ",pending_total";
        for (int k = 0; k < X_N; ++k) sf << "," << kUnac[k];
        sf << ",unaccounted_total,conflict_delivered_and_dropped,uids_multiple_drop_events,uids_drop_at_non_holder,"
              "data_records_without_app_tx\n";
        sf << protocol << "," << nSensors << "," << trafficLevel << "," << actualRateKbps << "," << seed << ","
           << (arpPrepopulate ? 1 : 0) << "," << appTxU << "," << appTx << "," << g_appRx << "," << sinkRx << ","
           << g_uidSinkUnknown << "," << txPkts << "," << rxPkts << "," << deliveredU << "," << dups;
        for (int k = 0; k < UD_N; ++k) sf << "," << drops[k];
        sf << "," << dropTot;
        for (int k = 0; k < P_N; ++k) sf << "," << pend[k];
        sf << "," << pendTot;
        for (int k = 0; k < X_N; ++k) sf << "," << unac[k];
        sf << "," << unacTot << "," << confDelDrop << "," << multiDrop << "," << nonHolder << "," << noAppTx << "\n";
        sf.close();
    }

    // ---- risk study outputs (new files only) ----
    if (riskStudy)
    {
        auto pathOf = [&](const std::vector<int64_t>& par, uint32_t s) {
            std::vector<uint32_t> p;   // nodes after s, ending at the gateway; empty if unreachable
            int64_t a = par[s];
            uint32_t guard = 0;
            while (a >= 0 && guard++ <= n)
            {
                p.push_back(static_cast<uint32_t>(a));
                if (a == static_cast<int64_t>(gatewayIndex)) break;
                a = par[a];
            }
            if (p.empty() || p.back() != gatewayIndex) p.clear();
            return p;
        };
        auto costOf = [&](const std::vector<uint32_t>& p) {
            double c = 0.0;
            for (uint32_t v : p) c += 1.0 + riskBeta * (v == gatewayIndex ? 0.0 : tau[v]);
            return c;
        };
        auto highOf = [&](const std::vector<uint32_t>& p) {
            uint32_t h = 0;
            for (uint32_t v : p) h += (v != gatewayIndex && g_riskState[v] == HIGH_RISK) ? 1 : 0;
            return h;
        };
        auto join = [](const std::vector<uint32_t>& p, uint32_t first) {
            std::ostringstream o;
            o << first;
            for (uint32_t v : p) o << ">" << v;
            return o.str();
        };
        // safe path: BFS from the gateway with HIGH_RISK nodes allowed only as the source itself
        std::vector<bool> safeReach(n, false);
        {
            std::queue<uint32_t> q;
            safeReach[gatewayIndex] = true;
            q.push(gatewayIndex);
            while (!q.empty())
            {
                uint32_t v = q.front();
                q.pop();
                if (v != gatewayIndex && g_riskState[v] == HIGH_RISK) continue;   // reached, but not a relay
                for (uint32_t u : adj[v])
                    if (!safeReach[u]) { safeReach[u] = true; q.push(u); }
            }
        }
        std::string highStr;
        for (size_t k = 0; k < highIds.size(); ++k) highStr += (k ? ";" : "") + std::to_string(highIds[k]);

        std::ofstream rn(outDir + "/risk_nodes.csv");
        rn << "node_id,is_gateway,hop_to_gw,degree,bfs_descendants,is_relay_candidate,selection_rank,risk_state,"
              "risk_score,risk_tau,high_risk_rank,eligible_transit_pkts,risk_dropped,risk_passed\n";
        for (uint32_t i = 0; i < n; ++i)
        {
            auto rk = std::find(ranking.begin(), ranking.end(), i);
            bool isCand = i < nSensors && hop[i] >= 1 && descendants[i] >= 1;
            rn << i << "," << (i == gatewayIndex ? 1 : 0) << "," << hop[i] << "," << degree[i] << ","
               << descendants[i] << "," << (isCand ? 1 : 0) << ","
               << (rk == ranking.end() ? -1 : static_cast<int64_t>(rk - ranking.begin()) + 1) << ","
               << (g_riskState[i] == HIGH_RISK ? "HIGH_RISK" : "LOW_RISK") << "," << std::setprecision(17)
               << g_riskP[i] << "," << tau[i] << std::setprecision(6) << "," << highRank[i] << ","
               << g_riskEligible[i] << "," << g_riskDropped[i] << "," << g_riskPassed[i] << "\n";
        }
        rn.close();

        const bool planned = (protocol == "static" || protocol == "riskaware");
        uint32_t srcExposedBfs = 0, srcExposedPlanned = 0, srcAvoided = 0, srcUnavoidable = 0, srcRouted = 0;
        double plannedCostSum = 0.0, plannedHopSum = 0.0;
        std::ofstream rp(outDir + "/routes_planned.csv");
        rp << "src,protocol,reachable,installed_next_hop,installed_path,installed_hops,installed_risk_cost,"
              "installed_high_risk_transits,bfs_path,bfs_hops,bfs_risk_cost,bfs_high_risk_transits,"
              "riskaware_path,riskaware_hops,riskaware_risk_cost,riskaware_high_risk_transits,safe_path_exists\n";
        for (uint32_t s = 0; s < nSensors; ++s)
        {
            std::vector<uint32_t> pb = pathOf(parent, s), pr = pathOf(raParent, s);
            const std::vector<uint32_t>* pi = protocol == "static" ? &pb : protocol == "riskaware" ? &pr : nullptr;
            const bool reach = hop[s] >= 1;
            const bool safe = safeReach[s];
            rp << s << "," << protocol << "," << (reach ? 1 : 0) << ",";
            if (pi && !pi->empty())
                rp << pi->front() << "," << join(*pi, s) << "," << pi->size() << "," << std::setprecision(17)
                   << costOf(*pi) << std::setprecision(6) << "," << highOf(*pi) << ",";
            else
                rp << "NA,NA,NA,NA,NA,";
            if (!pb.empty())
                rp << join(pb, s) << "," << pb.size() << "," << std::setprecision(17) << costOf(pb) << std::setprecision(6)
                   << "," << highOf(pb) << ",";
            else
                rp << "NA,NA,NA,NA,";
            if (!pr.empty())
                rp << join(pr, s) << "," << pr.size() << "," << std::setprecision(17) << costOf(pr) << std::setprecision(6)
                   << "," << highOf(pr) << ",";
            else
                rp << "NA,NA,NA,NA,";
            rp << (safe ? 1 : 0) << "\n";
            if (!pb.empty() && highOf(pb) > 0)
            {
                ++srcExposedBfs;
                if (!safe) ++srcUnavoidable;
                else if (!pr.empty() && highOf(pr) == 0) ++srcAvoided;
            }
            if (pi && !pi->empty())
            {
                ++srcRouted;
                plannedCostSum += costOf(*pi);
                plannedHopSum += pi->size();
                if (highOf(*pi) > 0) ++srcExposedPlanned;
            }
        }
        rp.close();

        // observed paths
        uint64_t appTxR = 0, delivered = 0, dupR = 0, riskLost = 0, otherLost = 0, exposedPkts = 0, highTransits = 0;
        uint64_t hopsDelivered = 0, followPlanned = 0, deliveredChecked = 0;
        std::map<std::pair<uint32_t, std::string>, std::array<uint64_t, 4>> ps;   // (src, path) -> pkts, rx, risk, other
        std::vector<uint64_t> uids;
        uids.reserve(g_path.size());
        for (const auto& kv : g_path) uids.push_back(kv.first);
        std::sort(uids.begin(), uids.end(), [&](uint64_t a, uint64_t b) {
            const PathRec& x = g_path[a];
            const PathRec& y = g_path[b];
            return std::tie(x.src, x.seq) < std::tie(y.src, y.seq);
        });
        std::ofstream pp;
        if (perPacketTrace)
        {
            pp.open(outDir + "/packet_paths.csv");
            pp << "src,seq,uid,tx_time_s,rx_time_s,delay_s,fate,receptions,path,relay_hops,high_risk_transits\n";
        }
        for (uint64_t uid : uids)
        {
            const PathRec& r = g_path[uid];
            ++appTxR;
            uint32_t ht = 0;
            for (uint32_t v : r.relays) ht += (g_riskState[v] == HIGH_RISK) ? 1 : 0;
            std::string fate = r.rx > 0 ? "delivered" : r.riskDropNode >= 0 ? "risk_drop" : "lost_other";
            if (r.rx > 0) { ++delivered; dupR += r.rx - 1; hopsDelivered += r.relays.size() + 1; }
            else if (r.riskDropNode >= 0) ++riskLost;
            else ++otherLost;
            if (ht > 0) ++exposedPkts;
            highTransits += ht;
            std::ostringstream path;
            path << r.src;
            for (uint32_t v : r.relays) path << ">" << v;
            if (r.rx > 0) path << ">" << gatewayIndex;
            auto& cell = ps[{r.src, path.str()}];
            cell[0]++;
            if (r.rx > 0) cell[1]++;
            else if (r.riskDropNode >= 0) cell[2]++;
            else cell[3]++;
            if (planned && r.rx > 0)
            {
                std::vector<uint32_t> want = pathOf(protocol == "static" ? parent : raParent, r.src);
                std::vector<uint32_t> got = r.relays;
                got.push_back(gatewayIndex);
                ++deliveredChecked;
                if (got == want) ++followPlanned;
            }
            if (perPacketTrace)
                pp << r.src << "," << r.seq << "," << uid << "," << std::setprecision(12) << r.txNs * 1e-9 << ","
                   << (r.rxNs >= 0 ? std::to_string(r.rxNs * 1e-9) : std::string("NA")) << ","
                   << (r.rxNs >= 0 ? std::to_string((r.rxNs - r.txNs) * 1e-9) : std::string("NA"))
                   << std::setprecision(6) << "," << fate << "," << r.rx << "," << path.str() << ","
                   << r.relays.size() << "," << ht << "\n";
        }
        if (perPacketTrace) pp.close();
        std::ofstream sp(outDir + "/path_summary.csv");
        sp << "src,path,packets,delivered,risk_dropped,lost_other,high_risk_transits\n";
        for (const auto& kv : ps)
        {
            uint32_t ht = 0;
            std::istringstream ss(kv.first.second);
            std::string tok;
            bool first = true;
            while (std::getline(ss, tok, '>'))
            {
                uint32_t v = static_cast<uint32_t>(std::stoul(tok));
                if (!first && v != gatewayIndex && g_riskState[v] == HIGH_RISK) ++ht;
                first = false;
            }
            sp << kv.first.first << "," << kv.first.second << "," << kv.second[0] << "," << kv.second[1] << ","
               << kv.second[2] << "," << kv.second[3] << "," << ht << "\n";
        }
        sp.close();

        std::ofstream rd(outDir + "/risk_drops.csv");
        rd << "node_id,src,seq,uid,time_s,u\n";
        for (const RiskDropRec& d : g_riskDropLog)
            rd << d.node << "," << d.src << "," << d.seq << "," << d.uid << "," << std::setprecision(12) << d.ns * 1e-9
               << "," << std::setprecision(17) << d.u << std::setprecision(6) << "\n";
        rd.close();

        uint64_t riskDropsTot = 0;
        for (uint32_t i = 0; i < n; ++i) riskDropsTot += g_riskDropped[i];
        std::ofstream rs(outDir + "/risk_summary.csv");
        rs << "standard,protocol,nodes,trafficLevel,offered_rate_kbps,seed,arp_prepopulate,num_high_risk,risk_select,"
              "high_risk_ids,high_risk_drop_prob,low_risk_drop_prob,risk_beta,risk_drop_seed,relay_candidates,"
              "app_tx_pkts,path_records,delivered_unique,duplicates,sink_rx_counter,fm_rx_pkts,pdr_app_pct,"
              "risk_dropped_pkts,risk_drop_events,lost_other_pkts,risk_share_of_loss_pct,exposed_pkts,"
              "exposure_rate_pct,mean_high_risk_transits_per_pkt,mean_hops_delivered,srcs_routed,"
              "srcs_exposed_bfs,srcs_exposed_installed,srcs_avoided_by_riskaware,srcs_unavoidable,"
              "mean_installed_risk_cost,mean_installed_hops,delivered_following_installed_path,"
              "delivered_checked_against_installed,key_missing,eligible_local_source\n";
        const uint64_t lost = appTxR - delivered;
        rs << sc.name << "," << protocol << "," << nSensors << "," << trafficLevel << "," << actualRateKbps << "," << seed
           << "," << (arpPrepopulate ? 1 : 0) << "," << numHighRisk << "," << riskSelect << ","
           << (highStr.empty() ? "none" : highStr) << "," << highRiskDropProb << "," << lowRiskDropProb << ","
           << riskBeta << "," << riskDropSeed << "," << ranking.size() << "," << appTx << "," << appTxR << ","
           << delivered << "," << dupR << "," << g_appRx << "," << rxPkts << ","
           << (appTxR ? 100.0 * delivered / appTxR : 0.0) << "," << riskLost << "," << riskDropsTot << ","
           << otherLost << "," << (lost ? 100.0 * riskLost / lost : 0.0) << "," << exposedPkts << ","
           << (appTxR ? 100.0 * exposedPkts / appTxR : 0.0) << ","
           << (appTxR ? static_cast<double>(highTransits) / appTxR : 0.0) << ","
           << (delivered ? static_cast<double>(hopsDelivered) / delivered : 0.0) << "," << srcRouted << ","
           << srcExposedBfs << "," << (planned ? std::to_string(srcExposedPlanned) : std::string("NA")) << ","
           << srcAvoided << "," << srcUnavoidable << ","
           << (planned && srcRouted ? std::to_string(plannedCostSum / srcRouted) : std::string("NA")) << ","
           << (planned && srcRouted ? std::to_string(plannedHopSum / srcRouted) : std::string("NA")) << ","
           << (planned ? std::to_string(followPlanned) : std::string("NA")) << ","
           << (planned ? std::to_string(deliveredChecked) : std::string("NA")) << "," << g_riskKeyMissing << ","
           << g_riskLocalSource << "\n";
        rs.close();

        std::ofstream wr(outDir + "/wifi_readback.csv");
        wr << wifiReadback.str();
        wr.close();
        std::ofstream wt(outDir + "/wifi_txvector_counts.csv");
        wt << "frame_class,frame_type,preamble,modulation_class,mode,channel_width_mhz,guard_interval_ns,psdus\n";
        for (const auto& kv : g_txvCounts) wt << kv.first << "," << kv.second << "\n";
        wt.close();
    }

    if (baSsnFix && sc.qos)
    {
        std::ofstream bf(outDir + "/ba_ssn_fix.csv");
        bf << "time_s,node_id,recipient,tid,advertised_ssn,originator_start,bar_scheduled\n";
        for (const BaFixRec& b : g_baFixLog)
            bf << std::setprecision(12) << b.ns * 1e-9 << std::setprecision(6) << "," << b.node << "," << b.recipient << ","
               << +b.tid << "," << b.advertised << "," << b.originatorStart << ",1\n";
        bf.close();
    }

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
