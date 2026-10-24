#!/usr/bin/env python3
"""Count AODV routing events from an NS_LOG stream on stdin (read-only diagnostic; nothing is stored but counts).

    NS_LOG="AodvRoutingProtocol=level_logic|prefix_time|prefix_node" <sim> ... 2>&1 >stdout.log \
        | python3 -I -B aodv_log_counter.py <run dir> <gateway ip> <first send s> <cbr period s>

Log lines look like "+30.512000000s 5 [node 5] AodvRoutingProtocol:SendRequest(0x..., 10.1.1.101)".
Every line that does not start with "+" is not NS_LOG output and is copied to <run dir>/stderr.log, so stderr.log
keeps its usual meaning. Writes <run dir>/aodv_log_counts.json:
  totals            per event key (function entry, or a classified LOGIC/DEBUG message)
  per_10s           per event key, counts in 10 s bins of simulation time
  phase_32ms        for t >= first send: counts per 32 ms bin of (t - first send) mod cbr period
  rreq_by_dst       SendRequest destination: gateway / other
  per_node          per node: SendRequest, SendHello, RERR (link break / no route), RecvRequest
"""
import json
import sys
from collections import defaultdict

MSG = (  # (prefix, key) for LOGIC/DEBUG messages
    ("Send RREQ with id", "rreq_sent_to_socket"),
    ("Send new RREQ for outbound packet", "rreq_new_for_outbound"),
    ("Resend RREQ", "rreq_resend"),
    ("route discovery to", "rreq_retries_exhausted"),
    ("Route not found. Drop all packets", "drop_all_route_not_found"),
    ("Route down. Stop search", "drop_route_down_stop_search"),
    ("Ignoring RREQ due to duplicate", "rreq_ignored_duplicate"),
    ("Ignoring RREQ from node in blacklist", "rreq_ignored_blacklist"),
    ("TTL exceeded. Drop RREQ", "rreq_ttl_exceeded"),
    ("Send reply since I am the destination", "rrep_by_destination"),
    ("Drop RREQ from", "rreq_dropped_dest_nexthop"),
    ("TTL exceeded. Drop RREP", "rrep_ttl_exceeded"),
    ("Send gratuitous RREP", "rrep_gratuitous"),
    ("Hello deferred", "hello_deferred"),
    ("Broadcast RERR", "rerr_broadcast"),
    ("Unicast RERR", "rerr_unicast"),
    ("one precursor => unicast RERR", "rerr_unicast_one_precursor"),
    ("RerrRateLimit reached", "rerr_rate_limited"),
    ("No precursors", "rerr_no_precursors"),
    ("Send RERR message with maximum size", "rerr_max_size"),
    ("route not found to", "no_route_forward_send_rerr"),
    ("Drop packet", "drop_packet_no_route"),
    ("Duplicated packet", "duplicate_broadcast"),
    ("Valid Route not found", "routeoutput_no_valid_route"),
    ("Add packet", "queued_awaiting_route"),
    ("Applying binary exponential backoff", "rreq_backoff"),
)
TIMED = {"SendRequest", "SendHello", "SendRerrWhenBreaksLinkToNextHop", "SendRerrWhenNoRouteToForward",
         "SendRerrMessage", "RecvRequest", "RecvReply", "RecvError", "SendReply", "SendReplyByIntermediateNode",
         "rreq_resend", "rreq_new_for_outbound", "drop_all_route_not_found", "rreq_ignored_duplicate"}


def main():
    run, gw, t0, period = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
    tot, per10, phase = defaultdict(int), defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))
    node = defaultdict(lambda: defaultdict(int))
    rdst = defaultdict(int)
    nlines = 0
    with open(f"{run}/stderr.log", "w") as err:
        for raw in sys.stdin.buffer:
            line = raw.decode("utf-8", "replace")
            if not line.startswith("+"):
                err.write(line)
                continue
            nlines += 1
            try:
                ts, _ctx, rest = line.split(" ", 2)
                t = float(ts[1:-1])
                if rest.startswith("[node "):
                    nd, msg = rest[6:].split("] ", 1)
                else:
                    nd, msg = "-1", rest
            except ValueError:
                tot["unparsed"] += 1
                continue
            if msg.startswith("AodvRoutingProtocol:"):
                key = msg[20:msg.find("(")] if "(" in msg else msg[20:].strip()
                if key == "SendRequest":
                    rdst["gateway" if msg.rstrip().endswith(gw + ")") else "other"] += 1
            else:
                key = next((k for p, k in MSG if msg.startswith(p)), None)
                if key is None:
                    key = "other_msg"
            tot[key] += 1
            if key in TIMED:
                per10[key][int(t // 10) * 10] += 1
                if t >= t0:
                    phase[key][int(((t - t0) % period) / 0.032)] += 1
            if key in ("SendRequest", "SendHello", "SendRerrWhenBreaksLinkToNextHop", "SendRerrWhenNoRouteToForward",
                       "RecvRequest", "rreq_resend"):
                node[nd][key] += 1
    json.dump(dict(log_lines=nlines, totals=dict(sorted(tot.items())), rreq_by_dst=dict(rdst),
                   per_10s={k: dict(sorted(v.items())) for k, v in per10.items()},
                   phase_32ms={k: dict(sorted(v.items())) for k, v in phase.items()},
                   per_node={k: dict(v) for k, v in sorted(node.items(), key=lambda x: int(x[0]))}),
              open(f"{run}/aodv_log_counts.json", "w"), indent=1)


if __name__ == "__main__":
    main()
