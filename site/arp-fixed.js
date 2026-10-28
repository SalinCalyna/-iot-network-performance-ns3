// ARP-fixed IEEE 802.11b section. Every number comes from data/arp-fixed.json, built by
// experiments/wifi-std/build_site_arp_fixed.py from the verified ARP-fixed analysis outputs (tested by
// experiments/wifi-std/test_site_arp_fixed.py). No original (ARP-affected) value is read here.
// Confidence intervals are drawn only for 11-seed cells; 3-seed cells are shown as means without an interval.
(function () {
  const AF_COLORS = { aodv: "var(--aodv)", olsr: "var(--olsr)", static: "var(--static)", offered: "#7a828e" };   // neutral grey for the offered-load reference line (no grey variable exists)
  let AF = null, afTraffic = "high", afBnTraffic = "high", afRateN = 50;

  function caption(container, html) {
    let cap = container.parentNode.querySelector(":scope > .ci-caption");
    if (!cap) { cap = document.createElement("div"); cap.className = "ci-caption"; container.insertAdjacentElement("afterend", cap); }
    cap.innerHTML = html;
  }
  function intervalNote(container, seeds) {
    if (seeds === 11) ciCaption(container, "band", "High traffic: seeds 20–30.");
    else caption(container, "3 seeds (20, 25, 30): descriptive only, so no interval is drawn.");
  }
  function series(metric, t, scale) {
    const k = scale || 1, out = {};
    ["aodv", "olsr", "static"].forEach(p => {
      out[p] = AF[metric][t][p].map(d => {
        const pt = { x: d.n, y: d.mean * k, n: d.seeds };
        if (d.ci != null) pt.ci = d.ci * k;
        return pt;
      });
    });
    return out;
  }
  function drawProtocolCharts() {
    const t = afTraffic, seeds = AF.pdr[t].static[0].seeds;
    const base = { colors: AF_COLORS, xNumeric: true, xtitle: "Number of sensor nodes (N)" };
    const c1 = document.getElementById("chart-af-pdr");
    lineChart(c1, series("pdr", t), { ...base, unit: "%", yfmt: 0, ytitle: "PDR (%)" });
    intervalNote(c1, seeds);
    const c2 = document.getElementById("chart-af-goodput");
    const g = series("goodput", t);
    g.offered = AF.goodput[t].static.map(d => ({ x: d.n, y: d.offered }));
    lineChart(c2, g, { ...base, unit: " kbit/s", yfmt: 0, ytitle: "Goodput (kbit/s)" });
    intervalNote(c2, seeds);
    const c3 = document.getElementById("chart-af-delay");
    lineChart(c3, series("delay", t), { ...base, unit: " ms", yfmt: 0, ytitle: "Mean delay of delivered packets (ms)" });
    intervalNote(c3, seeds);
  }
  function drawAirtime() {
    const t = afBnTraffic, c = document.getElementById("chart-af-airtime");
    const pts = p => AF.bottleneck[`${p}-${t}`].map(d => ({ x: d.n, y: d.gw_airtime * 100, ci: d.gw_airtime_ci * 100, n: d.seeds }));
    groupedBar(c, { olsr: pts("olsr"), static: pts("static") },
      { colors: AF_COLORS, unit: "%", yfmt: 0, xlabel: x => `N=${x}`, ytitle: "Gateway airtime (% busy)", xtitle: `Number of sensor nodes (N), ${t} traffic` });
    ciCaption(c, "bar", "Seeds 20–30.");
  }
  function drawRate() {
    const c = document.getElementById("chart-af-rate");
    const pts = p => AF.ratesweep[`${p}-${afRateN}`].map(d => ({ x: d.rate + "k", y: d.pdr, n: d.seeds }));
    lineChart(c, { olsr: pts("olsr"), static: pts("static") },
      { colors: AF_COLORS, unit: "%", yfmt: 0, ytitle: "PDR (%)", xtitle: `Offered rate per sensor (kbit/s), N = ${afRateN}` });
    caption(c, "3 seeds (20, 25, 30) per point: descriptive only, so no interval is drawn.");
  }
  async function init() {
    if (!document.getElementById("view-arp-fixed")) return;
    try {
      const r = await fetch("data/arp-fixed.json");
      if (!r.ok) throw new Error(r.status);
      AF = await r.json();
    } catch (e) {
      document.getElementById("af-status").textContent = "The ARP-fixed data file could not be loaded.";
      return;
    }
    legend(document.getElementById("af-legend"), [["AODV", "var(--aodv)"], ["OLSR", "var(--olsr)"], ["Static", "var(--static)"], ["Offered load (goodput chart)", AF_COLORS.offered]]);
    legend(document.getElementById("af-bn-legend"), [["OLSR", "var(--olsr)"], ["Static", "var(--static)"]]);
    legend(document.getElementById("af-rate-legend"), [["OLSR", "var(--olsr)"], ["Static", "var(--static)"]]);
    const T = ["low", "medium", "high"];
    pillGroup(document.getElementById("af-traffic"), ["Low (4 kbit/s)", "Medium (8)", "High (16)"], T.indexOf(afTraffic), i => { afTraffic = T[i]; drawProtocolCharts(); });
    pillGroup(document.getElementById("af-bn-traffic"), ["Medium", "High"], afBnTraffic === "high" ? 1 : 0, i => { afBnTraffic = i ? "high" : "medium"; drawAirtime(); });
    pillGroup(document.getElementById("af-rate-n"), ["50", "75", "100"], [50, 75, 100].indexOf(afRateN), i => { afRateN = [50, 75, 100][i]; drawRate(); });
    drawProtocolCharts();
    drawAirtime();
    drawRate();
  }
  document.addEventListener("DOMContentLoaded", init);
})();
