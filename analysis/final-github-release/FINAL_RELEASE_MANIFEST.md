# Final Release Manifest

Pre-commit audit for the "Finalize IoT NS-3 research and dashboard" release, prepared in an
isolated git worktree (`main` branch, `github` remote) so that the ns-3-dev checkout (`master`
branch, `origin` remote) was never touched.

## Repository topology discovery (important context)

This working directory doubles as a clone of the upstream ns-3-dev project (`origin` remote,
`master` branch, tracking GitLab) with the user's own research repository layered in via a second
remote (`github`, branch `main`, **completely unrelated git history** — no common ancestor with
`master`). All research work in this project accumulated as uncommitted/untracked files against
the `master` checkout and had **never been committed to any branch connected to GitHub** before
this release — including a partially-advanced branch `v3-phase1` (5 unpushed commits ahead of
`main`) which itself predates the V3 official baseline, V4 study, bottleneck characterisation,
retry validation, rate sweep, diagnostic, and reproducibility check. This release is therefore the
**first-ever publication** of that entire body of work, not an incremental update.

## Outdated-phrase audit (task step 18)

| Phrase | Occurrences found | Classification |
|---|---|---|
| "V2.7" | README.md, site/index.html, docs/*.md, experiments/*.py, dashboard/* | **B** — legitimate historical documentation/code, now explicitly labelled as legacy in the rewritten README and site's "Research History" section |
| "V3 in-progress" | none | n/a |
| "4 validation runs" | none | n/a |
| "60 total simulation runs" | README.md (inside the "V2.7 baseline (legacy)" collapsed section) | **B** — accurate historical figure, correctly scoped to the legacy section |
| "15-node clustered topology" | README.md, docs/research-history.md, site/index.html (all describing the historical prototype), scratch/iot-network-v3.cc (source comment) | **B/C** — legitimate historical reference / unchanged legacy code |
| "current baseline" | docs/research-history.md line 32 | **A, already resolved** — correctly asserts `iot-network-v3-ext.cc` (not the legacy `iot-network.cc`) as the current baseline |
| "sigmoid extension" | none | n/a |

No outdated phrase was found describing V2.7, the old 60-run study, or the 4-run sigmoid smoke
test as the *current* research state in any file. `dashboard/app.py` and its templates/static
files remain unchanged (legacy Flask tool, explicitly relabelled in the README as a local-only
V2.7 browser, not the public dashboard) — left as-is per the task's "do not blindly replace
historical references" instruction, since it is legitimate historical code, category C.

## Files added / modified

- **3,633 new files, 13 modified files**, +106,935 / −1,129 lines (full `git diff --cached
  --stat` retained in this worktree's git history after commit).
- New: `scratch/iot-network-v3-ext.cc`, `scratch/iot-network-bottleneck-probe.cc`,
  `results/v4-matched/`, `results/v4-sensitivity/`, `analysis/final-report-data/`,
  `analysis/final-reproducibility-check/`, `analysis/bottleneck-characterisation/`,
  `analysis/update8-tier1-activation/`, `analysis/final-github-release/`,
  `docs/research-history.md`, `site/data/final_research.json`,
  `site/static/final-dashboard.{css,js}`.
- Modified: `README.md` (full rewrite), `site/index.html` (full rewrite — public dashboard),
  11 files under `results/v3-ext/` (the public repo previously held only partial/legacy content
  at these exact paths from the unpushed `v3-phase1` branch; they are now the complete, frozen,
  unmodified 11-seed official dataset copied byte-for-byte from the frozen research).
- Retained as historical, untouched: `scratch/iot-network.cc`, `scratch/iot-network-v3.cc`,
  `scratch/scratch-simulator.cc`, `dashboard/` (all files), `experiments/`, legacy `results/*.csv`
  + `results/logs/` + `results/plots/` + `results/v3/`, `site/data/{summary,sigmoid,methodology,
  rows,meta,v3ext-*}.json`, `site/static/{style.css,site.js,realworld.js,topology.js}` (superseded
  by the new final-dashboard files but not deleted), `docs/{methodology,experiment-design,
  sigmoid-metric,v3-experiment-framework}.md`.

## Git safety checks performed

- `git status` / `git diff --cached --stat`: reviewed in full, no unexpected paths.
- Secrets scan (`api_key|secret|password|BEGIN ... KEY|AKIA...`) over the staged diff: **0 matches**.
- `.env` / credential-shaped filename scan: **0 matches**. (`dashboard/.env.example` is a template
  with no real values, pre-existing, unchanged.)
- No frozen dataset was altered: every file under `analysis/final-report-data/`,
  `analysis/final-reproducibility-check/`, `analysis/bottleneck-characterisation/`,
  `analysis/update8-tier1-activation/`, `results/v3-ext/`, `results/v4-matched/`,
  `results/v4-sensitivity/`, and both final `scratch/*.cc` sources were copied byte-for-byte from
  the frozen research working directory — none were edited during this release process.
- No push has been made yet. Commit is local to this worktree, fully reversible.

## Confirmation

No new research experiment was performed to produce this release. No simulation was run. No
frozen numerical result was changed, recalculated, or replaced. This is a documentation and
publication task only.
