#!/bin/bash
# ==============================================
# Server Scraper Setup Script
# Run this on the DO Sydney server (syd1)
# ==============================================

set -e

echo "🏇 Setting up scraper on server..."

# 1. Install pip packages
echo "📦 Installing Python packages..."
pip install playwright aiohttp 2>/dev/null || pip3 install playwright aiohttp

# 2. Install Playwright browsers (chromium only to save space on 1GB server)
echo "🌐 Installing Chromium browser..."
playwright install chromium
playwright install-deps chromium

# 3. Create the cron wrapper script
echo "📝 Creating cron wrapper..."
REPO_DIR=$(cd "$(dirname "$0")" && pwd)

cat > "$REPO_DIR/run_scraper.sh" << WRAPPER
#!/bin/bash
cd $REPO_DIR
export SCRAPER_MODE=sequential
python github_scraper.py >> /var/log/racing-scraper.log 2>&1
WRAPPER

chmod +x "$REPO_DIR/run_scraper.sh"

# 4. Create log file
touch /var/log/racing-scraper.log

# 5. Add cron job (every 5 minutes)
echo "⏰ Setting up cron job..."
CRON_CMD="*/5 * * * * $REPO_DIR/run_scraper.sh"

# Check if cron already exists
(crontab -l 2>/dev/null | grep -v "run_scraper.sh"; echo "$CRON_CMD") | crontab -

echo ""
echo "✅ Setup complete!"
echo ""
echo "What was done:"
echo "  1. Installed playwright + aiohttp"
echo "  2. Installed Chromium browser"
echo "  3. Created run_scraper.sh wrapper (sequential mode)"
echo "  4. Added cron job: every 5 minutes"
echo ""
echo "📋 Commands:"
echo "  View logs:     tail -f /var/log/racing-scraper.log"
echo "  Run manually:  SCRAPER_MODE=sequential python $REPO_DIR/github_scraper.py"
echo "  Check cron:    crontab -l"
echo "  Remove cron:   crontab -l | grep -v run_scraper | crontab -"
