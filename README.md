# Golsinyali Football API

High-performance football match data API with multi-source failover, intelligent caching, and comprehensive analysis features.

## Features

- **Multi-Source Failover**: Automatic failover between data sources (nowgoal26.com, goaloo.com) with health tracking
- **Intelligent Caching**: Redis-backed hybrid caching with stale-while-revalidate pattern
- **Real-Time Live Data**: Live match updates with 30-second refresh intervals
- **Comprehensive Analysis**: H2H statistics, odds analysis, team performance, and predictions
- **Production Ready**: Gunicorn/gevent deployment, systemd service, Sentry error tracking

## Quick Start

### Prerequisites

- Python 3.9+
- Redis Server
- Virtual Environment (recommended)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd golsinyali_api_mevcut

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your configuration

# Start Redis
redis-server

# Run development server
python app.py
```

### Production Deployment

```bash
# Install systemd service
sudo cp golsinyali-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable golsinyali-api
sudo systemctl start golsinyali-api

# Warm cache
./warm_cache.sh http://localhost:8000

# Setup daily cache warming (6:00 AM)
./setup_cron.sh http://localhost:8000
```

## API Endpoints

### Match Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/match/{id}` | GET | Match details with analysis |
| `/api/v1/match/{id}/h2h` | GET | Head-to-head data |
| `/api/v1/match/{id}/odds` | GET | Odds analysis |
| `/api/v1/matches/today` | GET | Today's matches |
| `/api/v1/matches/date/{date}` | GET | Matches by date (YYYY-MM-DD) |
| `/api/v1/matches/tomorrow` | GET | Tomorrow's matches |
| `/api/v1/matches/yesterday` | GET | Yesterday's matches |

### Live Matches

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/matches/live` | GET | All live matches |
| `/api/v1/matches/live/{id}` | GET | Live match details |
| `/api/v1/matches/live/{id}/stats` | GET | Live technical statistics |
| `/api/v1/matches/live/{id}/odds` | GET | Live odds (Bet365) |
| `/api/v1/matches/live/{id}/corners` | GET | Corner statistics |
| `/api/v1/matches/live/{id}/events` | GET | Match events (goals, cards) |

### Health & Monitoring

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Basic health check |
| `/api/v1/health/detailed` | GET | Detailed health information |
| `/api/v1/cache/stats` | GET | Cache performance metrics |
| `/api/v1/sources/health` | GET | Data source health metrics |

### Other

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/token` | POST | Generate JWT token |
| `/api/v1/leagues` | GET | Get all leagues |
| `/api/v1/leagues/{id}/matches` | GET | Matches by league |
| `/api/v1/teams/search?q=` | GET | Search teams |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Flask Application                        │
│  Rate Limiting (200/min) │ CORS │ Compression │ Sentry      │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                    Routes (Blueprints)                       │
│  matches.py │ live.py │ health.py │ leagues.py │ teams.py   │
└─────────────────────────────┬───────────────────────────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    │                         │                         │
┌───▼───────┐        ┌───────▼────────┐        ┌───────▼───────┐
│   Cache   │        │  HTTP Client   │        │   Analysis    │
│   Layer   │        │  Thread Pool   │        │    Modules    │
│  (Redis)  │        │ (20 workers)   │        │  (H2H, Odds)  │
└───────────┘        └───────┬────────┘        └───────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼────────┐    │     ┌────────▼────────┐
     │ Source Manager  │    │     │    Parsers      │
     │ Health Tracking │◄───┘     │  HTML/JSON      │
     │ Auto Failover   │          │  Parsing        │
     └────────┬────────┘          └─────────────────┘
              │
    ┌─────────▼──────────────────────────────┐
    │            Data Sources                 │
    │  Primary: live3.nowgoal26.com          │
    │  Fallback: www.goaloo.com              │
    └─────────────────────────────────────────┘
```

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```bash
# Flask
FLASK_ENV=production
SECRET_KEY=your-secret-key

# Data Sources
PRIMARY_DATA_SOURCE=https://live3.nowgoal26.com
FALLBACK_DATA_SOURCES=https://www.goaloo.com

# Cache (Redis)
CACHE_TYPE=redis
CACHE_REDIS_HOST=localhost
CACHE_REDIS_PORT=6379
CACHE_DEFAULT_TIMEOUT=1800

# Timeouts (Fast Failover)
HTTP_TIMEOUT_CONNECT=3
HTTP_TIMEOUT_READ=5
MAX_RETRIES_PER_SOURCE=0

# Thread Pool
MAX_CONCURRENT_REQUESTS=20
MAX_WORKERS_PER_REQUEST=8

