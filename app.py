"""
Flask API Application - Modular Architecture
"""
import os
import logging
from flask import Flask
from flask_caching import Cache
from flask_compress import Compress
# from flask_limiter import Limiter  # Rate limiting disabled
from flask_cors import CORS
from dotenv import load_dotenv
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

# Import configuration and modules
from config import config
from security import security_middleware
from http_client import close_all_sessions

# Load environment variables
load_dotenv()

# Initialize Sentry with smart fingerprinting
sentry_dsn = os.getenv('SENTRY_DSN')

def sentry_before_send(event, hint):
    """
    Custom Sentry fingerprinting to group similar errors together.
    This prevents the same root cause from creating multiple issues.
    """
    exception = hint.get('exc_info')
    error_message = event.get('message', '') or ''

    # Get exception message if available
    if exception:
        exc_type, exc_value, _ = exception
        # str(exc_value) can be "" for bare exceptions (e.g. concurrent.futures.TimeoutError())
        # In that case keep the original log message instead of overwriting with empty string
        exc_str = str(exc_value)
        if exc_str:
            error_message = exc_str
        exc_type_name = exc_type.__name__ if exc_type else ''
    else:
        exc_type_name = ''

    # Combine for pattern matching
    full_message = f"{exc_type_name}: {error_message}".lower()

    # --- FINGERPRINTING RULES ---

    # 0a. DROP: Rate limit exceeded — expected behavior, not an error
    if 'ratelimitexceeded' in full_message or '429 too many requests' in full_message:
        return None

    # 0b. DROP: flask-limiter "Empty value" log — root cause fixed in get_rate_limit_key(),
    # this filter handles any remaining noise from older workers still running.
    if 'skipping limit' in full_message and 'empty value' in full_message:
        return None

    # 0c. DROP: Upstream unavailable (503) — expected during source failover
    if 'upstream data sources are temporarily unavailable' in full_message:
        return None

    # 0d. DROP: Optional endpoint failures (data not available for all matches - expected)
    # These are WARNING level logs, not errors. Drop from Sentry entirely.
    optional_endpoints = ['correct_score_odds', 'corner_odds', 'h2h_details',
                          'double_chance_odds', 'first_half_odds']
    if 'all' in full_message and 'sources failed' in full_message:
        for endpoint in optional_endpoints:
            if endpoint in full_message:
                return None

    # 1. SSL/TLS errors - all grouped together
    if any(x in full_message for x in ['ssl', 'tlsv1', 'certificate', 'handshake']):
        event['fingerprint'] = ['ssl-connection-error']
        event['tags'] = event.get('tags', {})
        event['tags']['error_category'] = 'ssl'
        return event

    # 2. Connection/Network errors - grouped by type
    if any(x in full_message for x in ['connectionpool', 'max retries exceeded', 'connection refused', 'connection reset']):
        event['fingerprint'] = ['connection-pool-error']
        event['tags'] = event.get('tags', {})
        event['tags']['error_category'] = 'connection'
        return event

    # 3. Futures unfinished/timeout - drop if it's just upstream timeout
    # These are expected during high load or slow data sources
    if 'futures unfinished' in full_message:
        # Drop events that are just timeout warnings (not critical)
        # Real timeouts will still be tracked via source health metrics
        return None

    # 4. Request timeouts - grouped together
    if any(x in full_message for x in ['timeout', 'timed out', 'read timed out']):
        event['fingerprint'] = ['request-timeout-error']
        event['tags'] = event.get('tags', {})
        event['tags']['error_category'] = 'timeout'
        return event

    # 5. Data source 404s - grouped together
    if '404' in full_message or 'not found' in full_message:
        event['fingerprint'] = ['data-source-404']
        event['tags'] = event.get('tags', {})
        event['tags']['error_category'] = '404'
        return event

    # 6. Cache errors - check if it's caused by upstream fetch failure
    if any(x in full_message for x in ['cache-error', 'redis', 'cache failed']):
        # If caused by futures unfinished (upstream timeout), drop the event
        # This is a symptom of upstream failure, not a cache problem
        if 'futures unfinished' in full_message:
            return None
        # Otherwise group cache errors together
        event['fingerprint'] = ['cache-error']
        event['tags'] = event.get('tags', {})
        event['tags']['error_category'] = 'cache'
        return event

    # 7. Import/Module errors - grouped by module
    if 'importerror' in full_message or 'modulenotfounderror' in full_message:
        event['fingerprint'] = ['import-error']
        event['tags'] = event.get('tags', {})
        event['tags']['error_category'] = 'import'
        return event

    # 8. APIError - group by status code
    if 'apierror' in full_message:
        # Extract status code if present
        import re
        status_match = re.search(r'status[:\s]*(\d{3})', full_message)
        if status_match:
            status_code = status_match.group(1)
            event['fingerprint'] = [f'api-error-{status_code}']
        else:
            event['fingerprint'] = ['api-error-generic']
        event['tags'] = event.get('tags', {})
        event['tags']['error_category'] = 'api_error'
        return event

    # Default: let Sentry use its own fingerprinting
    return event


