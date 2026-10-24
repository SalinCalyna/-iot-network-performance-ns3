// Headless-Chrome QA for the static dashboard (no npm dependencies; Chrome DevTools Protocol over WebSocket).
//
//   node --experimental-websocket experiments/dashboard/browser_check.mjs <url> <out dir> [width,width,...] [--axe]
//
// For every viewport width (default 1440,768,390) it records, into <out dir>/report-<width>.json:
//   console errors/warnings and uncaught exceptions, failed or >= 400 network requests,
//   document width vs viewport (horizontal overflow) and the elements that overflow (outside scroll containers),
//   broken images, in-page anchors / nav targets that do not resolve, visible "undefined"/"NaN"/"null" text,
//   text rendered below 11 px, charts (svg.chart) without an accessible name,
//   and (with --axe) an axe-core WCAG 2 A/AA scan.
// It also writes full-page screenshots <out dir>/shot-<width>-<i>.png in 4000 px tiles.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const [url, outDir, widthArg, ...rest] = process.argv.slice(2);
const widths = (widthArg && !widthArg.startsWith("--") ? widthArg : "1440,768,390").split(",").map(Number);
const useAxe = process.argv.includes("--axe");
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
mkdirSync(outDir, { recursive: true });
const profile = mkdtempSync(join(tmpdir(), "cdp-"));
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, "--no-first-run", "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function target() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const p = list.find(t => t.type === "page");
      if (p) return p.webSocketDebuggerUrl;
    } catch { /* not up yet */ }
    await sleep(200);
  }
  throw new Error("Chrome did not start");
}

const ws = new WebSocket(await target());
await new Promise(r => ws.addEventListener("open", r, { once: true }));
let seq = 0;
const pending = new Map(), events = [];
ws.addEventListener("message", ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } else if (m.method) events.push(m);
});
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = ++seq;
  pending.set(id, m => (m.error ? rej(new Error(`${method}: ${m.error.message}`)) : res(m.result)));
  ws.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expr => {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};

await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable"); await send("Network.enable");

const PROBE = `(() => {
  const W = document.documentElement.clientWidth, out = [];
  const scrollable = e => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX; if (ox === "auto" || ox === "scroll" || ox === "hidden") return true; } return false; };
  document.querySelectorAll("body *").forEach(e => {
    const r = e.getBoundingClientRect();
    if (r.width > 0 && r.right > W + 1 && !scrollable(e) && getComputedStyle(e).position !== "fixed") {
      const s = e.closest("section[id]"); const parentOver = e.parentElement && e.parentElement.getBoundingClientRect().right > W + 1 && !scrollable(e.parentElement);
      if (!parentOver) out.push((s ? s.id : "(shell)") + " " + e.tagName.toLowerCase() + "." + String(e.className.baseVal ?? e.className).split(" ")[0] + " right=" + Math.round(r.right));
    }
  });
  const ids = new Set([...document.querySelectorAll("[id]")].map(e => e.id));
  const badAnchors = [...document.querySelectorAll('a[href^="#"]')].map(a => a.getAttribute("href").slice(1)).filter(h => h && !ids.has(h));
  const badTargets = [...document.querySelectorAll("[data-target]")].map(e => e.dataset.target).filter(h => !ids.has(h));
  const brokenImgs = [...document.images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.getAttribute("src"));
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const badText = [], tiny = new Map(), tinySamples = [];
  for (let n; (n = walker.nextNode());) {
    const t = n.textContent.trim(); if (!t) continue;
    const el = n.parentElement; if (!el || el.closest("script,style,noscript")) continue;
    const cs = getComputedStyle(el); if (cs.display === "none" || cs.visibility === "hidden") continue;
    if (/(^|[^\\w])(undefined|NaN|null)([^\\w]|$)/.test(t)) badText.push((el.closest("section[id]")?.id || "") + ": " + t.slice(0, 80));
    const fs = parseFloat(cs.fontSize);
    const isSvg = el.closest("svg");
    const eff = isSvg ? fs * (isSvg.getBoundingClientRect().width / (isSvg.viewBox?.baseVal?.width || isSvg.getBoundingClientRect().width)) : fs;
    if (eff < 11) { const k = (el.closest("section[id]")?.id || "(shell)") + (isSvg ? " svg" : ""); tiny.set(k, (tiny.get(k) || 0) + 1);
      if (tinySamples.length < 60) tinySamples.push(k + " " + el.tagName.toLowerCase() + "." + String(el.className.baseVal ?? el.className).split(" ")[0] + " " + eff.toFixed(1) + "px: " + t.slice(0, 30)); }
  }
  const charts = [...document.querySelectorAll("svg.chart")];
  return { viewport: W, docWidth: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight,
    overflow: out, badAnchors, badTargets, brokenImgs, badText,
    tinyText: Object.fromEntries(tiny), tinySamples, charts: charts.length,
    chartsWithoutName: charts.filter(c => !(c.getAttribute("aria-label") || c.querySelector("title"))).length };
})()`;

