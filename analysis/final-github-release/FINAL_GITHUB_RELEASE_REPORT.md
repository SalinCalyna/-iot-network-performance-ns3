# Final GitHub Release Report

## Repository audit

This working directory doubles as a checkout of the upstream ns-3-dev project (`origin` remote,
`master` branch) with the user's research repository layered in via a second remote (`github`,
branch `main`, unrelated git history). All release work was performed in an isolated `git
worktree` for `main`, so `master`/`origin` were never touched (confirmed clean before and after).
Before this release, the entire body of research (V3 official, V4, bottleneck characterisation,
retry validation, rate sweep, Static/N=50 diagnostic, integrity audit, frozen report package,
reproducibility check) had never been committed to any branch connected to GitHub — this release
is its first publication. Full detail, including the outdated-phrase audit (task step 18), is in
`FINAL_RELEASE_MANIFEST.md` in this same directory.

## Files added

3,633 new files, including both final simulator sources (`scratch/iot-network-v3-ext.cc`,
`scratch/iot-network-bottleneck-probe.cc`), the official V3 raw results (`results/v3-ext/`), V4
raw results (`results/v4-matched/`, `results/v4-sensitivity/`), the full frozen analysis packages
(`analysis/final-report-data/`, `analysis/final-reproducibility-check/`,
`analysis/bottleneck-characterisation/`, `analysis/update8-tier1-activation/`), the new public
dashboard (`site/index.html`, `site/static/final-dashboard.{css,js}`,
`site/data/final_research.json`), and `docs/research-history.md`.

## Files modified

`README.md` (full rewrite), `site/index.html` (full rewrite), and 11 files under
`results/v3-ext/` (previously partial/legacy content at those paths, now the complete frozen
11-seed dataset, copied byte-for-byte, unmodified from the frozen research).

## Files retained as historical

`scratch/iot-network.cc`, `scratch/iot-network-v3.cc`, `scratch/scratch-simulator.cc`,
`dashboard/` (all files, unchanged, relabelled in the README as a local-only legacy tool),
`experiments/`, legacy `results/*.csv` + `results/logs/` + `results/plots/` + `results/v3/`, the
pre-existing `site/data/*.json` and `site/static/{style.css,site.js,realworld.js,topology.js}`
(superseded by the new dashboard files, not deleted), and the pre-existing design docs under
`docs/`.

## Files excluded

None of the frozen research was excluded — the user selected the "full frozen package" scope.
`analysis/final-integrity-audit/` and `analysis/thesis-writing-plan/` were intentionally **not**
published (they are working documents for the researcher's own thesis-writing process, not part
of the public research record this task scoped).

## Commit and push

- Commit: `6294c5b8c` — "Finalize IoT NS-3 research and dashboard"
- Pushed: `a295802ef..6294c5b8c main -> main` on the `github` remote — confirmed successful.

## GitHub Actions status

Workflow "Deploy dashboard to GitHub Pages" (run 34559964720) triggered on push and completed
with conclusion `success`.

## GitHub Pages status — IMPORTANT FINDING

**The repository's live Pages configuration does not appear to be sourcing from the `site/`
artifact the `deploy-pages.yml` workflow uploads.** The bare public URL
(`https://salincalyna.github.io/-iot-network-performance-ns3/`) currently renders a
**Jekyll-auto-generated page built from `README.md`** (Jekyll SEO tag, default theme, `anchor.min.js`
from cdnjs) — not the new dashboard. This is consistent with the repository's Pages **source**
setting being "Deploy from a branch: `main` / `(root)`" (the classic pipeline, which auto-renders
`README.md` when no `index.html` exists at the repository root) rather than "GitHub Actions" (the
pipeline `deploy-pages.yml` is written for). Because Jekyll passes through non-excluded files
verbatim, the new dashboard **is** reachable and **fully functional** at a sub-path:

**Verified live and working:** https://salincalyna.github.io/-iot-network-performance-ns3/site/index.html
(fetched directly: HTTP 200, exact byte size match to the authored file, all data/JS/CSS assets
resolve with HTTP 200 relative to that path, verified content markers present.)

This is very likely a **pre-existing** repository setting, not something this release changed —
`deploy-pages.yml` already existed before this release and was never modified by it. Changing the
Pages source requires a one-time change in the repository's web UI
(**Settings → Pages → Build and deployment → Source → "GitHub Actions"**), which requires
repository-admin access this session does not have (no `gh` CLI authentication, no API token was
available). **Recommend the researcher make this one setting change**; no further code or content
change is needed — once the source is switched, the existing `deploy-pages.yml` workflow will
serve the new dashboard at the bare root URL on the next push (or via a manual
"Run workflow" trigger).

## Verified dashboard URL

https://salincalyna.github.io/-iot-network-performance-ns3/site/index.html (working now)
https://salincalyna.github.io/-iot-network-performance-ns3/ (currently shows the Jekyll-rendered
README instead, pending the Pages-source setting change above)

## Dashboard sections (verified present)

Overview, Baseline Performance, V4 Routing Investigation, Bottleneck, Retry Exhaustion,
Offered-Rate Intervention, Static Control, Reproducibility, Conclusions & Limitations, Research
History.

## Data sources

`analysis/final-report-data/*.csv` (via the curated `site/data/final_research.json` extract) —
every figure/table on the dashboard was checked against the exact frozen values before publishing.

## Confirmation

Frozen numerical results were not changed, recalculated, or replaced by this release. No new
research experiment was performed. No simulation was run.
