#!/bin/bash
#
# Cron Job Setup Script - Daily Cache Warm-up
#
# Bu script her sabah 06:00'da otomatik cache warm-up yapacak cron job'ı ekler.
#
# Kullanım:
#   ./setup_cron.sh [API_URL]
#
# Örnek:
#   ./setup_cron.sh http://localhost:8000
#   ./setup_cron.sh https://api.golsinyali.com
#

set -e

# Default API URL
API_URL="${1:-http://localhost:8000}"

# Project root directory (bu script'in bulunduğu dizin)
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
WARM_CACHE_SCRIPT="$PROJECT_ROOT/warm_cache.sh"

echo "=================================================="
echo "🕐 Cron Job Setup - Daily Cache Warm-up"
echo "=================================================="
echo "API URL: $API_URL"
echo "Project root: $PROJECT_ROOT"
echo "Script path: $WARM_CACHE_SCRIPT"
echo ""

# Check if warm_cache.sh exists
if [ ! -f "$WARM_CACHE_SCRIPT" ]; then
    echo "❌ ERROR: warm_cache.sh not found at $WARM_CACHE_SCRIPT"
    exit 1
fi

# Make sure warm_cache.sh is executable
chmod +x "$WARM_CACHE_SCRIPT"
echo "✅ warm_cache.sh is executable"

# Create cron job entry
CRON_COMMENT="# Golsinyali API - Daily cache warm-up at 06:00"
CRON_JOB="0 6 * * * $WARM_CACHE_SCRIPT $API_URL >> $PROJECT_ROOT/logs/cron_warmup.log 2>&1"

echo ""
echo "Cron job to be added:"
echo "  $CRON_COMMENT"
echo "  $CRON_JOB"
echo ""

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "$WARM_CACHE_SCRIPT"; then
    echo "⚠️  WARNING: Cron job already exists!"
    echo ""
    echo "Current crontab:"
    crontab -l | grep "$WARM_CACHE_SCRIPT"
    echo ""
    read -p "Do you want to REPLACE the existing cron job? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted. No changes made."
        exit 0
    fi

    # Remove existing entry
    crontab -l | grep -v "$WARM_CACHE_SCRIPT" | crontab -
    echo "✅ Removed old cron job"
fi

# Add new cron job
(crontab -l 2>/dev/null || true; echo "$CRON_COMMENT"; echo "$CRON_JOB") | crontab -

echo ""
echo "=================================================="
echo "✅ Cron Job Added Successfully!"
echo "=================================================="
echo ""
echo "Schedule: Every day at 06:00 AM"
echo "Action: Run cache warm-up for all today's matches"
echo "Log file: $PROJECT_ROOT/logs/cron_warmup.log"
echo ""
echo "Current crontab:"
crontab -l | grep -A 1 "Golsinyali"
echo ""
echo "To verify cron job:"
echo "  crontab -l | grep golsinyali"
echo ""
echo "To remove cron job:"
echo "  crontab -l | grep -v 'warm_cache.sh' | crontab -"
echo ""
echo "To test cron job manually:"
echo "  $WARM_CACHE_SCRIPT $API_URL"
echo ""
echo "🎉 Setup completed! Cache will be warmed up every day at 06:00."
