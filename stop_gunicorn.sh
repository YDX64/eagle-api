#!/bin/bash

# =============================================================================
# Gol Sinyali API - Gunicorn Stop Script
# =============================================================================
# Usage:
#   ./stop_gunicorn.sh           # Graceful shutdown (SIGTERM)
#   ./stop_gunicorn.sh --force   # Force kill (SIGKILL)
# =============================================================================

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PID_FILE="gunicorn.pid"

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo -e "${RED}❌ PID file not found: $PID_FILE${NC}"
    echo ""
    echo "Searching for running Gunicorn processes..."

    GUNICORN_PIDS=$(ps aux | grep "[g]unicorn.*golsinyali_api" | awk '{print $2}')

    if [ -z "$GUNICORN_PIDS" ]; then
        echo -e "${GREEN}✅ No Gunicorn processes found${NC}"
        exit 0
    else
        echo -e "${YELLOW}Found running processes:${NC}"
        ps aux | grep "[g]unicorn.*golsinyali_api"
        echo ""
        read -p "Kill these processes? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "$GUNICORN_PIDS" | xargs kill -TERM
            echo -e "${GREEN}✅ Sent SIGTERM to processes${NC}"
        fi
        exit 0
    fi
fi

# Read PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ! ps -p $PID > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Process not running (PID: $PID)${NC}"
    rm -f "$PID_FILE"
    exit 0
fi

# Parse arguments
FORCE=false
if [ "$1" == "--force" ]; then
    FORCE=true
fi

echo "============================================================================="
echo "🛑 Stopping Gol Sinyali API"
echo "============================================================================="
echo "PID: $PID"
echo ""

if [ "$FORCE" == true ]; then
    echo -e "${RED}⚠️  Force killing process...${NC}"
    kill -9 $PID
    sleep 1
else
    echo -e "${GREEN}Sending graceful shutdown signal (SIGTERM)...${NC}"
    kill -TERM $PID

    # Wait for graceful shutdown (max 10 seconds)
    echo -n "Waiting for shutdown"
    for i in {1..10}; do
        if ! ps -p $PID > /dev/null 2>&1; then
            break
        fi
        echo -n "."
        sleep 1
    done
    echo ""

    # Check if still running
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Process still running, force killing...${NC}"
        kill -9 $PID
        sleep 1
    fi
fi

# Verify shutdown
if ps -p $PID > /dev/null 2>&1; then
    echo -e "${RED}❌ Failed to stop process${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Gunicorn stopped successfully${NC}"
    rm -f "$PID_FILE"

    # Kill any orphaned workers
    ORPHANS=$(ps aux | grep "[g]unicorn.*golsinyali_api" | awk '{print $2}')
    if [ -n "$ORPHANS" ]; then
        echo -e "${YELLOW}Cleaning up orphaned workers...${NC}"
        echo "$ORPHANS" | xargs kill -9 2>/dev/null
    fi
fi

echo ""
echo "============================================================================="