def sentry_before_breadcrumb(crumb, hint):
    """
    Filter noisy breadcrumbs to keep useful context only.
    """
    # Skip very frequent/noisy breadcrumbs
    category = crumb.get('category', '')
    message = crumb.get('message', '')

    # Keep HTTP requests, errors, and important logs
    if category in ['http', 'error', 'exception']:
        return crumb

    # Skip dedup/cache debug messages (too noisy)
    if any(x in message for x in ['[DEDUP-HIT]', '[DEDUP-MISS]', '[DEDUP-RESULT]']):
        return None

    return crumb


if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FlaskIntegration()],
        # Performance Monitoring — default 0.05 (5%) to avoid quota drain
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '0.05')),
        # Environment
        environment=os.getenv('SENTRY_ENVIRONMENT', 'development'),
        # Include PII (user data, request headers, IP)
        send_default_pii=True,
        # Custom fingerprinting to group similar errors
        before_send=sentry_before_send,
        # Filter noisy breadcrumbs
        before_breadcrumb=sentry_before_breadcrumb,
        # Attach request data for better debugging
        max_breadcrumbs=50,
    )

cache = Cache()

# Initialize Flask app
app = Flask(__name__)

# Load configuration
env = os.getenv('FLASK_ENV', 'development')
app.config.from_object(config[env])

# Configuration from environment - CACHE_TYPE from env var, defaults to 'simple' (no Redis dependency)
app.config['CACHE_TYPE'] = os.getenv('CACHE_TYPE', 'simple')
app.config['CACHE_REDIS_HOST'] = os.getenv('CACHE_REDIS_HOST', 'localhost')
app.config['CACHE_REDIS_PORT'] = int(os.getenv('CACHE_REDIS_PORT', 6379))
app.config['CACHE_REDIS_DB'] = int(os.getenv('CACHE_REDIS_DB', 0))
app.config['CACHE_REDIS_PASSWORD'] = os.getenv('CACHE_REDIS_PASSWORD', None)
app.config['CACHE_DEFAULT_TIMEOUT'] = int(os.getenv('CACHE_DEFAULT_TIMEOUT', 1800))  # 30 minutes

# Redis şifre - CACHE_OPTIONS ile geçirilir (flask-caching 2.3.1)
_redis_pwd = app.config.get('CACHE_REDIS_PASSWORD') or None
if _redis_pwd:
    app.config['CACHE_OPTIONS'] = {'password': _redis_pwd}

# Initialize cache extension
cache.init_app(app)

# ✅ OPTIMIZED: Enable response compression (gzip)
# This reduces response size by ~75-85% (200KB → 30-50KB)
compress = Compress()
compress.init_app(app)

# Set cache instance BEFORE importing routes
from routes.utils import set_cache_instance
set_cache_instance(cache)

# NOW import endpoints (after cache is ready)
from routes import api_bp

# CORS Configuration
if app.config.get('ENABLE_CORS', True):
    # Production için güvenli CORS ayarları
    allowed_origins = [
        'http://localhost:3000',
        'http://localhost:8000',
        'http://127.0.0.1:3000',
        'http://127.0.0.1:8000',
        'https://golsinyali.com',
        'https://www.golsinyali.com',
    ]
    CORS(app, origins=app.config.get('ALLOWED_ORIGINS', allowed_origins))

# Rate Limiter - rate_limiter.py modülünden import et (circular import önleme)
from rate_limiter import limiter
from security import get_rate_limit_key, is_whitelisted

# Storage URI'yi Redis şifresiyle güncelle
_redis_pwd  = app.config.get('CACHE_REDIS_PASSWORD')
_redis_host = app.config.get('CACHE_REDIS_HOST', 'localhost')
_redis_port = app.config.get('CACHE_REDIS_PORT', 6379)
if os.getenv('CACHE_TYPE', 'simple') != 'simple':
    if _redis_pwd:
        _limiter_uri = f"redis://:{_redis_pwd}@{_redis_host}:{_redis_port}/1"
    else:
        _limiter_uri = f"redis://{_redis_host}:{_redis_port}/1"
    limiter._storage_uri = _limiter_uri

limiter.key_func = get_rate_limit_key
limiter.default_limits = ["3000 per hour", "200 per minute"]
limiter.init_app(app)

