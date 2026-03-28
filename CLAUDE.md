# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Golsinyali API** - High-performance football match data API with multi-source failover, intelligent caching, and comprehensive analysis features.

**Key Features:**
- Multi-source data aggregation (nowgoal26.com, nowgoal.com, goaloo.com) with automatic failover
- Hybrid caching (Redis primary + in-memory fallback) with stale-while-revalidate pattern
- Real-time live match data with 30-second refresh
- Comprehensive league data: standings, matches, player/team stats, handicap analysis
- Comprehensive match analysis (H2H, odds, predictions, team performance)
- Production-ready with Gunicorn/gevent, systemd, and Sentry integration
- AWS Lambda support via `lambda_function.py`

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT REQUEST                                  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────────┐
│                        FLASK APPLICATION (app.py)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ Rate Limit  │  │    CORS     │  │ Compression │  │  Error Handlers     │ │
│  │ 200/min     │  │ Configured  │  │   gzip      │  │  Sentry Integration │ │
│  │ Whitelist   │  │ golsinyali  │  │             │  │  Fingerprinting     │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────────────────┐
│                          ROUTES (Blueprint Layer)                            │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ │
│  │ matches.py │ │  live.py   │ │ health.py  │ │ leagues.py │ │league_data │ │
│  │ 303 lines  │ │ 343 lines  │ │ 275 lines  │ │ 264 lines  │ │ 1364 lines │ │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘ └────────────┘ │
│         routes/utils.py (1182 lines) · routes/live_utils.py (448 lines)     │
│                      All caching logic & data orchestration                  │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
┌────────▼────────┐    ┌─────────▼─────────┐    ┌────────▼────────┐
│   CACHE LAYER   │    │   HTTP CLIENT     │    │ ANALYSIS LAYER  │
│  cache_utils.py │    │  http_client.py   │    │    analysis/    │
│    679 lines    │    │    1051 lines     │    │   h2h, odds,    │
│                 │    │                   │    │  predictions,   │
│ ┌─────────────┐ │    │ ┌───────────────┐ │    │  tactics_data   │
│ │   Redis     │ │    │ │ Thread Pool   │ │    └─────────────────┘
│ │  Primary    │ │    │ │  100 workers  │ │
│ └─────────────┘ │    │ └───────────────┘ │
│ ┌─────────────┐ │    │ ┌───────────────┐ │
│ │  In-Memory  │ │    │ │  Connection   │ │
│ │  Fallback   │ │    │ │   Pooling     │ │
│ └─────────────┘ │    │ │ 50/pool       │ │
└─────────────────┘    │ └───────────────┘ │
                       └─────────┬─────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
   ┌──────────▼──────────┐      │      ┌──────────▼──────────┐
   │   SOURCE MANAGER    │      │      │      PARSERS        │
   │  source_manager.py  │      │      │    parsers.py       │
   │     505 lines       │◄─────┘      │   live_parsers.py   │
   │                     │             │  league_parser.py   │
   │ • Health tracking   │             │  1238+964+767 lines │
   │ • Dynamic priority  │             │                     │
   │ • Auto failover     │             │ • MatchDateParser   │
   └──────────┬──────────┘             │ • LiveMatchParser   │
              │                        │ • LiveStatsParser   │
              │                        │ • LeagueDataParser  │
              │                        └─────────────────────┘
   ┌──────────▼──────────────────────────────────────────────┐
   │                    DATA SOURCES                          │
   │  ┌─────────────────────┐    ┌─────────────────────────┐ │
   │  │ PRIMARY             │    │ FALLBACKS               │ │
   │  │ live3.nowgoal26.com │───►│ 1. www.nowgoal.com      │ │
   │  │ 3s connect timeout  │    │ 2. www.goaloo.com        │ │
   │  └─────────────────────┘    │ immediate failover      │ │
   │  ┌─────────────────────┐    └─────────────────────────┘ │
   │  │ LEAGUE DATA         │                                 │
   │  │ football.nowgoal26  │                                 │
   │  └─────────────────────┘                                 │
   └──────────────────────────────────────────────────────────┘
```

---

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Start Redis (required for caching)
redis-server

# Run development server (port 8000)
python app.py

# Run production server with Gunicorn
gunicorn -c gunicorn_config.py app:app

# Run tests
pytest tests/
```

