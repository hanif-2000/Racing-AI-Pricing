#!/bin/bash
# ==============================================
# Server Scraper Setup Script
# Run this on the DO Sydney server (syd1)
# Supports venv - auto-detects if venv/bin/python exists
# ==============================================

set -e

REPO_DIR=$(cd "$(dirname "$0")" && pwd)
echo "🏇 Setting up scraper on server..."
echo "   Repo: $REPO_DIR"

# Auto-detect venv
if [ -f "$REPO_DIR/venv/bin/python" ]; then
    PY="$REPO_DIR/venv/bin/python"
    PIP="$REPO_DIR/venv/bin/pip"
    PLAYWRIGHT="$REPO_DIR/venv/bin/playwright"
    echo "   Using venv: $REPO_DIR/venv"
else
    PY="python3"
    PIP="pip3"
    PLAYWRIGHT="playwright"
    echo "   Using system Python"
fi

# 1. Install pip packages
echo ""
echo "📦 Installing Python packages..."
$PIP install playwright aiohttp

# 2. Install Playwright browsers (Chromium + Firefox)
echo ""
echo "🌐 Installing Chromium + Firefox browsers..."
$PLAYWRIGHT install chromium
$PLAYWRIGHT install firefox
$PLAYWRIGHT install-deps chromium firefox 2>/dev/null || true

# 3. Create the cron wrapper script
echo ""
echo "📝 Creating cron wrapper..."

cat > "$REPO_DIR/run_scraper.sh" << WRAPPER
#!/bin/bash
cd $REPO_DIR
export SCRAPER_MODE=sequential
$PY github_scraper.py >> /var/log/racing-scraper.log 2>&1
WRAPPER

chmod +x "$REPO_DIR/run_scraper.sh"

# 4. Create log file
sudo touch /var/log/racing-scraper.log 2>/dev/null || touch /var/log/racing-scraper.log
sudo chmod 666 /var/log/racing-scraper.log 2>/dev/null || true

# 5. Add cron job (every 5 minutes)
echo ""
echo "⏰ Setting up cron job..."
CRON_CMD="*/5 * * * * $REPO_DIR/run_scraper.sh"

# Check if cron already exists
(crontab -l 2>/dev/null | grep -v "run_scraper.sh"; echo "$CRON_CMD") | crontab -

echo ""
echo "✅ Setup complete!"
echo ""
echo "What was done:"
echo "  1. Installed playwright + aiohttp"
echo "  2. Installed Chromium + Firefox browsers"
echo "  3. Created run_scraper.sh wrapper (sequential mode)"
echo "  4. Added cron job: every 5 minutes"
echo ""
echo "📋 Commands:"
echo "  View logs:     tail -f /var/log/racing-scraper.log"
echo "  Run manually:  SCRAPER_MODE=sequential $PY $REPO_DIR/github_scraper.py"
echo "  Check cron:    crontab -l"
echo "  Remove cron:   crontab -l | grep -v run_scraper | crontab -"
