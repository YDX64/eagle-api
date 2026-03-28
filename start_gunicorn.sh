#!/bin/bash

# =============================================================================
# Gol Sinyali API - Gunicorn Startup Script
# =============================================================================
# Usage:
#   ./start_gunicorn.sh              # Start normally
#   ./start_gunicorn.sh --reload     # Start with auto-reload (development)
#   ./start_gunicorn.sh --daemon     # Start as background daemon
# =============================================================================

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
VENV_PATH="instance/bin/activate"
APP_MODULE="app:app"
CONFIG_FILE="gunicorn_config.py"
PID_FILE="gunicorn.pid"

# Parse arguments
RELOAD_FLAG=""
DAEMON_FLAG=""
WORKERS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --reload)
            RELOAD_FLAG="--reload"
            echo -e "${YELLOW}⚠️  Auto-reload enabled (development mode)${NC}"
            shift
            ;;
        --daemon)
            DAEMON_FLAG="--daemon"
            echo -e "${YELLOW}🔄 Starting as background daemon${NC}"
            shift
            ;;
        --workers)
            WORKERS="--workers $2"
            echo -e "${YELLOW}👷 Using $2 workers${NC}"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${RED}❌ Gunicorn is already running (PID: $PID)${NC}"
        echo "Run './stop_gunicorn.sh' to stop it first"
        exit 1
    else
        echo -e "${YELLOW}⚠️  Stale PID file found, removing...${NC}"
        rm -f "$PID_FILE"
    fi
fi

# Activate virtual environment
if [ -f "$VENV_PATH" ]; then
    echo -e "${GREEN}✅ Activating virtual environment...${NC}"
    source "$VENV_PATH"
else
    echo -e "${RED}❌ Virtual environment not found at: $VENV_PATH${NC}"
    exit 1
fi

# Check if logs directory exists
if [ ! -d "logs" ]; then
    echo -e "${YELLOW}📁 Creating logs directory...${NC}"
    mkdir -p logs
fi

# Check if gunicorn is installed
if ! command -v gunicorn &> /dev/null; then
    echo -e "${RED}❌ Gunicorn is not installed${NC}"
    echo "Run: pip install -r requirements.txt"
    exit 1
fi

# Display startup info
echo ""
echo "============================================================================="
echo "🚀 Starting Gol Sinyali API with Gunicorn"
echo "============================================================================="
echo "App module:      $APP_MODULE"
echo "Config file:     $CONFIG_FILE"
echo "PID file:        $PID_FILE"
echo "Options:         $RELOAD_FLAG $DAEMON_FLAG $WORKERS"
echo "============================================================================="
echo ""

# Start Gunicorn
if [ -n "$DAEMON_FLAG" ]; then
    # Daemon mode
    gunicorn -c "$CONFIG_FILE" $RELOAD_FLAG $WORKERS $DAEMON_FLAG "$APP_MODULE"

    if [ $? -eq 0 ]; then
        sleep 2
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            echo -e "${GREEN}✅ Gunicorn started successfully (PID: $PID)${NC}"
            echo ""
            echo "To check status: ps aux | grep gunicorn"
            echo "To stop server:  ./stop_gunicorn.sh"
            echo "To view logs:    tail -f logs/gunicorn_error.log"
        else
            echo -e "${RED}❌ Failed to start Gunicorn (no PID file created)${NC}"
            exit 1
        fi
    else
        echo -e "${RED}❌ Failed to start Gunicorn${NC}"
        exit 1
    fi
else
    # Foreground mode
    echo -e "${GREEN}▶️  Starting in foreground mode (Press Ctrl+C to stop)${NC}"
    echo ""
    gunicorn -c "$CONFIG_FILE" $RELOAD_FLAG $WORKERS "$APP_MODULE"
fi
