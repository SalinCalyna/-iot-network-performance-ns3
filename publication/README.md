# ARP-fixed IEEE 802.11b evidence: claims, verifier and manifest

This folder connects the ARP-fixed 802.11b findings in the [main README](../README.md#ieee-80211b-study-arp-fixed-results-primary)
to the files that support them. The findings come from the thesis *Analysis of Gateway-Centric IoT Wireless Mesh
Networks Using NS-3*, which is **under advisor review**. The advisor approved
reporting the ARP-fixed runs as primary evidence, with the original runs as secondary evidence (October 2026).

| File | Purpose |
|---|---|
| [`CLAIMS.csv`](CLAIMS.csv) | one row per published number: value, raw evidence files, generating script, thesis location |
| [`verify_published_claims.py`](verify_published_claims.py) | recomputes every claim from the raw run files and checks the manifest and input hashes (Python standard library) |
| [`MANIFEST.sha256`](MANIFEST.sha256) | sha256 of every file added for the ARP-fixed evidence |
| [`PROVENANCE_PATHS.md`](PROVENANCE_PATHS.md) | how the original machine's repository root was redacted in the run provenance files, reversibly |

Run from the repository root:

```sh
python3 publication/verify_published_claims.py
```

Related:
- [`docs/arp-fixed-reproduction.md`](../docs/arp-fixed-reproduction.md): simulator, NS-3 base commit, build fix,
  re-running a case, regenerating the tables.
- `results/wifi-std/arp-*`: the run outputs.
- `analysis/chapter4-tables-figures/` and `analysis/arp-fixed-throughput-delay/`: analysis scripts, outputs and
  input hashes.

**Not included:**
- raw Wi-Fi 6 per-packet traces (see `docs/wifi6-risk-reproducibility.md`);
- the thesis text (under review);
- the provisional mobility and retry-exhaustion appendices (pending advisor decisions).

The dashboard's original 802.11b sections still show the original (frozen) values. A separate "802.11b ARP-fixed
results" section shows these runs, from `site/data/arp-fixed.json` (generator:
`experiments/wifi-std/build_site_arp_fixed.py`; tests: `experiments/wifi-std/test_site_arp_fixed.py`).
