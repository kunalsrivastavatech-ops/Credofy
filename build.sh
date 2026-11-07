#!/usr/bin/env bash
# Build Script for Cloud Deployment (Render, Railway, Heroku)
set -o errexit

echo "📦 Installing Python Dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# If npm is installed in container, rebuild; otherwise use tracked production dist
if command -v npm &> /dev/null; then
    echo "🎨 Building React Frontend with npm..."
    cd frontend && npm install && npm run build && cd ..
else
    echo "✓ Using pre-compiled production frontend dist assets."
fi

echo "✓ Build complete and ready for deployment!"
