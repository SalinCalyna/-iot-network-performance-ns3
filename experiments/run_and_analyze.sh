#!/usr/bin/env bash
#
# One-command entry point for the IoT Network V2 research pipeline:
#
#   NS-3 C++ simulation -> CSV -> Python analysis -> statistics -> graphs
#
# Default mode (no arguments): analysis only. Reads the EXISTING V2.7 CSV
# files under results/, validates them, computes statistics, and generates
# graphs. Never touches NS-3, never modifies results/*.csv or results/logs/.
#
#   ./experiments/run_and_analyze.sh
#
# --run mode: also (re)runs the full NS-3 experiment matrix first, via the
# existing experiments/run_experiments.sh, before analyzing. This is the
# only mode that regenerates results/*.csv -- never invoked automatically.
#
#   ./experiments/run_and_analyze.sh --run

set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-./myenv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="python3"
fi

RUN_MODE=0
for arg in "$@"; do
    case "$arg" in
        --run) RUN_MODE=1 ;;
        *) echo "Unknown argument: $arg (supported: --run)" >&2; exit 1 ;;
    esac
done

echo "----------------------------------------"
echo "Checking Python dependencies..."
"$PYTHON_BIN" - <<'EOF'
import importlib.util
missing = [m for m in ("pandas", "matplotlib") if importlib.util.find_spec(m) is None]
if missing:
    raise SystemExit(f"Missing Python packages: {', '.join(missing)}. Run: pip install -r experiments/requirements.txt")
print("  pandas, matplotlib available")
EOF

if [[ "$RUN_MODE" -eq 1 ]]; then
    echo "----------------------------------------"
    echo "MODE: --run -- re-running the full NS-3 experiment matrix first."
    echo "This will regenerate results/*.csv and results/logs/*."
    ./experiments/run_experiments.sh
else
    echo "----------------------------------------"
    echo "MODE: analyze-only (default) -- NS-3 will NOT be run."
    echo "Reading existing results/*.csv as-is."
fi

echo
"$PYTHON_BIN" experiments/analyze_results.py results
