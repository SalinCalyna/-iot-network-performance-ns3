# UPDATE #8 — Tier-1 V4 Activation Screen (Full Report)

**Approved scope, executed exactly.** 66/66 runs complete; integrity audit passed. This
report completes the analysis of the **existing** 66-run Tier-1 dataset. **No further
simulation was run. No source, runner, dashboard, or existing dataset was modified. No Git
commit/push.**

- **Source modification required? NO.** The V4 binary already exposes `--v4X0Risk`,
  `--v4X0Load`, `--v4KRisk`, `--v4KLoad`, `--v4WRisk`, `--v4WLoad`;
  `scratch/iot-network-v3-ext.cc` was used as-is and is git-clean.
- **Output:** `analysis/update8-tier1-activation/data/` (NEW; under `analysis/`, not
  `results/` — cannot collide with any locked dataset). The binary's fixed filename
  `v4_50_medium_static.csv` is in a *different directory* from
  `results/v4-sensitivity/v4_50_medium_static.csv`, so the identical basename is not a
  collision.
- Runs issued by `run_tier1_screen.sh` (in the new dir) calling the binary directly with
  the exact shared parameters `experiments/v4_sensitivity_study.py` uses, so Tier-1 matches
  the Stage-1 condition (50 nodes / medium traffic / static mobility / 300 s, seeds 20–30).

Everything below is **descriptive** statistics on **n = 11 seeds per configuration** — a
small sample; this is stated wherever an inference is drawn (§ Statistical comparison).

---

## 1. Configuration & integrity

| | |
|---|---|
| Expected / completed / failed runs | **66 / 66 / 0** |
| Structure | 6 configs × 11 seeds; `k_R = k_L = 10`, `w_R = w_L = 0.5`; `x0_R ∈ {0.50, 0.80}` × `x0_L ∈ {0.02, 0.05, 0.50}` |
| Missing / duplicate rows | 0 / 0 |
| Configs present | 6 / 6 (0 missing, 0 unexpected) |
| Rows per config / seeds | exactly 11 / {20…30} |
| `HopCountMethod` | `exact` (all 66) — clean exact-vs-exact comparison with Static |
| `PathChanges` | **0 for all 66 rows** (routes fixed for the run; **not** real-time adaptation) |
| NaN / Inf / negatives / bound violations | 0 / 0 / 0 / 0 |
| `k = 10` overlap with Stage-1 (`k ∈ {0.5,2,5}`) | none — all 66 runs are new |

---

## 2. Per-configuration results (the 10 requested quantities)

Route-tree difference from Static uses `AverageHopCount` (`exact` on both sides) as the
tree-identity proxy. "seeds tree ≠ Static" = number of the 11 seeds whose V4 mean hop count
differs from the seed-matched Static value. Static baseline at this condition (seeds 20–30):
**PDR 36.44 %, Throughput 153.65 kbps, Delay 0.0972 s, Jitter 0.0389 s, Packet Loss 16 747,
Hop Count 1.578, AvgLinkUtil 0.00784, MaxLinkUtil 0.0522.**

