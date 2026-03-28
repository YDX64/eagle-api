#!/bin/bash

# =============================================================================
# Gol Sinyali API - Gunicorn Restart Script
# =============================================================================
# Usage:
#   ./restart_gunicorn.sh              # Restart with same options
#   ./restart_gunicorn.sh --reload     # Restart with auto-reload
# =============================================================================

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "============================================================================="
echo "🔄 Restarting Gol Sinyali API"
echo "============================================================================="
echo ""

# Stop current instance
./stop_gunicorn.sh

# Wait a moment
sleep 2

# Start new instance
echo ""
echo -e "${YELLOW}Starting new instance...${NC}"
./start_gunicorn.sh "$@"
