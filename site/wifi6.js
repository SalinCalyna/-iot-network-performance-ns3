// Wi-Fi 6 Risk-Aware Routing sections. Every number comes from data/wifi6-risk.json, built by
// experiments/wifi6-risk/build_site_wifi6.py (ns-3-dev, branch exp/wifi6-arp) from validated analysis outputs; the
// JSON lists each source file with its sha256. N = 30 (n = 10) is inferential; N = 100 (n = 3) is descriptive only:
// no p-value is ever rendered for it.
(function () {
  "use strict";
  let W6 = null;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = id => document.getElementById(id);
  const num = (x, d) => (x < 0 ? "−" : "") + Math.abs(x).toFixed(d);
  const sgn = (x, d) => (x > 0 ? "+" : x < 0 ? "−" : "±") + Math.abs(x).toFixed(d);
  const pfmt = p => p.toPrecision(3);
  // display labels for raw CSV column names (cells are shown verbatim)
  const HEAD = { k: "k", variant: "Variant", delivered: "Delivered (pkts)", p99_ms: "p99 delay (ms)", max_delay_s: "Max delay (s)",
    gt10s: "Delayed > 10 s (pkts)", version: "Version", seed: "Seed", sink_delivered: "Delivered (pkts)", gt10s_per_100k: "> 10 s per 100k delivered",
    sink_minus_fm: "Sink − FlowMonitor rx (pkts)", bar_psdus: "BAR PSDUs", case: "Case", mechanism: "Mechanism", longest_hold: "Longest hold",
    status: "Status", validation_batch: "Validation batch", checks_passed: "Checks passed", checks_failed: "Checks failed", decision: "Decision",
    parameter: "Parameter", value: "Value", source_or_check: "Source / check", metric: "Metric", quantity: "Quantity", statement: "Statement",
    evidence: "Evidence", limitation: "Limitation", description: "Description", consequence: "Consequence for conclusions", category: "Category" };
  const NUMERIC = /^[−+\-±]?\d[\d,.]*(\s|%|$)|^\d/;

  function rawTable(el, t, opts) {
    opts = opts || {};
    if (!el || !t) return;
    const cols = opts.cols || t.header.map((_, i) => i);
    const head = "<thead><tr>" + cols.map(i => `<th>${esc(HEAD[t.header[i]] || t.header[i])}</th>`).join("") + "</tr></thead>";
    const body = t.rows.map(r => "<tr>" + cols.map(i => {
      let v = r[i];
      if (opts.statusCol === i) {
        const cls = v === "Confirmed" ? "measured" : v === "Hypothesis" ? "planned" : "repro";
        return `<td><span class="tag ${cls}">${esc(v)}</span></td>`;
      }
      return `<td${NUMERIC.test(v) && i > 0 ? ' class="num"' : ""}>${esc(v)}</td>`;
    }).join("") + "</tr>").join("");
    el.innerHTML = head + "<tbody>" + body + "</tbody>";
  }

  function pills(container, options, active, onChange) {
    container.innerHTML = "";
    options.forEach((o, i) => {
      const b = document.createElement("button");
      b.className = "pill" + (i === active ? " active" : "");
      b.type = "button";
      b.textContent = o;
      b.addEventListener("click", () => {
        [...container.children].forEach(c => c.classList.remove("active"));
        b.classList.add("active");
        onChange(i);
      });
      container.appendChild(b);
    });
  }

  const B = n => W6.batches[String(n)];
  const metric = k => W6.metrics.find(m => m.key === k);
  const pair = (n, k, m) => B(n).paired.find(x => x.k === k && x.metric === m);
  const cfg = (n, p, k) => B(n).configs.find(c => c.protocol === p && c.k === k);
  const nLabel = n => `N = ${n} · seeds ${B(n).seeds[0]}–${B(n).seeds[B(n).seeds.length - 1]} · n = ${B(n).n_seeds}`;
  const intervalName = n => (B(n).inferential ? "95 % confidence interval (Student t)" : "descriptive 95 % t interval");

  function renderOverview() {
    const p30 = pair(30, 3, "pdr_nominal_pct"), e30 = pair(30, 3, "exposure_rate_pct");
    const p100 = pair(100, 3, "pdr_nominal_pct"), e100 = pair(100, 3, "exposure_rate_pct");
    $("w6-kf-main").innerHTML = `<span class="kf-label">Key Finding</span><span>At N = 30 (10 seeds), with k = 3 high-risk relays, Risk-Aware raised nominal PDR by <strong>${sgn(p30.diff[0], 2)} pp</strong> [95 % CI ${sgn(p30.diff[2], 2)}, ${sgn(p30.diff[3], 2)}] and cut risk exposure by <strong>${num(-e30.diff[0], 2)} pp</strong> versus Static, in ${p30.higher}/${p30.n_pairs} matched pairs (exact Wilcoxon p = ${pfmt(p30.p_wilcoxon)}, Holm-adjusted ${pfmt(p30.p_holm)}). At N = 100 the same direction was observed in ${p100.higher}/${p100.n_pairs} seeds (${sgn(p100.diff[0], 2)} pp, descriptive only).</span>`;
    const runs = B(30).denominators.runs + B(100).denominators.runs;
    const kpi = (val, unit, label, note, color) => `<div class="kpi"><div class="num"${color ? ` style="color:${color}"` : ""}>${val}<span class="unit">${unit}</span></div><div class="label">${label}</div><div class="note">${note}</div></div>`;
    $("w6-kpis").innerHTML =
      kpi(sgn(p30.diff[0], 2), "pp", "PDR gain · N=30 · k=3", `95 % CI [${sgn(p30.diff[2], 2)}, ${sgn(p30.diff[3], 2)}] · n = ${p30.n_pairs} pairs`, "var(--ok)") +
      kpi(sgn(e30.diff[0], 2), "pp", "Exposure change · N=30 · k=3", `95 % CI [${sgn(e30.diff[2], 2)}, ${sgn(e30.diff[3], 2)}] · n = ${e30.n_pairs} pairs`, "var(--ok)") +
      kpi(sgn(p100.diff[0], 2), "pp", "PDR gain · N=100 · k=3", `descriptive [${sgn(p100.diff[2], 2)}, ${sgn(p100.diff[3], 2)}] · n = ${p100.n_pairs} · exposure ${sgn(e100.diff[0], 2)} pp`) +
      kpi(runs, "runs", "Validated runs", `N=30: ${B(30).denominators.runs} · N=100: ${B(100).denominators.runs} · 4 protocols × k = 0–3`);
    const d30 = B(30).denominators, d100 = B(100).denominators;
    $("w6-denominators").textContent = `In all ${d30.runs + d100.runs} main runs no scheduled packet went unsent (max unsent at source: ${Math.max(d30.max_unsent_at_source, d100.max_unsent_at_source)}), so nominal PDR equals sink-based PDR exactly (max difference ${Math.max(d30.max_abs_sink_minus_nominal_pp, d100.max_abs_sink_minus_nominal_pp).toFixed(2)} pp). FlowMonitor is not used for PDR (it undercounts by up to ${Math.max(d30.max_sink_minus_flowmonitor_pkts, d100.max_sink_minus_flowmonitor_pkts)} packet per run here).`;
    rawTable($("w6-t-params"), W6.tables["T-W1_parameters"]);
  }

  let resN = 30, resM = 0;
  function renderResults() {
    const m = W6.metrics[resM], b = B(resN);
    $("w6-res-title").textContent = `${m.label} (${m.unit}) — ${nLabel(resN)}`;
    $("w6-res-sub").textContent = `Cells: mean ± SD [${intervalName(resN)}]. ` + (b.inferential ? "" : "Three seeds: the interval is a descriptive range, not evidence of significance. ") +
      (m.key.startsWith("delay") || m.key.startsWith("mean_hops") ? "Over delivered packets only (survivorship: see Cost of risk avoidance)." : m.key === "pdr_nominal_pct" ? "Nominal PDR = delivered ÷ scheduled packets." : "");
    const head = "<thead><tr><th>Protocol</th>" + [0, 1, 2, 3].map(k => `<th>k = ${k}</th>`).join("") + "</tr></thead>";
    const body = W6.protocols.map(p => "<tr><td>" + esc(p.label) + "</td>" + [0, 1, 2, 3].map(k => {
      const v = cfg(resN, p.key, k)[m.key];
      return `<td class="num">${num(v[0], m.digits)} <span style="color:var(--text-faint)">± ${v[1].toFixed(m.digits)}</span><br><span style="color:var(--text-faint);font-size:.72rem">[${num(v[2], m.digits)}, ${num(v[3], m.digits)}]</span></td>`;
    }).join("") + "</tr>").join("");
    $("w6-res-table").innerHTML = head + "<tbody>" + body + "</tbody>";
  }

  let pairN = 30;
  function renderPaired() {
    const b = B(pairN), inf = b.inferential;
    $("w6-pair-title").textContent = `Risk-Aware − Static, ${nLabel(pairN)}`;
    $("w6-pair-sub").textContent = inf
      ? "Mean difference with 95 % confidence interval (paired t), pairs where Risk-Aware is higher/equal/lower, Cohen's d_z, exact two-sided Wilcoxon p. Holm adjustment applies to the primary family only (nominal PDR and exposure, k = 1–3); other p-values are secondary and unadjusted. With n = 10 the smallest attainable exact p is 0.00195."
      : "Descriptive only: mean difference with the descriptive 95 % t interval and every per-seed difference. No hypothesis test is reported for three seeds and no significance is claimed.";
    const cols = ["k", "Metric", "Static", "Risk-Aware", "Difference", inf ? "95 % CI" : "Descriptive interval", "Higher / equal / lower"]
      .concat(inf ? ["d_z", "Wilcoxon p", "Holm p"] : ["Per-seed difference"]);
    const head = "<thead><tr>" + cols.map(c => `<th>${esc(c)}</th>`).join("") + "</tr></thead>";
    const order = m => W6.metrics.findIndex(x => x.key === m);
    const body = b.paired.slice().sort((x, y) => x.k - y.k || order(x.metric) - order(y.metric)).map(x => {
      const m = metric(x.metric), d = m.digits;
      const cells = [x.k, `${m.label} (${m.unit})`, num(x.static_mean, d), num(x.riskaware_mean, d), sgn(x.diff[0], d),
        `[${sgn(x.diff[2], d)}, ${sgn(x.diff[3], d)}]`, `${x.higher} / ${x.equal} / ${x.lower}`];
      if (inf) cells.push(sgn(x.cohen_dz, 2), pfmt(x.p_wilcoxon), x.p_holm == null ? "— (secondary)" : pfmt(x.p_holm));
      else cells.push(x.per_seed.split(" ").map(t => { const [s, v] = t.split(":"); return `${s}: ${sgn(parseFloat(v), d)}`; }).join(" · "));
      const primary = (x.metric === "pdr_nominal_pct" || x.metric === "exposure_rate_pct");
      return `<tr${primary ? ' style="font-weight:600"' : ""}>` + cells.map((c, i) => `<td${i > 1 ? ' class="num"' : ""}>${esc(c)}</td>`).join("") + "</tr>";
    }).join("");
    $("w6-pair-table").innerHTML = head + "<tbody>" + body + "</tbody>";
    const p = k => pair(30, k, "pdr_nominal_pct");
    $("w6-kf-paired").innerHTML = `<span class="kf-label">Measured</span><span>N = 30: Risk-Aware's nominal PDR is higher than Static's in ${p(1).higher}/${p(1).n_pairs}, ${p(2).higher}/${p(2).n_pairs} and ${p(3).higher}/${p(3).n_pairs} pairs at k = 1, 2, 3 (Holm-adjusted p = ${[1, 2, 3].map(k => pfmt(p(k).p_holm)).join(", ")}). N = 100: higher in ${pair(100, 1, "pdr_nominal_pct").higher}/3, ${pair(100, 2, "pdr_nominal_pct").higher}/3 and ${pair(100, 3, "pdr_nominal_pct").higher}/3 seeds — consistent in direction, descriptive only.</span>`;
  }

  function renderCost() {
    const hc = W6.hop_check;
    const head = "<thead><tr><th>Network</th><th>Protocol</th><th>Packets</th>" + [0, 1, 2, 3].map(k => `<th>k = ${k}</th>`).join("") + "</tr></thead>";
    const lab = p => p === "static" ? "Static" : "Risk-Aware";
    const body = hc.map(h => ["delivered", "all_sent"].map(kind => `<tr><td>${esc(h.n)}</td><td>${lab(h.protocol)}</td><td>${kind === "delivered" ? "delivered" : "all sent"}</td>` +
      h[kind].map(v => `<td class="num">${v.toFixed(3)}</td>`).join("") + "</tr>").join("")).join("");
    $("w6-hop-table").innerHTML = head + "<tbody>" + body + "</tbody>";
    const g = (n, p) => hc.find(h => h.n.startsWith(`N = ${n} `) && h.protocol === p);
    const r30 = g(30, "riskaware").all_sent, s100 = g(100, "static").all_sent, r100 = g(100, "riskaware").all_sent;
    $("w6-hop-note").innerHTML = `<strong>N = 30:</strong> Risk-Aware lengthens paths for real — ${r30[0].toFixed(2)} → ${r30[3].toFixed(2)} links over all sent packets at k = 3; the rest of its delivered-hop difference versus Static is survivorship. <strong>N = 100:</strong> no real lengthening — Risk-Aware's all-sent path length equals Static's (${r100[3].toFixed(3)} vs ${s100[3].toFixed(3)} links at k = 3), because equal-length safe detours exist at this density.`;
  }

  function renderAodv() {
    const t = W6.tables;
    rawTable($("w6-t-aodv-a"), t["T-W6a_aodv_vs_olsr_n100"]);
    rawTable($("w6-t-aodv-b"), t["T-W6b_aodv_diagnostic_seed20"]);
    rawTable($("w6-t-aodv-c"), t["T-W6c_aodv_findings_status"], { statusCol: 0 });
    const a = cfg(100, "aodv", 0).pdr_nominal_pct, o = cfg(100, "olsr", 0).pdr_nominal_pct;
    const row = lbl => t["T-W6b_aodv_diagnostic_seed20"].rows.find(r => r[0] === lbl);
    const pdr = row("Nominal PDR (%)"), air = row("Gateway airtime");
    $("w6-kf-aodv").innerHTML = `<span class="kf-label">Measured</span><span>At N = 100, k = 0 (3 seeds): AODV nominal PDR ${num(a[0], 2)} ± ${a[1].toFixed(2)} % vs OLSR ${num(o[0], 2)} ± ${o[1].toFixed(2)} %. Turning the Block Ack modification off (seed 20) left the collapse in place: PDR ${pdr[1]} % (off) vs ${pdr[2]} % (on), gateway airtime ${air[1]} vs ${air[2]}. The likely mechanism is a routing-repair feedback loop — a hypothesis, not an isolated cause.</span>`;
  }

  function renderValidity() {
    const t = W6.tables;
    rawTable($("w6-t-ba-a"), t["T-W2a_ba_defect_n30"]);
    rawTable($("w6-t-ba-b"), t["T-W2b_residual_tail_n100_64k"]);
    rawTable($("w6-t-ba-c"), t["T-W2c_tail_mechanisms"]);
    rawTable($("w6-t-ba-d"), t["T-W2d_validation"]);
    rawTable($("w6-t-load"), t["T-W3_load_calibration"]);
    rawTable($("w6-t-lim"), t["T-W7_limitations"], { cols: [0, 1, 2] });
    const files = Object.keys(W6.sources).length;
    $("w6-provenance").innerHTML = `Provenance: ${esc(W6.generated_by)}; ${files} validated source files with sha256 in <a href="data/wifi6-risk.json">data/wifi6-risk.json</a>. Batches: <code>${esc(B(30).batch)}</code>, <code>${esc(B(100).batch)}</code>.`;
  }

  function renderFigures() {
    document.querySelectorAll("figure.w6-fig").forEach(f => {
      const fig = W6.figures[f.dataset.fig];
      if (!fig) { f.innerHTML = '<p class="panel-sub">Figure unavailable.</p>'; return; }
      f.innerHTML = `<a href="${esc(fig.src)}" target="_blank" rel="noopener"><img src="${esc(fig.src)}" alt="${esc(f.dataset.fig.replace(/_/g, " "))}" loading="lazy"></a>` +
        `<figcaption><strong>${esc(f.dataset.fig.split("_")[0])}.</strong> ${esc(fig.caption)} <span class="w6-src">Source: ${esc(fig.source)}</span></figcaption>`;
    });
  }

  async function init() {
    if (!$("view-w6-overview")) return;
    try {
      W6 = await fetch("data/wifi6-risk.json").then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
    } catch (e) {
      console.warn("wifi6-risk.json unavailable:", e);
      document.querySelectorAll('[id^="w6-"]').forEach(el => { if (el.textContent.trim() === "—") el.textContent = "Data file unavailable."; });
      return;
    }
    renderOverview();
    pills($("w6-res-n"), ["N = 30 · n = 10", "N = 100 · n = 3"], 0, i => { resN = i ? 100 : 30; renderResults(); });
    pills($("w6-res-m"), W6.metrics.map(m => m.label), 0, i => { resM = i; renderResults(); });
    renderResults();
    pills($("w6-pair-n"), ["N = 30 · n = 10 · inferential", "N = 100 · n = 3 · descriptive"], 0, i => { pairN = i ? 100 : 30; renderPaired(); });
    renderPaired();
    renderCost();
    renderAodv();
    renderValidity();
    renderFigures();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