| # | `x0_R` | `x0_L` | **Route-tree diff from Static** | **PathChanges** | **HopCount** (V4 / Static) | **PDR %** | **Throughput** kbps | **Delay** s | **Jitter** s | **PacketLoss** | **AvgLinkUtil** | **MaxLinkUtil** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.50 | 0.02 | **0 / 11 seeds (0.0 %)** — trees identical (mean |Δhop| = 0.000) | 0 | 1.578 / 1.578 (+0.0 %) | 34.95 | 147.36 | 0.1011 | 0.0407 | 17 140 | 0.00789 | 0.0547 |
| 2 | 0.50 | 0.05 | **1 / 11 (9.1 %)** — mean |Δhop| 0.002, max 0.02 | 0 | 1.580 / 1.578 (+0.1 %) | 35.15 | 148.20 | 0.1012 | 0.0407 | 17 087 | 0.00793 | 0.0552 |
| 3 | 0.50 | **0.50** | **8 / 11 (72.7 %) — ACTIVATED** — mean |Δhop| 0.038, max 0.12 | 0 | 1.616 / 1.578 (+2.4 %) | 32.40 | 136.59 | 0.0906 | 0.0369 | 17 813 | 0.00765 | 0.0468 |
| 4 | 0.80 | 0.02 | **3 / 11 (27.3 %)** — mean |Δhop| 0.011, max 0.04 | 0 | 1.589 / 1.578 (+0.7 %) | 34.89 | 147.08 | 0.0984 | 0.0400 | 17 157 | 0.00800 | 0.0572 |
| 5 | 0.80 | 0.05 | **5 / 11 (45.5 %) — ACTIVATED** — mean |Δhop| 0.016, max 0.04 | 0 | 1.595 / 1.578 (+1.0 %) | 34.51 | 145.48 | 0.0970 | 0.0391 | 17 258 | 0.00801 | 0.0564 |
| 6 | 0.80 | **0.50** | **11 / 11 (100 %) — ACTIVATED** — **mean |Δhop| 0.440, max 1.10** | 0 | **2.018 / 1.578 (+27.9 %)** | 37.72 | 159.04 | 0.1182 | 0.0410 | 16 410 | 0.00931 | 0.0745 |

`T_tier1_activation_and_perf.csv`, `T_full_paired_stats.csv`,
`plots/fig1_route_change_by_config.png`, `plots/fig_{PDR,Throughput,Delay,PacketLoss}_by_config.png`.

**Note:** `PathChanges = 0` in every config — V4 installs one fixed tree per run and never
changes it during the simulation. Route "activity" here means *the installed tree differs
from Static's*, not runtime re-routing.

---

## 3. Statistical comparison vs matched Static (paired, n = 11 seeds)

Paired difference `d_s = V4(seed s) − Static(seed s)`. Reported: mean Δ, median Δ,
two-sided **exact sign-test p** (binomial on the count of seeds where V4 is on the better
side, for higher/lower-is-better metrics), **Cohen's d** (paired: meanΔ / SD of the paired
differences), and effect direction. `T_full_paired_stats.csv`.

> **Small-sample caveat (stated explicitly):** with **n = 11**, the exact two-sided sign
> test can only reach p < 0.05 at a split of 10/11 or 11/11 (or 0/11, 1/11). **No
> configuration reaches that on any core metric.** Cohen's d values are reported as
> *effect-size indicators*, not as significance; their confidence intervals at n = 11 are
> wide. Nothing here is claimed as "statistically significant."

### Non-activated configs (1, 2, 4)

| Config | PDR | Throughput | Delay | Jitter | PacketLoss | direction |
|---|---|---|---|---|---|---|
| **1** `x0_R=0.5, x0_L=0.02` | meanΔ −1.49, medΔ −0.77, **p 0.55**, d −0.23 | −4.1 %, d −0.23 | +4.0 %, p 1.0, d +0.21 | +4.6 %, p 1.0, d +0.26 | +2.3 %, p 0.55, d +0.23 | slightly worse / indistinguishable |
| **2** `x0_R=0.5, x0_L=0.05` | meanΔ −1.29, medΔ −0.77, **p 0.55**, d −0.21 | −3.5 %, d −0.21 | +4.0 %, p 1.0 | +4.5 %, p 1.0 | +2.0 %, p 0.55 | slightly worse / indistinguishable |
| **4** `x0_R=0.8, x0_L=0.02` | meanΔ −1.56, **medΔ +0.57**, **p 1.0**, d −0.19 | −4.3 %, d −0.19 | +1.2 %, p 1.0, d +0.05 | +2.7 %, p 1.0 | +2.5 %, p 1.0 | indistinguishable |