### Server Management
```bash
# Start/Stop/Restart Gunicorn
./start_gunicorn.sh [--daemon] [--reload] [--workers N]
./stop_gunicorn.sh [--force]
./restart_gunicorn.sh

# Systemd service management
sudo systemctl start golsinyali-api
sudo systemctl stop golsinyali-api
sudo systemctl restart golsinyali-api
sudo systemctl status golsinyali-api

# View logs
tail -f logs/app.log
tail -f logs/gunicorn_error.log
sudo journalctl -u golsinyali-api -f
```

### Cache Operations
```bash
# Warm cache with today's matches (10 parallel workers)
./warm_cache.sh [API_URL]

# Setup automated daily cache warming at 6:00 AM
./setup_cron.sh [API_URL]

# Clear cache via API
curl -X POST http://localhost:8000/api/v1/cache/clear

# View cache stats
curl http://localhost:8000/api/v1/cache/stats

# Reset cache stats counters
curl -X POST http://localhost:8000/api/v1/cache/stats/reset
```

### Data Source Management
```bash
# Check source health
curl http://localhost:8000/api/v1/sources/health

# Force primary source change
curl -X POST http://localhost:8000/api/v1/sources/force-primary \
  -H "Content-Type: application/json" \
  -d '{"source_url": "https://www.goaloo.com"}'

# Reset source metrics
curl -X POST http://localhost:8000/api/v1/sources/reset-metrics

# Update base URL interactively
./update_base_url.sh
```

---

## Code Organization

### Directory Structure
```
golsinyali_api_mevcut/
├── app.py                    # Flask application entry point (484 lines)
├── app_config.py             # Central config loader, avoids circular imports (15 lines)
├── config.py                 # Configuration classes (182 lines)
├── models.py                 # Data models, validation, exceptions (104 lines)
├── lambda_function.py        # AWS Lambda handler with urllib3 (standalone)
│
├── Core Modules/
│   ├── http_client.py        # HTTP requests, failover, pooling (1051 lines)
│   ├── cache_utils.py        # Caching layer, deduplication (679 lines)
│   ├── source_manager.py     # Health tracking, failover logic (505 lines)
│   ├── parsers.py            # Static data parsing (1238 lines)
│   ├── live_parsers.py       # Live match parsing (964 lines)
│   ├── league_parser.py      # League data parsing (767 lines)
│   ├── security.py           # JWT, API key, rate limiting (267 lines)
│   ├── background_tasks.py   # Cache cleanup, log rotation, leader election (491 lines)
│   ├── rate_limit_whitelist.py # IP whitelist for rate limiting (54 lines)
│   └── parse_tactics.py      # Tactics data parser
│
├── routes/                   # API Endpoints
│   ├── __init__.py           # Blueprint registration (35 lines)
│   ├── matches.py            # /match, /matches endpoints (303 lines)
│   ├── live.py               # /matches/live endpoints (343 lines)
│   ├── live_utils.py         # Live data fetch/cache utilities (448 lines)
│   ├── health.py             # /health, /cache, /sources endpoints (275 lines)
│   ├── auth.py               # /auth/token endpoint (37 lines)
│   ├── leagues.py            # /leagues list endpoints (264 lines)
│   ├── league_data.py        # /leagues/{id}/* data endpoints (1364 lines - LARGE)
│   └── utils.py              # Shared caching utilities (1182 lines - LARGE)
│
├── analysis/                 # Match Analysis Modules
│   ├── h2h.py                # Head-to-head statistics (721 lines)
│   ├── odds_analysis.py      # Odds interpretation (1117 lines)
│   ├── team_performance.py   # Team form metrics (689 lines)
│   ├── final_predictions.py  # Combined predictions (436 lines)
│   ├── odds_trends.py        # Odds movement analysis (602 lines)
│   ├── correct_score.py      # Score probability (235 lines)
│   ├── tactics.py            # Tactical analysis (521 lines)
│   ├── tactics_data.py       # Tactics reference data (570 lines)
│   └── tips.py               # Betting tips generation (74 lines)
│
├── data/                     # Static data files
│   ├── leagues.json          # League database (full structure)
│   ├── leagues_master.json   # Generated from league_gercek.js (cup detection)
│   └── league_gercek.js      # Source JS file for league data
│
├── tests/                    # Test suite
│   ├── conftest.py           # pytest fixtures
│   └── test_leagues.py       # Leagues endpoint unit tests
│
├── scripts/
│   └── migrate_league_data.py # One-time league data migration
│
├── docs/                     # API Documentation
│   ├── API_DOCUMENTATION.md
│   ├── LEAGUES_API_DOCUMENTATION.md
│   ├── LIVE_API_DOCUMENTATION.md
│   └── openapi.yaml
│
├── Deployment/
│   ├── gunicorn_config.py    # Gunicorn WSGI configuration
│   ├── golsinyali-api.service # Systemd service file
│   ├── start_gunicorn.sh     # Start script
│   ├── stop_gunicorn.sh      # Stop script
│   ├── restart_gunicorn.sh   # Restart script
│   ├── warm_cache.sh         # Cache warming script
│   └── setup_cron.sh         # Cron setup script
│
└── logs/                     # Application logs
    ├── app.log               # Main application log (RotatingFileHandler 10MB×5)
    ├── gunicorn_access.log   # HTTP access log
    └── gunicorn_error.log    # Gunicorn errors
```

