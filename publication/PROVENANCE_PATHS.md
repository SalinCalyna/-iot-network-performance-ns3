# Local paths in the ARP-fixed run provenance

Every ARP-fixed run directory under `results/wifi-std/` has a `provenance.json` written by the run manager at the
time of the run. Before publication, the absolute path of the original repository root was replaced by the token
`<NS3_ROOT>`. Nothing else in these files was changed.

## What they contain (review of all 503 files, 2026-10-28)

| Field | Content | Local information |
|---|---|---|
| `argv[0]` | simulator binary: `<NS3_ROOT>/build/scratch/ns3-dev-iot-network-wifi-std-arp-default` | redacted |
| `cwd` | working directory: `<NS3_ROOT>` | redacted |
| `argv[1:]` | the simulator arguments | none (these are what you need to re-run a case) |
| `source`, `source_sha256`, `binary_sha256` | source path (repository-relative) and hashes | none |
| `git_head`, `git_branch` | commit and branch of the original research workspace (`exp/wifi6-arp`) | none. These commits belong to a private working branch that also carries the upstream NS-3 history; they are **not** in this repository. The simulator source is identified by `source_sha256` instead |
| `exit_code`, `wall_sec`, `stderr_bytes`, `timeout_sec`, `timed_out`, `finished` | run status and timing | none |

No e-mail address, host name, real name or student number appears in any provenance file.

## The redaction is reversible
`PROVENANCE_REDACTION.tsv` lists, for each file, the sha256 of the original and of the published version. Replacing
`<NS3_ROOT>` by the original root reproduces the original bytes, so a holder of the original files (for example the
thesis examiners) can match them to the published ones. The analyses read only `argv[1:]`, `exit_code` and the
hashes; their outputs are byte-identical before and after the redaction. Only the two `INPUTS.sha256` files (which
hash the provenance files) and the source hashes in `site/data/arp-fixed.json` were regenerated.

## How to read them
- To re-run a case, use `argv[1:]` with your own build (`docs/arp-fixed-reproduction.md` §2).
- To check a published `provenance.json`, compare its sha256 with `publication/MANIFEST.sha256` and with the
  analyses' `INPUTS.sha256` files.