→ **All three are statistically and practically indistinguishable from Static** (sign-test
p ∈ {0.55, 1.0}; |d| ≤ 0.26). The small deltas are two-pass execution stochasticity
(Update #6 §11.6), not routing effects (config 1's tree is *identical* to Static's yet its
PDR differs by −1.5 points — pure execution noise).

### Activated configs (3, 5, 6)

| Config | PDR | Throughput | Delay | Jitter | PacketLoss | HopCount | AvgLU | MaxLU |
|---|---|---|---|---|---|---|---|---|
| **3** `x0_R=0.5, x0_L=0.5` (72.7 %) | meanΔ **−4.05**, medΔ **−6.74**, p 0.23, **d −0.61** → **V4 worse** | −11.1 %, d −0.61 | meanΔ −0.0067, −6.9 %, p 0.23, d −0.41 → V4 better | −5.1 %, d −0.23 → V4 better | meanΔ **+1066**, +6.4 %, p 0.23, **d +0.61** → **V4 worse** | +2.4 % (8/11 higher, d +0.97) | −2.4 % | −10.3 % |
| **5** `x0_R=0.8, x0_L=0.05` (45.5 %) | meanΔ −1.94, medΔ **+0.57**, **p 1.0**, d −0.23 | −5.3 %, d −0.23 | −0.3 %, p 1.0, d −0.01 (flat) | +0.5 %, p 1.0 | +3.0 %, p 1.0 | +1.0 % (5/11 higher, d +0.83) | +2.3 % | +8.2 % |
| **6** `x0_R=0.8, x0_L=0.5` (100 %) | meanΔ **+1.28**, **medΔ −2.55**, **p 1.0**, d +0.15 | +3.5 %, d +0.15 | meanΔ **+0.021**, **+21.6 %**, **p 0.065**, **d +0.69** → **V4 worse** | +5.5 %, p 0.55, **d +0.51** → V4 worse | −2.0 %, p 1.0, d −0.15 | **+27.9 % (11/11 higher, d +1.47)** | **+18.6 % (9/11)** | **+42.8 % (9/11, d +0.89)** |

**Directional summary of the three activated configs:**
- **Config 3** — *active, net worse on delivery.* PDR −11.1 % (d −0.61, medium-large;
  median Δ −6.7 → the typical seed is clearly lower), Packet Loss +6.4 % (d +0.61); a
  modest latency reduction (delay −6.9 %, jitter −5.1 %) does not offset the delivery loss.
- **Config 5** — *active, roughly neutral, slightly negative.* PDR −5.3 % but median Δ is
  *positive* (+0.57) and sign-test p = 1.0; delay/jitter flat; hop and MaxLU up a little.
  Best described as "no benefit, marginal cost."