### Large Files Warning
These files are very large and should be navigated by searching for specific functions:
- `routes/league_data.py` (1364 lines) - All league data endpoints (standings, matches, stats)
- `routes/utils.py` (1182 lines) - Caching logic, data fetching orchestration
- `parsers.py` (1238 lines) - Static data parsers
- `http_client.py` (1051 lines) - HTTP client with failover
- `analysis/odds_analysis.py` (1117 lines) - Odds analysis logic

---

## API Endpoints Reference

### Match Data Endpoints

| Endpoint | Method | Description | Cache TTL |
|----------|--------|-------------|-----------|
| `/api/v1/match/{id}` | GET | Match details with analysis | 1min (live) / 24h (finished) |
| `/api/v1/match/{id}/h2h` | GET | Head-to-head data | 24 hours |
| `/api/v1/match/{id}/odds` | GET | Odds analysis | 15 minutes |
| `/api/v1/matches/date/{date}` | GET | Matches by date (YYYY-MM-DD) | 5 minutes |
| `/api/v1/matches/today` | GET | Today's matches | 1 minute |
| `/api/v1/matches/tomorrow` | GET | Tomorrow's matches | 5 minutes |
| `/api/v1/matches/yesterday` | GET | Yesterday's matches | 24 hours |

### Live Match Endpoints

| Endpoint | Method | Description | Cache TTL |
|----------|--------|-------------|-----------|
| `/api/v1/matches/live` | GET | All live matches | 30 seconds |
| `/api/v1/matches/live/{id}` | GET | Live match details | 30 seconds |
| `/api/v1/matches/live/{id}/stats` | GET | Live technical stats | 30 seconds |
| `/api/v1/matches/live/{id}/odds` | GET | Live odds (Bet365) | 15 seconds |
| `/api/v1/matches/live/{id}/corners` | GET | Corner statistics | 30 seconds |
| `/api/v1/matches/live/{id}/events` | GET | Match events | 30 seconds |

### League List Endpoints (leagues.py)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/leagues` | GET | Leagues with active matches today |
| `/api/v1/leagues/all` | GET | All leagues from JSON (country/type filter) |
| `/api/v1/leagues/top` | GET | Top leagues + major cups |
| `/api/v1/leagues/countries` | GET | Countries with league counts |
| `/api/v1/leagues/{id}/lookup` | GET | Lookup league by ID from JSON |

### League Data Endpoints (league_data.py)

| Endpoint | Method | Description | Cache TTL |
|----------|--------|-------------|-----------|
| `/api/v1/leagues/{id}/standings` | GET | League table / standings | 12 hours |
| `/api/v1/leagues/{id}/matches` | GET | Season matches (?season=, ?round=) | 48 hours |
| `/api/v1/leagues/{id}/full` | GET | Standings + matches combined | 12 hours |
| `/api/v1/leagues/{id}/info` | GET | League metadata | 7 days |
| `/api/v1/leagues/{id}/team-stats` | GET | Team statistics | 12 hours |
| `/api/v1/leagues/{id}/player-stats` | GET | Top scorer/assist stats | 24 hours |
| `/api/v1/leagues/{id}/handicap-stats` | GET | Handicap/Asian stats | 12 hours |
| `/api/v1/leagues/{id}/current-round` | GET | Current round number | 12 hours |

