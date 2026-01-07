#!/usr/bin/env bash
# build.sh - Render Build Script

set -o errexit

echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

echo "🎭 Installing Playwright..."
playwright install chromium
playwright install-deps chromium || true

echo "📊 Running migrations..."
python manage.py migrate

echo "📁 Collecting static files..."
python manage.py collectstatic --no-input

echo "✅ Build complete!"