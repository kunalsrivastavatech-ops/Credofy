#!/bin/bash
# Startup script for Kredo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../pdf_env/bin/activate" 2>/dev/null || source /Users/kunal/.gemini/antigravity/scratch/pdf_env/bin/activate
cd "$SCRIPT_DIR"
streamlit run app.py --server.port=8501 --server.headless=true