- **Config 6** — *strongly active, no credible delivery gain, clear latency/path/efficiency
  cost.* PDR mean +3.5 % but **median Δ is negative (−2.55)** and p = 1.0 (the mean is
  pulled up by 2–3 seeds; the typical seed's PDR is *lower*). Paid for with **delay +21.6 %
  (d +0.69, p = 0.065 — the closest any metric comes to significance, and in the *worse*
  direction)**, jitter +5.5 % (d +0.51), **hop count +27.9 % in all 11 seeds** (d +1.47),
  AvgLinkUtil +18.6 %, MaxLinkUtil +42.8 % (d +0.89).

---

## 4. The two questions, kept separate

### 4a. Mechanism activation — *does V4 actually change routing?*

**YES.** The pre-registered criterion (route tree differs from Static in ≥ 30 % of the 11
seeds) is met by **3 of 6 configurations**. Total route-changing runs: **28 / 66**. In
Config 6 every one of the 11 seeds produces a substantially different (longer) tree. The V4
sigmoid cost function, at `k = 10`, genuinely alters the shortest-cost path Dijkstra
selects.

### 4b. Performance benefit — *when it changes the route, does performance improve?*

**NO — not on any of the eight metrics, in any activated configuration.**

- **Delivery (PDR, Throughput):** Config 3 gets clearly *worse* (−11.1 %, d −0.61);
  Config 5 is slightly worse / neutral; Config 6's mean PDR is +3.5 % but **not
  distinguishable from zero** (p = 1.0, d = +0.15) and **negative at the median**.
- **Latency (Delay, Jitter):** only Config 3 improves delay (−6.9 %, d −0.41) — and it is
  the config that loses the most delivery. Config 6, the most active, *worsens* delay by
  +21.6 % (d +0.69) and jitter by +5.5 % (d +0.51).
- **Packet Loss:** worse in Configs 3 (+6.4 %) and 5 (+3.0 %); ~flat in Config 6 (−2.0 %,
  p = 1.0).
- **Hop Count:** rises in every activated config (Config 6: +27.9 %, all 11 seeds) —
  activation = **longer paths**, by construction (the risk cost steers traffic onto
  low-degree relays).
- **Link Utilisation:** Config 6 raises Avg/Max link utilisation by +18.6 % / +42.8 % —
  activation = **more concentrated per-link load**, again by construction.

**Answer to the most important question:** *When the sigmoid actually changes the route, it
routes traffic onto longer, lower-degree, more-heavily-loaded paths — which is exactly what
a degree-avoiding cost is designed to do — but in this uniform-random 50-node IoT mesh that
does **not** translate into better packet delivery, throughput, delay, jitter, packet loss,
or link efficiency. In the two configs where routing changes substantially, performance is
either worse on delivery (Config 3) or neutral-on-delivery-at-a-large-latency-cost
(Config 6).*

---

## 5. Investigating the surprising result (from the actual sigmoid equations)

The Update #8 hypothesis was: *lowering `x0_L` toward the observed LoadScore scale (~0.008)
would engage the load term and increase routing activity.* **The data contradict this:**
`x0_L = 0.50` (the control, "load term effectively off") produced the **most** activation;
lowering `x0_L` to 0.02–0.05 **reduced** activation. Also `x0_R = 0.80` out-activated
`x0_R = 0.50` at every `x0_L`. Here is why, from `S(x) = 1/(1+e^{-k(x-x0)})` with `k = 10`
and the **observed** input ranges (link-load proxy: median ≈ 0.008, peak ≈ 0.05–0.13;
RiskScore ensemble: q05 ≈ 0.44, median ≈ 0.80, ~66 % of edges in [0.5, 0.9]):

### 5a. The load sigmoid `S_L` at `k_L = 10`

| edge load → | 0.008 | 0.03 | 0.05 | 0.09 | 0.13 | behaviour |
|---|---|---|---|---|---|---|
| `S_L`, `x0_L = 0.50` | 0.007 | 0.009 | 0.011 | 0.016 | 0.024 | **≈ 0 constant** for every edge → the `w_L·S_L` term is a fixed ≈ 0.005 offset → **load term is OFF**; `AdaptiveCost ≈ w_R·S_R + const` |
| `S_L`, `x0_L = 0.05` | 0.40 | 0.45 | 0.50 | 0.60 | 0.69 | mean ≈ 0.5; a **large additive term (~0.25 of every edge's cost)** that varies only mildly across edges |
| `S_L`, `x0_L = 0.02` | 0.47 | 0.53 | 0.57 | 0.67 | 0.75 | mean ≈ 0.55; same picture, slightly larger and steeper |

**Consequence.** At `x0_L ∈ {0.02, 0.05}` the load term adds ~0.5 to `S_L` for essentially
every edge. Because `w_L = 0.5`, this contributes ~0.25 to *every* edge's `AdaptiveCost`.
This term (i) does **not discriminate** usefully — link loads span a narrow band, so `S_L`
only ranges ~0.4–0.75 — and (ii) it **inflates the total path cost roughly uniformly**, so
the risk-cost *differences* between candidate paths become a **smaller fraction of the total
path cost** that Dijkstra compares. A risk-avoiding detour that was "worth it" under a
pure-risk cost is now often outweighed by the extra hop's inflated cost. Additionally, the
Pass-1 load is measured under **baseline BFS routing**, so the loaded edges *are the
shortest-hop tree's own edges* — a self-referential signal that mildly penalises the BFS
tree but does not point to any better alternative. **Net effect: engaging the load term at
these midpoints dilutes, rather than augments, the routing signal → fewer route changes.**
At `x0_L = 0.5` the load term vanishes, leaving a clean, full-weight risk cost → **more
route changes.**

### 5b. The risk sigmoid `S_R` at `k_R = 10`

| RiskScore → | 0.44 (q05) | 0.60 | 0.70 | 0.80 (median) | 0.90 | 1.00 (q95) | behaviour |
|---|---|---|---|---|---|---|---|
| `S_R`, `x0_R = 0.50` | 0.354 | 0.731 | 0.881 | 0.953 | 0.982 | 0.993 | across the RiskScore **bulk (0.6–1.0)**: `S_R` ≈ **0.73–0.99** — near-saturated, **weak discrimination among the common edges**; only rare low-degree edges (RiskScore < 0.5) get a distinctly lower cost |
| `S_R`, `x0_R = 0.80` | 0.027 | 0.119 | 0.269 | **0.500** | 0.731 | 0.881 | across the RiskScore **bulk (0.6–1.0)**: `S_R` ≈ **0.12–0.88** — the sigmoid's **steep region sits exactly on the data** → **strong per-edge discrimination**: two typical edges differing by 0.1 in RiskScore now differ by ~0.2–0.25 in cost |

**Consequence.** RiskScore is concentrated around its median ≈ 0.80. Placing `x0_R` at 0.5
puts the steep part of the sigmoid *below* where the edges are, so most edges land on the
flat saturated shoulder and get near-identical costs — Dijkstra can only exploit the rare
low-RiskScore edges. Placing `x0_R` at 0.80 puts the steep part *on* the bulk, so the cost
faithfully tracks relative degree across the edges Dijkstra actually chooses between →
**more route changes.** This part of the Update #8 hypothesis (re-centring `x0_R` helps)
**is confirmed.**

### 5c. Why the six configs rank as they do

Route change increases with **(i) `x0_R` closer to the RiskScore median** (0.80 > 0.50 at
every `x0_L`) and **(ii) `x0_L` further from the load scale** (0.50 ≫ 0.05 ≳ 0.02), because
(i) sharpens the useful signal and (ii) removes a diluting term. The most active config
(`x0_R = 0.80, x0_L = 0.50`) has the sharpest risk discrimination and no load dilution →
100 % of seeds re-routed. The least active (`x0_R = 0.50, x0_L = 0.02`) has the flattest
risk response *and* the strongest dilution → 0 %.

**The Update #8 hypothesis was directionally right about `k` and `x0_R`, and wrong in sign
about `x0_L`.** The error was conceptual: "activating the load term" was assumed to add
routing information, but for this load regime the load term adds a near-uniform cost that
*subtracts* discriminative power. The Update #8 *arithmetic* (§5: `S_L` spread ≤ 0.043 at
`x0_L = 0.5`; observed loads ≪ 0.5) was correct — only the inference from it was wrong.

---

## 6. Stage-1 vs Tier-1 — what `k`, `x0_R`, `x0_L` each contribute

| | Stage-1 (`k_R, k_L ≤ 5`; `x0_R = x0_L = 0.5`; 27 configs) | Tier-1 (`k_R = k_L = 10`; `x0_R ∈ {0.5, 0.8}`; `x0_L ∈ {0.02, 0.05, 0.5}`; 6 configs) |
|---|---|---|
| Route-changing runs | **1 / 297** | **28 / 66** |
| Direct `k`-only contrast (`x0_R = x0_L = 0.5`, `w = 0.5`) | `k = 5`: ~1 changed seed total across the grid | `k = 10`: **8 / 11 seeds changed (72.7 %)** |

- **Steepness `k` is the decisive lever.** With everything else identical (`x0_R = x0_L =
  0.5`, `w = 0.5`), raising `k` from 5 to 10 flips the mechanism from inert (≈ 1/297) to
  active (8/11). This matches Update #8's diagnosis: at `k ≤ 5` the sigmoid is too gentle
  for RiskScore's narrow high band (`S_R` spread over the RiskScore distribution ≈ 0.48 at
  `k = 5`; ≈ 0.63–0.85 at `k = 10`). The practical threshold is roughly `k ≳ 8–10`.