# Monitoring
SENTRY_DSN=your-sentry-dsn
LOG_LEVEL=INFO
```

### Gunicorn Configuration

The `gunicorn_config.py` is optimized for high-concurrency:

- **Workers**: `(CPU cores × 2) + 1`
- **Worker Class**: `gevent` (10,000 connections each)
- **Timeout**: 90 seconds (allows for failover)
- **Max Requests**: 10,000 per worker (with jitter)

## Caching Strategy

### Smart TTLs

| Data Type | Cache TTL | Reason |
|-----------|-----------|--------|
| Finished matches | 24 hours | Data never changes |
| Live matches | 1 minute | Frequent updates |
| Future matches | 5 minutes | Moderate changes |
| H2H data | 24 hours | Historical data |
| Odds data | 15 minutes | Changes frequently |
| Live odds | 15 seconds | Real-time data |

### Stale-While-Revalidate

The API implements a stale-while-revalidate pattern:
1. Return cached data immediately (even if stale)
2. Trigger background refresh for stale data
3. Users never wait for fresh data

### Request Deduplication

Concurrent identical requests share the same fetch operation, preventing duplicate upstream calls.

## Multi-Source Failover

### Configuration

```python
MAX_RETRIES_PER_SOURCE = 0      # No retry, immediate failover
HTTP_TIMEOUT_CONNECT = 3         # 3 second connection timeout
HTTP_TIMEOUT_READ = 5            # 5 second read timeout
SOURCE_HEALTH_THRESHOLD = 0.3    # 30% error rate triggers swap
CONSECUTIVE_FAIL_THRESHOLD = 10  # 10 consecutive failures triggers swap
MIN_SWAP_INTERVAL = 300          # 5 min minimum between swaps
```

### Health Tracking

The system tracks:
- Error rate per source (sliding window of 100 requests)
- Consecutive failures
- Error types (timeout, 404, 5xx)
- Automatic primary source swapping

## Management Scripts

| Script | Description |
|--------|-------------|
| `./start_gunicorn.sh` | Start server (supports --daemon, --reload) |
| `./stop_gunicorn.sh` | Stop server (supports --force) |
| `./restart_gunicorn.sh` | Restart server |
| `./warm_cache.sh` | Pre-warm cache with today's matches |
| `./setup_cron.sh` | Setup daily cache warming |
| `./update_base_url.sh` | Interactive data source configuration |

## Monitoring

### Health Endpoints

```bash
# Basic health
curl http://localhost:8000/api/v1/health

# Cache statistics
curl http://localhost:8000/api/v1/cache/stats

# Data source health
curl http://localhost:8000/api/v1/sources/health
```

### Logs

```bash
# Application logs
tail -f logs/app.log

# Gunicorn access logs
tail -f logs/gunicorn_access.log

# Gunicorn error logs
tail -f logs/gunicorn_error.log

# Systemd logs
sudo journalctl -u golsinyali-api -f
```

### Sentry Integration

All 5xx errors are automatically sent to Sentry with:
- Error details and stack traces
- Request context
- Custom error metadata

## Development

### Project Structure

```
golsinyali_api_mevcut/
├── app.py                  # Flask application entry point
├── config.py               # Configuration classes
├── models.py               # Data models and validation
├── http_client.py          # HTTP client with failover
├── cache_utils.py          # Caching layer
├── source_manager.py       # Health tracking and failover
├── parsers.py              # Data parsers (static)
├── live_parsers.py         # Data parsers (live)
├── security.py             # Authentication
├── background_tasks.py     # Background jobs
├── routes/                 # API endpoints
│   ├── matches.py
│   ├── live.py
│   ├── health.py
│   ├── auth.py
│   ├── leagues.py
│   ├── teams.py
│   └── utils.py
├── analysis/               # Analysis modules
│   ├── h2h.py
│   ├── odds_analysis.py
│   ├── team_performance.py
│   └── final_predictions.py
└── logs/                   # Application logs
```

### Adding a New Endpoint

1. Create route in appropriate blueprint (`routes/*.py`)
2. Use caching utilities from `routes/utils.py`
3. Raise `APIError` for errors
4. Register blueprint if new file

### Testing

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Match details
curl http://localhost:8000/api/v1/match/2804405

# Today's matches
curl http://localhost:8000/api/v1/matches/today

# Live matches
curl http://localhost:8000/api/v1/matches/live
```

## Performance

### Current Metrics

- Cache hit rate: ~40% (target: >70%)
- P50 response time: ~3s (target: <2s)
- Failover time: 5-10s on source failure

### Optimizations

- Connection pooling (20 connections per source)
- Thread pool limiting (20 global workers)
- Response compression (gzip)
- Request deduplication
- Smart cache TTLs

## Security

### Features

- Rate limiting: 200/min, 3000/hour per IP
- CORS: Configured for specific domains
- JWT authentication (optional)
- API key authentication for admin endpoints
- Security headers (X-Frame-Options, HSTS, etc.)

### Known Issues

1. Admin endpoints (`/cache/clear`, `/sources/force-primary`) need API key protection
2. API key comparison should use constant-time comparison

## Dependencies

### Core

- Flask (Web framework)
- Gunicorn + gevent (Production server)
- Redis + flask-caching (Caching)
- BeautifulSoup4 + lxml (Parsing)
- requests (HTTP client)

### Security

- PyJWT (JWT tokens)
- flask-limiter (Rate limiting)
- flask-cors (CORS)

### Monitoring

- sentry-sdk (Error tracking)

### Performance

- flask-compress (Response compression)
- boto3 (AWS Lambda integration)

## License

This project is proprietary software.

## Support

For issues and questions, please contact the development team.
