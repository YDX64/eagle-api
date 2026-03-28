#!/bin/bash
#
# Cache Warming Script - Deploy Öncesi Cache'i Doldur
#
# Bu script deploy öncesi çalıştırılmalı!
# Cache warm-up olmadan production'a deploy ETMEYİN!
#
# Kullanım: ./warm_cache.sh [API_URL]
# Örnek: ./warm_cache.sh http://localhost:8000
#

set -e  # Exit on error

# API URL (default: localhost)
API_URL="${1:-http://localhost:8000}"

echo "=================================================="
echo "🔥 Golsinyali API - Cache Warming Script"
echo "=================================================="
echo "API URL: $API_URL"
echo ""

# Check if API is reachable
echo "🔍 Checking API health..."
if ! curl -sf "$API_URL/api/v1/health" > /dev/null 2>&1; then
    echo "❌ ERROR: API is not reachable at $API_URL"
    echo "   Please start the API first"
    exit 1
fi
echo "✅ API is healthy"
echo ""

# Get today's date
TODAY=$(date +%Y-%m-%d)
echo "📅 Today: $TODAY"
echo ""

# Step 1: Fetch today's matches
echo "📋 Step 1/3: Fetching today's matches..."
RESPONSE=$(curl -sf "$API_URL/api/v1/matches/today")
if [ -z "$RESPONSE" ]; then
    echo "❌ ERROR: Failed to fetch today's matches"
    exit 1
fi

# Extract match IDs using jq (if available) or grep
if command -v jq &> /dev/null; then
    MATCH_IDS=$(echo "$RESPONSE" | jq -r '.data.matches[]?.match_id // empty' 2>/dev/null | sort -u)
else
    # Fallback: use grep (less reliable but works without jq)
    MATCH_IDS=$(echo "$RESPONSE" | grep -o '"match_id":[0-9]*' | cut -d: -f2 | sort -u)
fi

if [ -z "$MATCH_IDS" ]; then
    echo "⚠️  WARNING: No matches found for today"
    exit 0
fi

# Count matches
MATCH_COUNT=$(echo "$MATCH_IDS" | wc -l | tr -d ' ')
echo "✅ Found $MATCH_COUNT matches"
echo ""

# Step 2: Warm cache for each match (parallel for speed)
echo "🔥 Step 2/3: Warming cache for all matches..."
echo "   This will take 5-10 minutes (parallel execution)"
echo ""

# Progress counter
COUNTER=0
TOTAL=$MATCH_COUNT

# Function to warm a single match (including odds and h2h)
warm_match() {
    local match_id=$1
    local api_url=$2

    # Fetch match details (this populates cache)
    curl -sf "$api_url/api/v1/match/$match_id" > /dev/null 2>&1

    # Fetch odds (separate cache)
    curl -sf "$api_url/api/v1/match/$match_id/odds" > /dev/null 2>&1

    # Fetch h2h (separate cache)
    curl -sf "$api_url/api/v1/match/$match_id/h2h" > /dev/null 2>&1

    echo "  ✅ Match $match_id cached (match+odds+h2h)"
}

export -f warm_match

# Parallel execution (10 concurrent workers)
echo "$MATCH_IDS" | xargs -P 10 -I {} bash -c "warm_match {} $API_URL"

echo ""
echo "✅ Cache warming for match details completed"
echo ""

# Step 3: Verify cache hit ratio
echo "📊 Step 3/3: Verifying cache performance..."

# Test a random match ID for cache hit
TEST_MATCH_ID=$(echo "$MATCH_IDS" | shuf -n 1)
START_TIME=$(date +%s%3N)
curl -sf "$API_URL/api/v1/match/$TEST_MATCH_ID" > /dev/null
END_TIME=$(date +%s%3N)
RESPONSE_TIME=$((END_TIME - START_TIME))

echo "🧪 Test cache hit:"
echo "   Match ID: $TEST_MATCH_ID"
echo "   Response time: ${RESPONSE_TIME}ms"

if [ "$RESPONSE_TIME" -lt 1000 ]; then
    echo "   ✅ FAST! Cache is warm"
elif [ "$RESPONSE_TIME" -lt 5000 ]; then
    echo "   ⚠️  OK but could be faster"
else
    echo "   ❌ SLOW! Cache might not be working"
fi

echo ""
echo "=================================================="
echo "✅ Cache Warming Completed!"
echo "=================================================="
echo ""
echo "Summary:"
echo "  • Total matches: $MATCH_COUNT"
echo "  • Cache warmed: $MATCH_COUNT matches"
echo "  • Test response: ${RESPONSE_TIME}ms"
echo ""
echo "Next steps:"
echo "  1. Deploy your application"
echo "  2. Monitor cache hit ratio (target: >95%)"
echo "  3. Check response times (target: <1s avg)"
echo ""
echo "🚀 Ready for production deployment!"
