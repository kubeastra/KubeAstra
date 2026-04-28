#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_DIR="$(cd "$SCRIPT_DIR/../mcp" && pwd)"

echo "Starting Kubeastra Web UI..."

# Start backend
cd "$SCRIPT_DIR/backend"
MCP_PATH="$MCP_DIR" PYTHONPATH="$MCP_DIR" venv/bin/uvicorn main:app --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID (port 8000)"

# Start frontend
cd "$SCRIPT_DIR/frontend"

# Build if .next/ is missing or older than the source
if [ ! -d ".next" ] || [ ! -f ".next/BUILD_ID" ]; then
    echo "No production build found — running 'npm run build' (one-time, ~30-60s)..."
    npm run build || { echo "Build failed — aborting."; kill $BACKEND_PID; exit 1; }
fi

API_BASE_URL=http://localhost:8000 npm run start &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID (port 3000)"

echo ""
echo "Open: http://localhost:3000"
echo "Press Ctrl+C to stop both services"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