### Health & Monitoring Endpoints

| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/api/v1/health` | GET | Basic health check | No |
| `/api/v1/health/detailed` | GET | Detailed health | No |
| `/api/v1/cache/status` | GET | Cache configuration | No |
| `/api/v1/cache/stats` | GET | Cache performance metrics | No |
| `/api/v1/cache/clear` | POST | Clear all cache | No* |
| `/api/v1/cache/stats/reset` | POST | Reset stats counters | No* |
| `/api/v1/sources/health` | GET | Data source health metrics | No |
| `/api/v1/sources/force-primary` | POST | Force primary source | No* |
| `/api/v1/sources/reset-metrics` | POST | Reset source metrics | No* |

*Note: Admin endpoints should require API key but currently don't - security improvement needed.

### Auth Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/token` | POST | Generate JWT token (requires API key) |

> **Note:** `/api/v1/teams/*` endpoints are **deprecated** and removed from blueprint registration.

---

## Core Patterns

### Multi-Source Failover Flow
```
Request arrives
    ↓
get_prioritized_sources() → [live3.nowgoal26.com, www.nowgoal.com, www.goaloo.com]
    ↓
For each source:
    ↓
    Try fetch with 3s connect / 5s read timeout
        ↓
    Success? → record_success() → Return data
        ↓
    Failure? → record_failure(error_type) → Try next source
        ↓
All failed? → Return error response, send to Sentry
```

**Configuration** (config.py):
```python
MAX_RETRIES_PER_SOURCE = 0     # No retry, immediate failover
HTTP_TIMEOUT_CONNECT = 3        # Fast connection timeout
HTTP_TIMEOUT_READ = 5           # Fast read timeout
SOURCE_HEALTH_THRESHOLD = 0.3   # 30% error rate triggers swap
CONSECUTIVE_FAIL_THRESHOLD = 10 # 10 consecutive failures triggers swap
MIN_SWAP_INTERVAL = 300         # 5 min minimum between swaps
```

### Caching Strategy

**Smart TTLs** (routes/utils.py:get_smart_cache_timeout):
```python
match_status == 'finished' → 86400s (24 hours)
match_status == 'live'     → 60s    (1 minute)
match_status == 'future'   → 300s   (5 minutes)
data_type == 'h2h'         → 86400s (24 hours)
data_type == 'odds'        → 900s   (15 minutes)
```

**League Cache TTLs** (config.py):
```python
LEAGUE_CACHE_TTL_STANDINGS    = 43200  # 12 hours
LEAGUE_CACHE_TTL_MATCHES      = 172800 # 48 hours
LEAGUE_CACHE_TTL_FULL         = 43200  # 12 hours
LEAGUE_CACHE_TTL_INFO         = 604800 # 7 days
LEAGUE_CACHE_TTL_TEAM_STATS   = 43200  # 12 hours
LEAGUE_CACHE_TTL_PLAYER_STATS = 86400  # 24 hours
LEAGUE_CACHE_TTL_HANDICAP     = 43200  # 12 hours
LEAGUE_CACHE_TTL_CURRENT_ROUND= 43200  # 12 hours
LEAGUE_CACHE_TTL_ODDS         = 300    # 5 minutes
```

**Stale-While-Revalidate Pattern**:
```python
# get_with_background_refresh() / get_with_stale_fallback() flow:
1. Check cache
2. If found (fresh or stale): Return immediately
3. If stale: Start background refresh thread
4. If miss: Fetch fresh, user waits
```

**Request Deduplication**:
```python
# Prevents N concurrent identical requests from making N upstream calls
RequestDeduplicator:
  - First request: Start fetch, store Future
  - Subsequent requests: Wait on same Future
  - All receive same result
```

### Thread Pool Management
```python
# Prevents "can't start new thread" errors
Global Thread Pool: 100 workers (MAX_CONCURRENT_REQUESTS)
Per-Request Workers: 20 max (MAX_WORKERS_PER_REQUEST)

# Usage in http_client.py:
executor = get_global_thread_pool()
future = executor.submit(fetch_with_failover, ...)
```

