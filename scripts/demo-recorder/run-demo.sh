#!/bin/bash
# Orchestrates the full demo: kind cluster + broken workloads + UI + walkthrough.
# Records a video automatically.
#
# Usage:  ./scripts/demo-recorder/run-demo.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "═══════════════════════════════════════════════════════════════════"
echo "  Kubeastra demo recorder"
echo "═══════════════════════════════════════════════════════════════════"

# ── 1. Kind cluster + broken workloads ───────────────────────────────────────
echo ""
echo "[1/4] Bringing up demo cluster…"
cd "$REPO_ROOT"
make demo

# ── 2. Wait for backend health ───────────────────────────────────────────────
echo ""
echo "[2/4] Waiting for backend (http://localhost:8800) …"
for i in {1..60}; do
    if curl -fs http://localhost:8800/api/health >/dev/null 2>&1; then
        echo "   backend ✓"
        break
    fi
    sleep 2
    if [ "$i" = "60" ]; then
        echo "ERROR: backend not reachable after 120s — check 'make demo' logs."
        exit 1
    fi
done

# ── 3. Wait for frontend ─────────────────────────────────────────────────────
echo ""
echo "[3/4] Waiting for frontend (http://localhost:3300) …"
for i in {1..60}; do
    if curl -fs http://localhost:3300 >/dev/null 2>&1; then
        echo "   frontend ✓"
        break
    fi
    sleep 2
    if [ "$i" = "60" ]; then
        echo "ERROR: frontend not reachable after 120s."
        exit 1
    fi
done

# Give the LLM-router prompt enough time to finish warming up
echo ""
echo "Pausing 5s for the AI-router to warm up…"
sleep 5

# ── 4. Install Playwright deps if missing, then run walkthrough ──────────────
echo ""
echo "[4/4] Running the walkthrough (recording video)…"
cd "$SCRIPT_DIR"

if [ ! -d "node_modules/playwright" ]; then
    echo "   Installing Playwright (one-time)…"
    npm install --silent
    npx playwright install chromium
fi

node walkthrough.mjs

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Done. Video output: scripts/demo-recorder/output/"
echo ""
echo "  Convert to mp4:"
echo "    cd scripts/demo-recorder/output"
echo "    ffmpeg -i *.webm -c:v libx264 -crf 23 -movflags +faststart demo.mp4"
echo ""
echo "  Stop the demo cluster when done:"
echo "    make demo-down     # keep cluster, stop UI"
echo "    make demo-clean    # full teardown"
echo "═══════════════════════════════════════════════════════════════════"
