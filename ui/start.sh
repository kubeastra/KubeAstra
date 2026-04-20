#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_DIR="$(cd "$SCRIPT_DIR/../mcp" && pwd)"

echo "Starting K8s DevOps Web UI..."

# Start backend
cd "$SCRIPT_DIR/backend"
MCP_PATH="$MCP_DIR" PYTHONPATH="$MCP_DIR" venv/bin/uvicorn main:app --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID (port 8000)"

# Start frontend
cd "$SCRIPT_DIR/frontend"
API_BASE_URL=http://localhost:8000 npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID (port 3000)"

echo ""
echo "Open: http://localhost:3000"
echo "Press Ctrl+C to stop both services"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