### Redis Connection Pool
```python
# app.py CACHE_REDIS_CONNECTION_POOL:
max_connections = 50
socket_keepalive = True
socket_connect_timeout = 5
socket_timeout = 5
retry_on_timeout = True
health_check_interval = 30
```

### Config Loading Pattern
All modules import config via `app_config.py` to avoid circular imports:
```python
# CORRECT - use this everywhere
from app_config import current_config
base_url = current_config.NOWGOAL_BASE_URL

# AVOID - causes circular imports
from config import config
```

---

## Configuration Reference

### Environment Variables

**Security (CRITICAL - must change in production):**
```bash
SECRET_KEY=<strong-random-string>
API_SECRET_KEY=<strong-random-string>
JWT_SECRET_KEY=<strong-random-string>
```

**Data Sources:**
```bash
PRIMARY_DATA_SOURCE=https://live3.nowgoal26.com
FALLBACK_DATA_SOURCES=https://www.nowgoal.com,https://www.goaloo.com
LEAGUE_DATA_SOURCE=https://football.nowgoal26.com
```

**Timeouts:**
```bash
HTTP_TIMEOUT_CONNECT=3
HTTP_TIMEOUT_READ=5
HTTP_TIMEOUT_TOTAL=10
```

**Cache:**
```bash
CACHE_TYPE=redis              # 'simple' for no Redis (dev/Lambda)
CACHE_REDIS_HOST=localhost
CACHE_REDIS_PORT=6379
CACHE_REDIS_DB=0
CACHE_DEFAULT_TIMEOUT=1800    # 30 minutes
```

**Thread Pool:**
```bash
MAX_CONCURRENT_REQUESTS=100
MAX_WORKERS_PER_REQUEST=20
```

**League Cache TTLs:**
```bash
LEAGUE_CACHE_TTL_STANDINGS=43200
LEAGUE_CACHE_TTL_MATCHES=172800
LEAGUE_CACHE_TTL_FULL=43200
LEAGUE_CACHE_TTL_INFO=604800
LEAGUE_CACHE_TTL_TEAM_STATS=43200
LEAGUE_CACHE_TTL_PLAYER_STATS=86400
LEAGUE_CACHE_TTL_HANDICAP=43200
LEAGUE_CACHE_TTL_CURRENT_ROUND=43200
LEAGUE_CACHE_TTL_ODDS=300
```

**Monitoring:**
```bash
SENTRY_DSN=<your-sentry-dsn>
SENTRY_TRACES_SAMPLE_RATE=0.1  # 10% in production
SENTRY_ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Configuration Classes (config.py)
```python
DevelopmentConfig:  DEBUG=True,  permissive settings
ProductionConfig:   DEBUG=False, reads all settings from env
TestingConfig:      CACHE_TYPE='null' (no cache for tests)
```

---

## Error Handling

### Custom Exception Flow
```
1. APIError raised (models.py)
   ↓
2. handle_api_error() catches (app.py)
   ↓
3. Log (WARNING for 4xx, ERROR for 5xx)
   ↓
4. Send to Sentry (5xx only, with custom fingerprinting)
   ↓
5. Add Retry-After header (503→60s, 504→30s)
   ↓
6. Return JSON: {"error": "message", "status_code": 404, "success": false}
```

### Sentry Fingerprinting (app.py:sentry_before_send)
Custom rules prevent duplicate Sentry issues:
- SSL/TLS errors → grouped as `ssl-connection-error`
- Connection pool errors → `connection-pool-error`
- Timeouts → `request-timeout-error`
- Upstream 404s → `data-source-404`
- Cache errors → `cache-error`
- Optional endpoint failures → **dropped** (expected behavior)
- `futures unfinished` → **dropped** (upstream timeout noise)

### Logging Levels
```
DEBUG   → Cache operations, status detection, deduplication
INFO    → Request lifecycle, cache hits/misses, source swaps
WARNING → Expected errors (404, 503, 504), preload failures
ERROR   → Unexpected 5xx errors, exceptions
```

---

## Background Tasks

### Automatic Tasks (background_tasks.py)
| Task | Interval | Purpose |
|------|----------|---------|
| Cache Cleanup | 1 hour | Delete old cache entries |
| Log Rotation | 24 hours | Remove logs >7 days old |

Note: Periodic cache refresh is DISABLED - using on-demand stale-while-revalidate instead.

### Multi-Worker Leader Election
In Gunicorn multi-worker setups, background tasks run only in one worker:
```python
LEADER_LOCK_KEY = "golsinyali:background_tasks:leader"
LEADER_LOCK_TTL = 60s       # Leader renews every 30s
# Uses Redis distributed lock to elect one leader worker
```

### Startup Behavior
1. First request triggers cache preload (today's matches + top 5 match details)
2. Background task daemon threads start with leader election
3. Initial cache warm takes ~5-10 seconds

---

## Deployment

### Production Deployment Steps
```bash
# 1. Copy files to server
scp -r . user@server:/var/www/golsinyali_api

