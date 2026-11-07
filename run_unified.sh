#!/bin/bash
# Kredo Unified Single-URL Startup Script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="/Users/kunal/.gemini/antigravity/scratch/pdf_env/bin"

echo "=================================================="
echo "🏦 EquiBharat.ai: Intelligent Credit Underwriting System"
echo "   Real-Time Explainable AI & Bank Document Verification"
echo "=================================================="

# Kill any existing processes on port 8000
lsof -ti :8000 | xargs kill -9 2>/dev/null || true

# Start Unified FastAPI Server (Hosts both Frontend UI + Backend API + MongoDB)
cd "$SCRIPT_DIR/backend"
$PYTHON_BIN/uvicorn server:app --host 0.0.0.0 --port 8000
