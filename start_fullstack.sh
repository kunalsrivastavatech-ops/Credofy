#!/bin/bash
# Kredo Full-Stack Launch Script (Backend + MongoDB + React Frontend)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="/Users/kunal/.gemini/antigravity/scratch/pdf_env/bin"

echo "=================================================="
echo "🏦 Starting Kredo.ai Full-Stack Architecture"
echo "   DEVIATHON 2.0 • Mission Bharat • Meridian"
echo "=================================================="

# 1. Kill any existing processes on ports 8000 and 3000
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
lsof -ti :3000 | xargs kill -9 2>/dev/null || true

# 2. Start FastAPI + MongoDB Backend
echo "🚀 [1/2] Starting FastAPI Backend on http://localhost:8000 ..."
cd "$SCRIPT_DIR/backend"
$PYTHON_BIN/uvicorn server:app --host 0.0.0.0 --port 8000 > "$SCRIPT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 2

# 3. Start React + Vite Frontend
echo "💻 [2/2] Starting React + Tailwind Frontend on http://localhost:3000 ..."
cd "$SCRIPT_DIR/frontend"
npm run dev > "$SCRIPT_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

sleep 2

echo ""
echo "✅ Kredo Full-Stack System is Live:"
echo "   • React Frontend UI:  http://localhost:3000"
echo "   • FastAPI Backend:    http://localhost:8000"
echo "   • API Docs (Swagger): http://localhost:8000/docs"
echo "   • MongoDB Database:   kredo_db (applications collection)"
echo ""
echo "Press Ctrl+C to stop all servers."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