# 2. Setup environment
cp .env.production .env
nano .env  # Set strong secrets

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start Redis
sudo systemctl start redis

# 5. Install systemd service
sudo cp golsinyali-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable golsinyali-api
sudo systemctl start golsinyali-api

# 6. Warm cache
./warm_cache.sh http://localhost:8000

# 7. Setup daily cache warming
./setup_cron.sh http://localhost:8000
```

### Gunicorn Configuration (gunicorn_config.py)
```python
Workers:            (CPU cores × 2) + 1
Worker Class:       gevent (10,000 connections each)
Timeout:            90 seconds (allows failover)
Graceful Timeout:   60 seconds
Max Requests:       10,000 (with 1,000 jitter)
Keep-Alive:         5 seconds
```

---

## Common Tasks

### Adding a New Endpoint
1. Create route in appropriate blueprint (routes/*.py)
2. Use `get_with_stale_fallback()` from `cache_utils.py` for caching
3. Import config via `from app_config import current_config` (not from config directly)
4. Raise `APIError` for errors (don't catch, let handler deal with it)
5. Register blueprint in `routes/__init__.py` if creating new file

### Modifying Cache Logic
- Match smart TTLs: `routes/utils.py:get_smart_cache_timeout()`
- League TTLs: `config.py:LEAGUE_CACHE_TTL_*` environment variables
- Stale-while-revalidate: `cache_utils.py:get_with_background_refresh()`
- Stale fallback: `cache_utils.py:get_with_stale_fallback()`
- Cache keys should include all parameters affecting result

### Adding New Data Source
1. Add to `FALLBACK_DATA_SOURCES` env var (comma-separated)
2. Add parsing logic to `parsers.py` if format differs
3. Health tracking is automatic via source_manager.py
4. Test with `/api/v1/sources/health`

### Updating League Data
1. Update `data/leagues_master.json` (generated from `data/league_gercek.js`)
2. Update `data/leagues.json` for league list/lookup endpoints
3. Run `scripts/migrate_league_data.py` if needed for data migration

### Debugging
```bash
# Check if server is running
curl http://localhost:8000/api/v1/health

# View source health
curl http://localhost:8000/api/v1/sources/health

# View cache performance
curl http://localhost:8000/api/v1/cache/stats

# Check logs
tail -f logs/app.log | grep ERROR

# Run tests
pytest tests/ -v
```

---

## Known Issues

### Critical
1. **Admin endpoints unprotected**: `/cache/clear`, `/sources/force-primary`, `/sources/reset-metrics`, `/cache/stats/reset` need API key auth
2. **Large files**: `league_data.py` (1364), `utils.py` (1182), `parsers.py` (1238) should be refactored

### Performance
- Cache hit rate ~40% (target: >70%)
- P50 response time ~3s (target: <2s)
- Failover adds 5-10s on source failure (acceptable)

### Security
- Rate limiting ENABLED (200/min, 3000/hour per IP) with IP whitelist support
- CORS configured for golsinyali.com domains in production
- API key comparison uses `!=` instead of constant-time (timing attack risk)

---

## Testing

**Partial test coverage** - leagues unit tests + manual testing:
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_leagues.py -v

# Manual API tests
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/match/2804405
curl http://localhost:8000/api/v1/matches/today
curl http://localhost:8000/api/v1/matches/live
curl http://localhost:8000/api/v1/leagues/36/standings
curl http://localhost:8000/api/v1/leagues/36/full
```