# Flask-Limiter 4.x'te exempt_when constructor'a verilmeli veya request_filter kullanılmalı
# default_limits_exempt_when attribute set etmek 4.x'te çalışmıyor
@limiter.request_filter
def _whitelist_filter():
    return is_whitelisted()

# Initialize security middleware
security_middleware.init_app(app)

# Register main blueprint
app.register_blueprint(api_bp, url_prefix='/api/v1')

# ========================================================================
# SWAGGER UI — Interactive API Documentation
# Served at /api/docs  (no package installation required, uses CDN)
# ========================================================================
from flask import send_from_directory, Response
import json as _json

@app.route('/api/docs')
def swagger_ui():
    """Interactive API documentation powered by Swagger UI."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Golsinyali API — Documentation</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
  <style>
    body { margin: 0; padding: 0; background: #fafafa; }
    .topbar { display: none !important; }
    .swagger-ui .info .title { color: #1a1a2e; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({
      url: '/api/docs/openapi.yaml',
      dom_id: '#swagger-ui',
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout: 'BaseLayout',
      deepLinking: true,
      displayRequestDuration: true,
      filter: true,
      tryItOutEnabled: true,
      persistAuthorization: true,
    });
  </script>
</body>
</html>"""
    return Response(html, mimetype='text/html')