- **Risk midpoint `x0_R` modulates *how much* activation, given sufficient `k`.** Moving
  `x0_R` from 0.5 to ≈ the RiskScore median (0.8) increases route change at every `x0_L`
  (e.g. 0 % → 27 % at `x0_L = 0.02`; 72.7 % → 100 % at `x0_L = 0.5`). Confirms the Update #8
  prediction.
- **Load midpoint `x0_L` behaves opposite to the Update #8 prediction.** `x0_L = 0.5`
  (load term ≈ off) is *most* active; pulling `x0_L` down to the load scale *reduces*
  activity by adding a diluting near-uniform cost. The load term, as currently defined
  (small, weakly-varying, Pass-1/self-referential), does not supply useful routing
  discrimination in this regime — engaging it hurts.

**Take-away:** the mechanism can be made *active* by using a sufficiently steep `k` and
centring `x0_R` on the RiskScore distribution; the **load** half of the composite metric
does not currently contribute — it is either inert or counter-productive.

---

## 7. A / B / C / D decision

> **A** — activated mechanism with promising performance
> **B** — activated mechanism but no performance benefit / performance worsens
> **C** — mechanism activation remains insufficient
> **D** — evidence still insufficient to decide

| Option | Assessment |
|---|---|
| **A** | **No.** No activated configuration shows promising performance. The one config with a positive mean PDR (Config 6, +3.5 %) is non-significant (sign-test p = 1.0, d = +0.15), negative at the median, and comes with delay +21.6 % (d +0.69), hop count +27.9 % (all 11 seeds), MaxLinkUtil +42.8 %. |
| **C** | **No.** 3 of 6 configs cleared the pre-registered 30 % route-change threshold; 28/66 route-changing runs (vs 1/297 in Stage-1). Activation is demonstrated, not insufficient. |
| **D** | **Partly** — for the *broader* question (only one network condition, one weight, two `k` values; the load term never usefully engaged; traffic/topology sensitivity of activation untested). But for the *specific* question "does activated V4 improve performance at this condition?", the evidence is sufficient and points to **no**. |
| **B** | **Yes — this is the match.** The mechanism activates (§4a), and in the configurations where routing changes substantially, performance is **not improved**: Config 3 is clearly worse on delivery (PDR −11.1 %, d −0.61); Config 6 restructures every path (+27.9 % hop count) and worsens latency (+21.6 % delay, d +0.69) and link utilisation (+42.8 %) for a delivery change indistinguishable from zero. Non-activated/weakly-activated configs are neutral. |

