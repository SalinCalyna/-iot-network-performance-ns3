# arp-r0-off: R0 flag-off regression of iot-network-wifi-std-arp.cc vs results/v3-ext

15 runs, 2026-10-18 15:41-15:45 +0700, `--arpPrepopulate` off, seed 20, static mobility:
AODV/OLSR/Static x N 10/20/50 x high (16 kbps), plus N=50 x low (4 kbps) and medium (8 kbps).
Low = `--trafficLevel=high --offeredRateKbps=4` (the program has no "low" label); run ids and all analysis labels say `low`.
Source 4923685a52f9f813, binary 9f74bd9ce2c6f009, HEAD 043f0f609 (exp/wifi6-arp). Every run exit 0, stderr 0 B.
Comparison: `experiments/wifi-std/compare_r0_v3ext.py`.

## Result
- First comparison (`../arp-r0-off_compare.txt`): 285 values compared, 7 differ, all in two columns:
  - `PathChanges`, OLSR N=10/20/50 high and N=50 low/medium (5 values): v3-ext 10/122/1268/288/617 vs new 0.
  - `UnreachableSensors`, AODV and OLSR N=10 high (2 values): v3-ext 0 vs new 8.
  The other 278 values (incl. PDR, throughput, delay, jitter, hop count, routing overhead) are identical.
- Official comparison (`../arp-r0-off_compare_v2.txt`), with the two columns excluded: 255 values compared, 0 differ, R0 PASS.

## Decision (user, 2026-10-18)
The 7 differences come from how the two programs report these columns, not from the simulation:
- `PathChanges`: `scratch/iot-network-wifi-std-arp.cc:532-533` schedules the route sampler only when
  `protocol == "aodv"`; `scratch/iot-network-v3-ext.cc:505-513` schedules it for every protocol. The sampler is a
  passive RouteOutput lookup, and all traffic metrics of the OLSR runs are identical.
- `UnreachableSensors`: `scratch/iot-network-wifi-std-arp.cc:435-437` counts BFS-unreachable sensors for every
  protocol; `scratch/iot-network-v3-ext.cc:1190-1245` counts them only inside `if (protocol == "static")`, so AODV/OLSR
  always report 0 there.

Therefore:
1. `PathChanges` and `UnreachableSensors` are removed from the regression criterion against v3-ext
   (`EXCLUDED` in compare_r0_v3ext.py; still printed, never a FAIL).
2. Neither column from iot-network-wifi-std-arp.cc is used in any analysis.