@app.route('/api/docs/openapi.yaml')
def openapi_spec():
    """Serve the OpenAPI specification file."""
    import os
    spec_path = os.path.join(os.path.dirname(__file__), 'docs', 'openapi.yaml')
    with open(spec_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return Response(content, mimetype='application/x-yaml')


# Configure logging
from logging.handlers import RotatingFileHandler
import os

log_level = getattr(logging, os.getenv('LOG_LEVEL', 'INFO').upper())
log_handlers = [
    RotatingFileHandler(
        'logs/app.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    ),
    logging.StreamHandler()
]

logging.basicConfig(
    level=log_level,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=log_handlers
)
logger = logging.getLogger(__name__)

# Error handlers
# Import APIError for error handling
from models import APIError

@app.errorhandler(APIError)
def handle_api_error(error):
    """Handle custom APIError exceptions"""
    # Log expected errors (404, 503, 504) as WARNING, unexpected as ERROR
    if error.status_code in [404, 503, 504]:
        logger.warning(
            f"APIError: {error.message} (status: {error.status_code})",
            extra={'payload': error.payload}
        )
    else:
        logger.error(
            f"APIError: {error.message} (status: {error.status_code})",
            extra={'payload': error.payload}
        )

    # Send to Sentry for all 5xx errors (including 503, 504)
    # 503 = Service Unavailable (upstream temporarily down)
    # 504 = Gateway Timeout (upstream slow/timeout)
    if error.status_code >= 500 and sentry_dsn:
        # Add context for better debugging
        with sentry_sdk.push_scope() as scope:
            scope.set_context("api_error", {
                "message": error.message,
                "status_code": error.status_code,
                "payload": error.payload
            })
            sentry_sdk.capture_exception(error)

    # Build response
    response_data = {
        'error': error.message,
        'status_code': error.status_code,
        'success': False
    }

    # TASK 2: Add Retry-After header for 503/504 errors
    from flask import make_response, jsonify
    response = make_response(jsonify(response_data), error.status_code)

    # Add Retry-After header for retryable errors
    if error.status_code == 503:
        # Service Unavailable - suggest retry in 60 seconds
        response.headers['Retry-After'] = '60'
    elif error.status_code == 504:
        # Gateway Timeout - suggest retry in 30 seconds
        response.headers['Retry-After'] = '30'
    elif error.status_code == 404:
        # Not Found - don't suggest retry (permanent error)
        pass

    return response

@app.errorhandler(429)
def handle_rate_limit(error):
    """Handle rate limit exceeded — expected behavior, never send to Sentry"""
    from flask import jsonify
    retry_after = getattr(error, 'retry_after', 60)
    response = jsonify({
        'error': 'Rate limit exceeded. Please slow down.',
        'success': False
    })
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    return response


@app.errorhandler(Exception)
def handle_exception(error):
    """Handle all unhandled exceptions"""
    # Skip rate limit errors — handled above, should never reach here
    from flask_limiter.errors import RateLimitExceeded
    if isinstance(error, RateLimitExceeded):
        return handle_rate_limit(error)

    # Log the full exception with stack trace
    logger.exception(f"Unhandled exception: {str(error)}")

    # Send to Sentry
    if sentry_dsn:
        sentry_sdk.capture_exception(error)

    # Return generic error response
    return {
        'error': 'Internal server error',
        'success': False
    }, 500

@app.errorhandler(404)
def handle_not_found(error):
    """Handle 404 errors"""
    logger.warning(f"Not found: {str(error)}")
    return {
        'error': 'Resource not found',
        'success': False
    }, 404

# Application lifecycle
@app.teardown_appcontext
def close_session(error):
    """Clean up session on request end"""
    if error:
        logger.warning(f"Request ended with error (already logged by error handler): {str(error)}")

# Cleanup on app shutdown
import atexit

def cleanup():
    """Cleanup function for app shutdown"""
    logger.info("Application shutting down...")

    # Stop background tasks
    try:
        stop_background_tasks()
        logger.info("✅ Background tasks stopped")
    except Exception as e:
        logger.error(f"❌ Error stopping background tasks: {e}")

    # Close HTTP session pools
    try:
        close_all_sessions()
        logger.info("✅ HTTP session pools closed")
    except Exception as e:
        logger.error(f"❌ Error closing HTTP sessions: {e}")

    logger.info("✅ Application cleanup completed")

atexit.register(cleanup)

# Initialize logging on module load
logger.info("Application starting up...")

# ========================================================================
# CACHE PRELOADING (P1 Optimization)
# ========================================================================
def preload_cache():
    """
    Preload today's matches into cache on application startup.
    This eliminates cold start delays for the first requests.

    P1 Optimization: Improves first-request performance by warming the cache.
    """
    try:
        import logging
        logger = logging.getLogger(__name__)

        from datetime import date
        from routes.utils import fetch_date_matches_cached

        logger.info("🔥 [CACHE-PRELOAD] Starting cache warm-up...")

        # Fetch today's matches (this will populate the cache)
        today_str = date.today().strftime('%Y-%m-%d')
        matches = fetch_date_matches_cached(today_str, use_cache=True)

        # matches is a dict with 'matches' key containing the list
        if matches and 'matches' in matches:
            match_list = matches['matches']
            match_count = len(match_list)
            logger.info(f"✅ [CACHE-PRELOAD] Successfully preloaded {match_count} matches for {today_str}")

            # Optional: Preload first 5 match details (most popular)
            preload_count = min(5, match_count)
            if preload_count > 0:
                from routes.utils import fetch_match_data_with_analysis_cached
                logger.info(f"🔥 [CACHE-PRELOAD] Preloading top {preload_count} match details...")

                preloaded = 0
                for i, match in enumerate(match_list):
                    if i >= preload_count:
                        break
                    try:
                        match_id = match.get('match_id')
                        if match_id:
                            fetch_match_data_with_analysis_cached(match_id, use_cache=True)
                            preloaded += 1
                            logger.info(f"   ✅ Preloaded match {match_id} ({preloaded}/{preload_count})")
                    except Exception as e:
                        logger.warning(f"⚠️ [CACHE-PRELOAD] Failed to preload match {match_id}: {e}")

                logger.info(f"✅ [CACHE-PRELOAD] Preloaded {preloaded}/{preload_count} match details")
        else:
            logger.warning("⚠️ [CACHE-PRELOAD] No matches found for today")

    except Exception as e:
        logger.error(f"❌ [CACHE-PRELOAD] Cache warm-up failed: {e}")
        # Don't crash the app if preload fails
        pass

# ========================================================================
# BACKGROUND TASKS (Cache Refresh, Cleanup, Log Rotation)
# ========================================================================
from background_tasks import init_background_tasks, stop_background_tasks

# Initialize background tasks after cache is ready
_background_tasks_started = False

def start_background_tasks_once():
    """Start background tasks only once"""
    global _background_tasks_started
    if not _background_tasks_started:
        _background_tasks_started = True
        logger.info("🚀 Starting background tasks (cache refresh, cleanup, logs)...")
        init_background_tasks(cache)

# Register preload function to run after first request
# Using a flag to ensure it only runs once
_cache_preloaded = False

@app.before_request
def preload_cache_once():
    """Run cache preload and background tasks only once on first request"""
    global _cache_preloaded
    if not _cache_preloaded:
        _cache_preloaded = True
        import threading

        # Run cache preload in background thread
        thread = threading.Thread(target=preload_cache)
        thread.daemon = True
        thread.start()

        # Start background tasks (refresh, cleanup, etc.)
        start_background_tasks_once()

if __name__ == '__main__':
    # Start background tasks immediately on startup
    logger.info("🚀 Starting background tasks on startup...")
    start_background_tasks_once()

    # Production için host='0.0.0.0' kullan
    # Local development için host='127.0.0.1' kullanabilirsin
    app.run(host='0.0.0.0', port=8000, debug=False)