### **Decision: B** — *activated mechanism, but no performance benefit; the
### strongly-activated configurations trend harmful (delivery loss, or large latency /
### path-length / link-utilisation cost for no credible delivery gain).*

(With a **D-flavoured caveat**: this is one condition, one weight, `k ∈ {5, 10}`; the load
term was never in a regime where it could both discriminate and correlate with genuine
congestion.)

---

## 8. Is Tier-2 scientifically justified?

**No — not as a performance-improvement search.** Every one of the disqualifying reasons
the task itself lists applies to the Tier-1 result:

- *activation is demonstrated but performance is not promising* — yes (§4b, §7);
- *route changes increase hop count* — yes, in every activated config (Config 6: +27.9 %,
  all 11 seeds);
- *no consistent metric improvement* — yes, no activated config improves any of the 8
  metrics with a credible, consistent effect;
- *mechanism is active but not beneficial* — yes (Decision B).

There is **one** narrow open question: *could the **load** term ever contribute usefully
under **heavier traffic**, where link loads might rise toward a midpoint at which `S_L`
both discriminates across edges and correlates with genuine congestion?* Tier-1 could not
test this (traffic held at `medium`; the risk term — the part that works — already shows
activation ⇒ neutral/worse performance). A decision to pursue that question is a **fresh
scope decision**, not something the Tier-1 evidence motivates, and it is weakened in
advance by (a) the Pass-1 self-referential-load limitation (Update #8 §9) and (b) Update
#7's projection that even `high` traffic keeps peak link load ≈ 0.15 — still low relative
to any midpoint where `S_L` becomes both steep and meaningful.

**If** it were pursued anyway, the smallest defensible test would be: the single
least-penalising active config from Tier-1 (`x0_R = 0.8`), run at `trafficLevel = high`,
50 nodes, static, seeds 20–30, with `x0_L ∈ {0.05, 0.15, 0.50-control}` — 3 × 11 = **33
runs** — under a pre-registered rule: *proceed further only if some config shows route
activation **and** improves ≥ 1 core metric **and** degrades no lower-is-better metric
(Delay, Jitter, Packet Loss) by > 10 %; otherwise stop.* **This is not run, and is not
recommended.**

---

# FINAL RECOMMENDATION

- **Tier-1 result.** 66/66 runs completed and audited clean. With `k_R = k_L = 10`, the
  V4 sigmoid cost function **activates** — 3 of 6 configurations changed the route tree in
  ≥ 30 % of seeds (28/66 route-changing runs, vs 1/297 across the entire Stage-1 `k ≤ 5`
  grid). Activation is driven by **steep `k` (≈ 10)** plus **centring `x0_R` on the
  RiskScore median (~0.8)**; **lowering `x0_L` did *not* help** — it added a near-uniform
  cost that diluted the risk signal, so `x0_L = 0.5` (load term effectively off) was the
  most active. This contradicts the Update #8 `x0_L` hypothesis, and §5 explains why from
  the sigmoid equations and the observed input ranges.

- **Mechanism status:** **ACTIVE and tunable.** It is *not* intrinsically inert — the
  Stage-1 inertness was a `k`/centring artefact, now understood. With appropriate `k` and
  `x0_R` it produces genuinely distinct, risk-aware route trees.

- **Performance status:** **NO demonstrated benefit; trending harmful when strongly
  active.** In no activated configuration does the route change improve PDR, Throughput,
  Delay, Jitter, Packet Loss, Hop Count, or Link Utilisation with a consistent, credible
  effect. The most active config (`x0_R = 0.8, x0_L = 0.5`) lengthens every path (+27.9 %
  hop count), raises latency (+21.6 % delay, d +0.69, p = 0.065 — the nearest thing to a
  significant result, and in the *worse* direction) and link utilisation (+42.8 %), for a
  PDR change that is not distinguishable from zero and is negative at the median. Another
  active config (`x0_R = 0.5, x0_L = 0.5`) loses delivery outright (PDR −11.1 %, d −0.61).
  n = 11 per config — no result is statistically significant; the pattern of medium-to-large
  effect sizes with wide uncertainty points consistently to *no gain, some cost*.

- **A / B / C / D decision:** **B** — *activated mechanism, but no performance benefit;
  strongly-activated configurations trend harmful.* (D-flavoured caveat: one condition, one
  weight, `k ∈ {5, 10}`; load term never usefully engaged.)

- **Is Tier-2 justified?** **No.** Activation is demonstrated *and* performance is not
  promising *and* route changes increase hop count *and* there is no consistent metric
  improvement — i.e. the mechanism is *active but not beneficial* at the tested condition.
  A further screen is not motivated by this evidence. The one residual question (load term
  under heavier traffic) is a separate scope decision, not a Tier-1 follow-through, and is
  weakened by the Pass-1 load limitation and the low projected high-traffic link loads.

- **Recommended next research step:** **close the V4 investigation and write it up** with
  the now-complete and honest characterisation:
  > *V4 implements a sigmoid-weighted, offline (two-pass) route-selection metric combining a
  > topological degree-risk term and a Pass-1-measured link-load term. At low sigmoid
  > steepness (`k ≤ 5`, `x0 = 0.5`) the metric is inert — its Dijkstra tree is
  > indistinguishable from unweighted shortest-hop (Static) routing (1/297 runs changed).
  > At `k = 10` with the risk-sigmoid midpoint re-centred on the observed degree
  > distribution, the metric activates and produces genuinely distinct risk-aware route
  > trees (28/66 runs changed). However, at the tested IoT-mesh condition (50 nodes, medium
  > traffic, static) this activation confers no measurable performance benefit: activated
  > routing steers traffic onto longer, lower-degree, more-heavily-loaded paths — as
  > designed — but delivers no improvement in packet delivery, throughput, delay, jitter,
  > packet loss, or link efficiency, and the most strongly activated configuration trades a
  > ~28 % path-length and ~22 % delay increase for a delivery change indistinguishable from
  > zero. The load half of the composite metric was found to be either inert or, when
  > engaged at a low midpoint, counter-productive (it dilutes the risk signal).*

  The V3 Official Baseline (audited, 1,782 runs) plus this V4 characterisation form a
  complete, defensible thesis contribution. Any resumption of V4 work (e.g. a genuinely
  reactive design per Update #5 §J, or a different composite metric) would be a **new**
  research question requiring its own approval and design.

---

## Confirmations

| Item | State |
|---|---|
| Tier-1 runs | **66 / 66 completed**, 0 failed |
| Simulations rerun in this analysis step | **none** — analysis of the existing 66-run dataset only |
| Existing datasets modified | **none** — 0 files under `results/` have a 2026-09-08 mtime |
| V3 official | **intact — 1,782 rows** (seeds 20–30) |
| V4 sensitivity | **intact — 297 rows** |
| V4 matched | **intact — 594 rows** |
| Update #7 / Update #8 (design-decision) artifacts | **intact** (25 + 7 files unchanged) |
| Source / runner / dashboard | **unchanged** — `scratch/iot-network-v3-ext.cc`, `experiments/*` runners, `experiments/v3_checksum_guard.py`, `results/v3ext_checksum_manifest.json`, `dashboard/*` all `git diff`-clean (dashboard unchanged since Update #2) |
| Git status | **27 tracked working-tree changes, unchanged from Updates #3–#8**; only new content is the untracked `analysis/update8-tier1-activation/`. No `git add`, commit, or push. |
| Unrelated experiments | **none** — only the 66 approved `--protocol=v4` runs at 50/medium/static |

### Files in `analysis/update8-tier1-activation/`

`run_tier1_screen.sh` · `run_master.log` · `nohup.out` · `data/v4_50_medium_static.csv`
(66 rows) · `data/logs/*.log` (66) · `analyze_tier1.py` · `T_tier1_activation_and_perf.csv`
· `T_full_paired_stats.csv` · `integrity_and_digest.json` · `git_status_snapshot.txt` ·
`plots/fig1_route_change_by_config.png` · `plots/fig_{PDR,Throughput,Delay,PacketLoss}_by_config.png`
· `UPDATE8_TIER1_ACTIVATION_SCREEN.md` (this report)

**STOP.** No Tier-2, Dashboard Update #1, V6, or further statistical analysis without
explicit approval.