const summary = {};
for (const w of widths) {
  events.length = 0;
  await send("Emulation.setDeviceMetricsOverride", { width: w, height: 900, deviceScaleFactor: 1, mobile: w < 500 });
  await send("Page.navigate", { url });
  for (let i = 0; i < 100 && !events.some(e => e.method === "Page.loadEventFired"); i++) await sleep(100);
  await sleep(4000);                                      // fetch()-driven rendering
  const probe = await evaluate(PROBE);
  let axe = null;
  if (useAxe) {
    await evaluate(`new Promise((res, rej) => { const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"; s.onload = res; s.onerror = () => rej(new Error("axe load failed")); document.head.appendChild(s); })`);
    axe = await evaluate(`axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } })
      .then(r => r.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
        sample: v.nodes.slice(0, 3).map(n => n.target.join(" ")) })))`);
  }
  const consoleMsgs = events.filter(e => e.method === "Runtime.consoleAPICalled" && ["error", "warning", "assert"].includes(e.params.type))
    .map(e => e.params.type + ": " + e.params.args.map(a => a.value ?? a.description ?? "").join(" "));
  const exceptions = events.filter(e => e.method === "Runtime.exceptionThrown").map(e => e.params.exceptionDetails.exception?.description || e.params.exceptionDetails.text);
  const logErrors = events.filter(e => e.method === "Log.entryAdded" && e.params.entry.level === "error").map(e => e.params.entry.text + " " + (e.params.entry.url || ""));
  const status = new Map();
  events.filter(e => e.method === "Network.responseReceived").forEach(e => status.set(e.params.requestId, [e.params.response.url, e.params.response.status]));
  const httpErrors = [...status.values()].filter(([, s]) => s >= 400).map(([u, s]) => s + " " + u);
  const failed = events.filter(e => e.method === "Network.loadingFailed" && !e.params.canceled).map(e => e.params.errorText + " " + (status.get(e.params.requestId)?.[0] || e.params.requestId));
  // full-page screenshot in tiles
  const { cssContentSize } = await send("Page.getLayoutMetrics");
  const H = Math.ceil(cssContentSize.height), tiles = [];
  for (let y = 0, i = 0; y < H; y += 4000, i++) {
    const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { x: 0, y, width: w, height: Math.min(4000, H - y), scale: 1 } });
    const f = join(outDir, `shot-${w}-${i}.png`); writeFileSync(f, Buffer.from(shot.data, "base64")); tiles.push(f);
  }
  const rep = { url, width: w, ...probe, consoleMsgs, exceptions, logErrors, httpErrors, failed, axe, tiles };
  writeFileSync(join(outDir, `report-${w}.json`), JSON.stringify(rep, null, 1));
  summary[w] = { overflowPx: probe.docWidth - probe.viewport, overflowElems: probe.overflow.length, console: consoleMsgs.length,
    exceptions: exceptions.length, logErrors: logErrors.length, http: httpErrors.length + failed.length, brokenImgs: probe.brokenImgs.length,
    badAnchors: probe.badAnchors.length + probe.badTargets.length, badText: probe.badText.length,
    tinyText: Object.values(probe.tinyText).reduce((a, b) => a + b, 0), chartsWithoutName: `${probe.chartsWithoutName}/${probe.charts}`,
    axe: axe ? axe.map(v => `${v.id}(${v.impact}):${v.nodes}`).join(" ") : "not run", tiles: tiles.length };
}
console.log(JSON.stringify(summary, null, 1));
ws.close(); chrome.kill();
