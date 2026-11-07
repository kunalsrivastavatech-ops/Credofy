#!/usr/bin/env bash
# Build Script for Cloud Deployment (Render, Railway, Heroku)
set -o errexit

echo "📦 Installing Python Dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🎨 Building React Frontend..."
cd frontend
npm install
npm run build
cd ..

echo "✓ Build complete and ready for deployment!"
