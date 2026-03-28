"""
HTTP client utilities for external API requests with multi-source failover support

Features:
- Multi-source failover (automatic retry with alternative sources)
- Intelligent retry logic with exponential backoff
- Health tracking integration
- Graceful degradation for partial failures
- Enhanced error logging and monitoring
- Thread pool limiting to prevent resource exhaustion
"""
# REMOVED: import asyncio (unused async code)
# REMOVED: import aiohttp (unused async code)
import time
import logging
import json
import requests
import os
import ipaddress
from datetime import datetime
from typing import Tuple, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# Merkezi config loader
from app_config import current_config

logger = logging.getLogger(__name__)

# ============================================================================
# SAFE HTTP GET - Redirect doğrulamalı istek
# ============================================================================

def _is_safe_redirect(url):
    """Redirect hedefinin güvenli olup olmadığını kontrol et.
    İzin verilen hostlar config.ALLOWED_SOURCE_HOSTS'tan okunur —
    yeni domain için sadece .env'deki FALLBACK_DATA_SOURCES'ı güncelle.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # hostname, IP değil - normal
        allowed_hosts = current_config.ALLOWED_SOURCE_HOSTS
        for allowed in allowed_hosts:
            if hostname == allowed or hostname.endswith('.' + allowed):
                return True
        return False
    except Exception:
        return False


def safe_get(session, url, **kwargs):
    """Redirect doğrulamalı güvenli GET isteği (allow_redirects=False ile başlar)"""
    kwargs.pop('allow_redirects', None)
    response = session.get(url, allow_redirects=False, **kwargs)

    redirect_count = 0
    max_redirects = 5

    while response.status_code in (301, 302, 303, 307, 308) and redirect_count < max_redirects:
        redirect_url = response.headers.get('Location')
        if not redirect_url:
            break
        if not _is_safe_redirect(redirect_url):
            logger.warning(f"Güvensiz redirect engellendi: {url} → {redirect_url}")
            break
        response = session.get(redirect_url, allow_redirects=False, **kwargs)
        redirect_count += 1

    return response

# ============================================================================
# GLOBAL THREAD POOL (Prevents "can't start new thread" errors)
# ============================================================================
_global_thread_pool = None
_thread_pool_lock = None

def get_global_thread_pool():
    """
    Get or create global thread pool with limited workers

    This prevents thread exhaustion by reusing a fixed pool of threads
    """
    global _global_thread_pool, _thread_pool_lock

    if _thread_pool_lock is None:
        import threading
        _thread_pool_lock = threading.Lock()

    if _global_thread_pool is None:
        with _thread_pool_lock:
            if _global_thread_pool is None:
                max_workers = current_config.MAX_CONCURRENT_REQUESTS
                _global_thread_pool = ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="http_worker"
                )
                logger.info(f"🔧 Global thread pool initialized with {max_workers} workers")

    return _global_thread_pool

# ============================================================================
# HTTP CONNECTION POOL (Prevents new TCP connection per request)
# ============================================================================
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import threading

_http_sessions = {}
_session_lock = threading.Lock()

def get_http_session(base_url=None):
    """
    Get or create HTTP session with connection pooling for a specific base URL

    Connection pooling dramatically improves performance by:
    - Reusing TCP connections (no handshake overhead)
    - Reusing SSL/TLS sessions (no certificate exchange)
    - Avoiding DNS lookups for subsequent requests

    Args:
        base_url: Base URL to create session for (used as cache key)

    Returns:
        requests.Session with connection pooling configured
    """
    global _http_sessions

    # Use base_url as key, or 'default' if not specified
    session_key = base_url or 'default'

    # Return existing session if available
    if session_key in _http_sessions:
        return _http_sessions[session_key]

    # Create new session with connection pooling
    with _session_lock:
        # Double-check after acquiring lock
        if session_key in _http_sessions:
            return _http_sessions[session_key]

        logger.info(f"🔌 Creating new HTTP session pool for: {session_key}")

        session = requests.Session()

        # Configure connection pool with HTTPAdapter
        adapter = HTTPAdapter(
            pool_connections=100,     # Number of connection pools to cache (increased for Lambda 1000 concurrency)
            pool_maxsize=100,         # Maximum number of connections to save in the pool
            max_retries=0,            # We handle retries manually
            pool_block=False          # Don't block when pool is full
        )

        # Mount adapter for both http and https
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        # Configure session defaults
        session.headers.update({
            'Connection': 'keep-alive',
            'Keep-Alive': 'timeout=30, max=100'
        })

        # Store session for reuse
        _http_sessions[session_key] = session

        # Warmup: Fetch homepage to get anti-bot cookies (LS_ACCESS_TOKEN)
        # Without this cookie, API requests return {"code":1002} or {"code":1004}
        # Always warmup for nowgoal/goaloo - even with Lambda, direct HTTP is used as fallback
        if base_url and ('nowgoal' in base_url or 'goaloo' in base_url):
            try:
                warmup_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
                warmup_response = safe_get(
                    session,
                    f"{base_url}/",
                    headers=warmup_headers,
                    timeout=(5, 10)
                )
                if warmup_response.status_code == 200:
                    logger.info(f"🍪 Cookie warmup successful for {base_url}, cookies: {list(session.cookies.keys())}")
                else:
                    logger.warning(f"⚠️ Cookie warmup returned {warmup_response.status_code} for {base_url}")
            except Exception as e:
                logger.warning(f"⚠️ Cookie warmup failed for {base_url}: {e}")

        logger.info(f"✅ HTTP session pool created with 100 connections for: {session_key}")

    return session

def close_all_sessions():
    """
    Close all HTTP sessions and connection pools

    Should be called on application shutdown to properly cleanup resources
    """
    global _http_sessions

    with _session_lock:
        for key, session in _http_sessions.items():
            try:
                session.close()
                logger.info(f"🔌 Closed HTTP session pool: {key}")
            except Exception as e:
                logger.warning(f"Error closing session {key}: {e}")

        _http_sessions.clear()

# Import source manager (lazy import to avoid circular dependencies)
_source_manager = None

def get_source_manager():
    """Lazy import of source manager to avoid circular imports"""
    global _source_manager
    if _source_manager is None:
        from source_manager import get_source_manager as _get_sm
        _source_manager = _get_sm()
    return _source_manager

# AWS Lambda client for IP rotation
try:
    import boto3
    from botocore.config import Config

    # Increase connection pool size to handle concurrent requests
    # Default is 10, which causes "Connection pool is full" errors
    lambda_config = Config(
        max_pool_connections=200,  # Increased for Lambda 1000 concurrency
        connect_timeout=5,
        read_timeout=20,           # Batch modda birden fazla URL çekiyor, 20s yeterli
        retries={'max_attempts': 0}  # Retry yok - Lambda başarısızsa hemen direkt HTTP'ye düş
    )

    lambda_client = boto3.client(
        'lambda',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY'),
        aws_secret_access_key=os.getenv('AWS_SECRET_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        config=lambda_config
    )
    USE_LAMBDA = True
    logger.info("[INFO] AWS Lambda client initialized with max_pool_connections=200")
except Exception as e:
    logger.warning(f"[WARN] Lambda not available: {e}, using direct requests")
    USE_LAMBDA = False

# ============================================================================
# BATCH LAMBDA FETCH
# ============================================================================

def fetch_batch_via_lambda(url_dict: dict) -> dict:
    """
    Birden fazla URL'i tek Lambda invocation ile fetch et.

    Args:
        url_dict: {"h2h": "https://...", "odds": "https://...", ...}

    Returns:
        {"h2h": {"statusCode": 200, "body": "..."}, "odds": {...}, ...}
        Hata durumunda boş dict döner.
    """
    if not USE_LAMBDA or not url_dict:
        return {}

    try:
        logger.info(f"[LAMBDA-BATCH] Fetching {len(url_dict)} URLs in single invocation")
        start_time = time.time()

        lambda_response = lambda_client.invoke(
            FunctionName='goaloo-scraper',
            InvocationType='RequestResponse',
            Payload=json.dumps({'urls': url_dict})
        )

        result = json.loads(lambda_response['Payload'].read())

        elapsed = time.time() - start_time

        if 'results' in result:
            results = result['results']
            success_count = sum(1 for r in results.values() if isinstance(r, dict) and r.get('statusCode') == 200)
            logger.info(f"[LAMBDA-BATCH] Done: {success_count}/{len(url_dict)} successful in {elapsed:.2f}s")
            return results
        else:
            logger.warning(f"[LAMBDA-BATCH] Unexpected response format: {str(result)[:200]}")
            return {}

    except Exception as e:
        logger.warning(f"[LAMBDA-BATCH] Failed: {type(e).__name__}: {e}")
        return {}


# ============================================================================
# URL REDIRECT DETECTION & AUTO-UPDATE
# ============================================================================

def extract_base_url(url: str) -> str:
    """
    Extract base URL from full URL

    Example: https://live2.nowgoal26.com/match/123 -> https://live2.nowgoal26.com
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_same_domain_family(base1: str, base2: str) -> bool:
    """
    Check if two base URLs belong to the same domain family.

    Example: live3.nowgoal26.com and live4.nowgoal26.com are the same family.
    This handles load-balancing redirects that shouldn't trigger source swaps.
    """
    from urllib.parse import urlparse
    host1 = urlparse(base1).hostname or ''
    host2 = urlparse(base2).hostname or ''

    # Extract root domain (last 2 parts: e.g., nowgoal26.com)
    parts1 = host1.split('.')
    parts2 = host2.split('.')

    root1 = '.'.join(parts1[-2:]) if len(parts1) >= 2 else host1
    root2 = '.'.join(parts2[-2:]) if len(parts2) >= 2 else host2

    return root1 == root2


def handle_url_redirect(original_url: str, final_url: str, source_url: str):
    """
    Handle URL redirect detection and update primary source.

    Same-domain-family redirects (e.g., live3.nowgoal26.com → live4.nowgoal26.com):
      - Update primary so subsequent requests go directly to new subdomain (no redirect overhead)
      - REPLACE old source in all_sources (don't append - prevents phantom source accumulation)
      - Transfer health metrics from old to new
      - Short cooldown (30s) to prevent rapid ping-pong

    Cross-domain redirects:
      - Full swap with standard rate limit (300s)

    Args:
        original_url: Original request URL
        final_url: Final URL after redirect(s)
        source_url: Base source URL that was used
    """
    original_base = extract_base_url(original_url)
    final_base = extract_base_url(final_url)

    # Only handle if base URL actually changed
    if original_base == final_base:
        return

    same_family = _is_same_domain_family(original_base, final_base)

    try:
        source_manager = get_source_manager()

        with source_manager.manager_lock:
            # Determine which source entry is being redirected
            redirected_source = None
            if source_manager.current_primary in (original_base, source_url):
                redirected_source = source_manager.current_primary
            else:
                # Not the primary, ignore
                return

            # Rate limit: short cooldown for same-family, full cooldown for cross-domain
            cooldown = 30 if same_family else source_manager.min_swap_interval
            if source_manager.last_swap_time:
                elapsed = (datetime.utcnow() - source_manager.last_swap_time).total_seconds()
                if elapsed < cooldown:
                    return

            # Already pointing to final_base, nothing to do
            if source_manager.current_primary == final_base:
                return

            old_primary = source_manager.current_primary

            if same_family:
                # Same domain family: REPLACE old source (don't accumulate)
                # Replace in all_sources list
                for i, s in enumerate(source_manager.all_sources):
                    if s == old_primary:
                        source_manager.all_sources[i] = final_base
                        break

                # Transfer health metrics (new subdomain inherits old one's track record)
                if old_primary in source_manager.source_metrics:
                    old_metrics = source_manager.source_metrics.pop(old_primary)
                    old_metrics.source_url = final_base
                    source_manager.source_metrics[final_base] = old_metrics
                elif final_base not in source_manager.source_metrics:
                    from source_manager import SourceHealthMetrics
                    source_manager.source_metrics[final_base] = SourceHealthMetrics(final_base, source_manager.window_size)

                # Update primary
                source_manager.current_primary = final_base
                source_manager.last_swap_time = datetime.utcnow()

                # Also update the initial primary reference so swap-back works
                if source_manager.primary_source == old_primary:
                    source_manager.primary_source = final_base

                logger.info(f"🔄 Subdomain updated: {old_primary} → {final_base}")
            else:
                # Cross-domain: add as new source if not exists
                source_manager.current_primary = final_base
                source_manager.last_swap_time = datetime.utcnow()

                if final_base not in source_manager.source_metrics:
                    from source_manager import SourceHealthMetrics
                    source_manager.source_metrics[final_base] = SourceHealthMetrics(final_base, source_manager.window_size)
                    source_manager.all_sources.append(final_base)

                logger.warning(f"🔄 Cross-domain redirect: {old_primary} → {final_base}")

    except Exception as e:
        logger.warning(f"Failed to handle redirect: {e}")


# ============================================================================
# MULTI-SOURCE FAILOVER FUNCTIONS
# ============================================================================

def fetch_single_url_with_retry(
    key: str,
    url: str,
    max_retries: int = 2,
    source_url: Optional[str] = None,
    skip_lambda: bool = False
) -> Tuple[str, Any, str, float]:
    """
    Fetch a single URL with retry logic (for a SINGLE source)
    Uses AWS Lambda for IP rotation if available (unless skip_lambda=True)

    Args:
        key: Data key (e.g., 'h2h_details', 'corner_odds')
        url: Full URL to fetch
        max_retries: Maximum number of retries for this source
        source_url: Base URL of the source (for logging)
        skip_lambda: Skip Lambda and use direct HTTP only (batch already tried Lambda)

    Returns:
        Tuple: (key, content, content_type, fetch_time)

    Raises:
        requests.Timeout: If timeout occurs after all retries
        requests.HTTPError: If HTTP error occurs
        Exception: For other errors
    """
    start_time = time.time()
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # Exponential backoff
                wait_time = current_config.RETRY_BACKOFF_FACTOR * (2 ** (attempt - 1))
                logger.info(f"   🔄 Retry {attempt}/{max_retries} for {key} after {wait_time:.1f}s")
                time.sleep(wait_time)

            logger.debug(f"   📤 Fetching {key} from {url}")

            # Try Lambda first (IP rotation), fallback to direct request
            response_text = None
            response_status = None

            if USE_LAMBDA and not skip_lambda:
                try:
                    logger.debug(f"   🔶 Attempting Lambda fetch for {key}")
                    lambda_response = lambda_client.invoke(
                        FunctionName='goaloo-scraper',
                        InvocationType='RequestResponse',
                        Payload=json.dumps({'url': url})
                    )

                    result = json.loads(lambda_response['Payload'].read())

                    if result.get('statusCode') == 200:
                        response_text = result['body']
                        response_status = 200
                        logger.debug(f"   ✅ Lambda fetch successful for {key}")
                    else:
                        logger.warning(f"   ⚠️ Lambda returned non-200: {result.get('statusCode')}")
                        response_status = result.get('statusCode', 500)
                        # Will fall through to direct request

                except Exception as lambda_error:
                    logger.warning(f"   ⚠️ Lambda error for {key}: {str(lambda_error)}, falling back to direct request")
                    # Will fall through to direct request

            # Direct request (if Lambda failed or not available)
            if response_text is None:
                logger.debug(f"   📡 Direct HTTP fetch for {key}")

                # Get headers with appropriate base URL
                headers = get_request_headers(source_url)

                # Get session with connection pool for this source
                session = get_http_session(source_url)

                # Make request with config timeouts using session pool
                response = safe_get(
                    session,
                    url,
                    headers=headers,
                    timeout=(
                        current_config.HTTP_TIMEOUT_CONNECT,
                        current_config.HTTP_TIMEOUT_READ
                    )
                )

                response_text = response.text
                response_status = response.status_code

                # Check for redirect and auto-update source if needed
                if response.history:
                    handle_url_redirect(url, response.url, source_url)

            # Process response based on status code

            # Check for retryable status codes (404, 502, 503, 504)
            # 404 can be transient if server is temporarily down/slow
            if response_status in [404, 502, 503, 504] and attempt < max_retries:
                logger.warning(f"   ⚠️ Transient error {response_status} for {key}, will retry")
                last_error = f"HTTP {response_status}"
                continue

            # Raise for other HTTP errors (non-200)
            if response_status != 200:
                raise requests.HTTPError(f"HTTP {response_status}", response=type('obj', (object,), {'status_code': response_status})())

            fetch_time = time.time() - start_time
            logger.debug(f"   ✅ Fetched {key} in {fetch_time:.2f}s")

            # Parse response based on key type
            if key == 'h2h_details':
                return key, response_text, 'html', fetch_time
            else:
                # Try to parse as JSON
                try:
                    json_data = json.loads(response_text)
                    return key, json_data, 'json', fetch_time
                except json.JSONDecodeError:
                    logger.warning(f"   ⚠️ Failed to parse JSON for {key}")
                    return key, {"error": "Invalid JSON response"}, 'error', fetch_time
                except:
                    logger.warning(f"   ⚠️ Response is not JSON for {key}")
                    return key, {"error": "Response is not JSON", "content": response_text[:200]}, 'error', fetch_time

        except requests.Timeout as e:
            last_error = f"Timeout: {str(e)}"
            if attempt < max_retries:
                logger.warning(f"   ⏱️ Timeout for {key}, retrying...")
                continue
            # Last attempt - raise
            raise

        except requests.HTTPError as e:
            last_error = f"HTTP {e.response.status_code}"
            # Don't retry non-transient errors (but 404 can be transient!)
            if e.response.status_code not in [404, 502, 503, 504]:
                raise
            # Retry transient errors if attempts left
            if attempt < max_retries:
                logger.warning(f"   ⚠️ HTTP {e.response.status_code} for {key}, retrying...")
                continue
            raise

        except requests.RequestException as e:
            last_error = str(e)
            if attempt < max_retries:
                logger.warning(f"   ⚠️ Request error for {key}, retrying...")
                continue
            raise

        except Exception as e:
            last_error = str(e)
            logger.warning(f"   💥 Unexpected error for {key}: {str(e)}")
            raise

    # Should not reach here, but just in case
    raise Exception(f"All retries exhausted for {key}, last error: {last_error}")


def fetch_with_failover(
    key: str,
    endpoint_template: str,
    match_id: int,
    use_source_manager: bool = True,
    skip_lambda: bool = False
) -> Tuple[str, Any, str, float, Optional[str]]:
    """
    Fetch data with multi-source failover support

    Tries primary source first, then fallback sources if primary fails.
    Records success/failure metrics for each source.

    Args:
        key: Data key (e.g., 'h2h_details', 'corner_odds')
        endpoint_template: Endpoint template (e.g., '/match/h2h-{match_id}')
        match_id: Match ID to substitute in template
        use_source_manager: Whether to use source manager (default: True)

    Returns:
        Tuple: (key, content, content_type, fetch_time, source_used)
    """
    if not use_source_manager:
        # Fallback to old behavior (single source)
        base_url = current_config.NOWGOAL_BASE_URL
        url = f"{base_url}{endpoint_template.format(match_id=match_id)}"
        result = fetch_single_url_with_retry(key, url, current_config.MAX_RETRIES_PER_SOURCE, base_url)
        return (*result, base_url)

    # Get source manager and prioritized sources
    source_manager = get_source_manager()
    prioritized_sources = source_manager.get_prioritized_sources()

    logger.debug(f"🎯 Fetching {key} for match {match_id} with {len(prioritized_sources)} sources")

    last_error = None
    last_error_type = 'unknown'

    # Try each source in priority order
    for source_idx, source_url in enumerate(prioritized_sources):
        try:
            # Format full URL
            url = f"{source_url}{endpoint_template.format(match_id=match_id)}"

            logger.info(f"📡 [{source_idx + 1}/{len(prioritized_sources)}] Trying {key} from {source_url}")

            # Attempt fetch with retries for this source
            result = fetch_single_url_with_retry(
                key,
                url,
                max_retries=current_config.MAX_RETRIES_PER_SOURCE,
                source_url=source_url,
                skip_lambda=skip_lambda
            )

            # SUCCESS! Record and return
            source_manager.record_success(source_url)
            logger.info(f"   ✅ Successfully fetched {key} from {source_url}")

            # Return with source info
            return (*result, source_url)

        except requests.Timeout:
            last_error = f"Timeout from {source_url}"
            last_error_type = 'timeout'
            source_manager.record_failure(source_url, 'timeout')
            logger.warning(f"   ⏱️ Timeout fetching {key} from {source_url}, trying next source...")

            # Add breadcrumb for debugging (no separate Sentry event)
            try:
                import sentry_sdk
                sentry_sdk.add_breadcrumb(
                    category='http',
                    message=f"Timeout: {key} from {source_url}",
                    level='warning',
                    data={'source': source_url, 'match_id': match_id, 'key': key}
                )
            except:
                pass

            continue

        except requests.HTTPError as e:
            status_code = e.response.status_code
            last_error = f"HTTP {status_code} from {source_url}"

            if status_code == 404:
                # 404 - try next source
                last_error_type = '404'
                source_manager.record_failure(source_url, '404')
                logger.warning(f"   🔍 404 for {key} at {source_url}, trying next source...")

                # Add breadcrumb (no separate Sentry event)
                try:
                    import sentry_sdk
                    sentry_sdk.add_breadcrumb(
                        category='http',
                        message=f"404: {key} at {source_url}",
                        level='warning',
                        data={'source': source_url, 'match_id': match_id, 'status_code': 404}
                    )
                except:
                    pass

                continue
            else:
                # Other HTTP errors (5xx, etc.)
                last_error_type = f'http_{status_code}'
                source_manager.record_failure(source_url, last_error_type)
                logger.warning(f"   ❌ HTTP {status_code} for {key} at {source_url}")

                # Add breadcrumb for HTTP errors
                try:
                    import sentry_sdk
                    sentry_sdk.add_breadcrumb(
                        category='http',
                        message=f"HTTP {status_code}: {key} at {source_url}",
                        level='error',
                        data={'source': source_url, 'match_id': match_id, 'status_code': status_code}
                    )
                except:
                    pass

                continue

        except Exception as e:
            last_error = f"Exception from {source_url}: {str(e)}"
            last_error_type = 'exception'
            source_manager.record_failure(source_url, 'exception')
            logger.warning(f"   💥 Exception fetching {key} from {source_url}: {str(e)}")

            # Add breadcrumb for exceptions
            try:
                import sentry_sdk
                sentry_sdk.add_breadcrumb(
                    category='http',
                    message=f"Exception: {key} from {source_url}",
                    level='error',
                    data={'source': source_url, 'match_id': match_id, 'error': str(e), 'error_type': type(e).__name__}
                )
            except:
                pass

            continue

    # All sources failed - check if this is an optional endpoint
    # Optional endpoints: data not available for all matches (expected behavior)
    OPTIONAL_ENDPOINTS = ['correct_score_odds', 'corner_odds', 'h2h_details',
                          'double_chance_odds', 'first_half_odds']

    is_optional = key in OPTIONAL_ENDPOINTS

    if is_optional:
        # Optional endpoint - use WARNING level (don't flood Sentry)
        logger.warning(f"⚠️ All {len(prioritized_sources)} sources failed for {key} (optional data)")
    else:
        # Required endpoint - use ERROR level
        logger.error(f"🚫 All {len(prioritized_sources)} sources failed for {key}")

    # Add comprehensive context via Sentry scope (only for required endpoints)
    if not is_optional:
        try:
            import sentry_sdk
            sentry_sdk.set_context("fetch_failure", {
                'key': key,
                'match_id': match_id,
                'sources_tried': prioritized_sources,
                'last_error': last_error,
                'last_error_type': last_error_type
            })
        except:
            pass

    # Return error result
    fetch_time = 0
    return key, {"error": "All sources failed", "details": last_error}, 'error', fetch_time, None


# --- REMOVED: Async HTTP Functions ---
# These async functions were never used and caused event loop conflicts with Gunicorn.
# The application uses fetch_all_urls_sync() instead.
# Removed functions:
# - async def fetch_url() [77 lines]
# - async def fetch_all_urls() [41 lines]

def _fetch_date_data_from_source(url, source_url):
    """
    Fetch date data from a single source URL.

    Tries Lambda first (IP rotation), falls back to direct HTTP.
    Returns response text on success, raises on failure.
    """
    # Lambda kullan (varsa)
    if USE_LAMBDA:
        try:
            logger.debug(f"[LAMBDA] Fetching via Lambda: {url}")
            lambda_response = lambda_client.invoke(
                FunctionName='goaloo-scraper',
                InvocationType='RequestResponse',
                Payload=json.dumps({'url': url})
            )
            result = json.loads(lambda_response['Payload'].read())

            if result.get('statusCode') == 200:
                logger.info(f"[LAMBDA] Success: {len(result['body'])} chars from {source_url}")
                return result['body']
            else:
                logger.warning(f"[LAMBDA] Non-200 from {source_url}, falling back to direct")
        except Exception as e:
            logger.warning(f"[LAMBDA] Failed for {source_url}: {type(e).__name__}, falling back to direct")

    # Direct HTTP request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'DNT': '1'
    }

    session = get_http_session(source_url)
    response = safe_get(
        session,
        url,
        headers=headers,
        timeout=(current_config.HTTP_TIMEOUT_CONNECT, current_config.HTTP_TIMEOUT_READ)
    )

    # Handle redirect
    if response.history:
        handle_url_redirect(url, response.url, source_url)

    if response.status_code != 200:
        raise requests.HTTPError(f"HTTP {response.status_code}", response=type('obj', (object,), {'status_code': response.status_code})())

    if not response.text or len(response.text) < 100:
        raise Exception(f"Empty or too short response ({len(response.text or '')} chars)")

    return response.text


def fetch_date_data_simple(api_url):
    """
    Fetch date data with multi-source failover support.

    Tries each source from SourceManager in priority order.
    Uses the endpoint path from api_url but replaces the base URL with each source.
    """
    from urllib.parse import urlparse

    # Extract the endpoint path from the original URL
    parsed = urlparse(api_url)
    endpoint_path = f"{parsed.path}{'?' + parsed.query if parsed.query else ''}"

    # Get sources from SourceManager (with circuit breaker filtering)
    source_manager = get_source_manager()
    sources = source_manager.get_prioritized_sources()

    last_error = None

    for idx, source_url in enumerate(sources):
        try:
            full_url = f"{source_url}{endpoint_path}"
            logger.info(f"📡 [DATE {idx+1}/{len(sources)}] Trying {source_url}")

            response_text = _fetch_date_data_from_source(full_url, source_url)

            # Success
            source_manager.record_success(source_url)
            logger.info(f"✅ [DATE] Fetched {len(response_text)} chars from {source_url}")
            return response_text

        except Exception as e:
            last_error = e
            source_manager.record_failure(source_url, type(e).__name__)
            logger.warning(f"❌ [DATE {idx+1}/{len(sources)}] Failed from {source_url}: {type(e).__name__}: {e}")
            continue

    # All sources failed
    from models import APIError
    raise APIError(f"All {len(sources)} sources failed for date data: {last_error}", 503)

# --- Request Header Utilities ---

def get_request_headers(base_url=None):
    """
    Get standard request headers for external API calls

    Args:
        base_url: Base URL for Referer and Origin headers.
                  If None, uses NOWGOAL_BASE_URL from config.
    """
    if base_url is None:
        base_url = current_config.NOWGOAL_BASE_URL

    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Encoding': 'gzip, deflate',  # Removed 'br' (brotli) to avoid decode errors
        'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{base_url}/',
        'Origin': base_url,
        'DNT': '1'
    }

# --- REMOVED: Async Cleanup Functions ---
# These were never properly called (missing await) and are no longer needed.
# Removed: async def cleanup_all_sessions() and async def cleanup_session()

def fetch_all_urls_sync(urls, match_id=None, use_failover=True):
    """
    Synchronous parallel URL fetching with multi-source failover support

    Args:
        urls: Dictionary of {key: (endpoint_template, match_id)} OR {key: url}
                New format: {'h2h_details': ('/match/h2h-{match_id}', 123)}
                Old format: {'h2h_details': 'https://goaloo.com/match/h2h-123'}
        match_id: Match ID (if using new format with endpoint templates)
        use_failover: Whether to use multi-source failover (default: True)

    Returns:
        List of tuples: (key, content, content_type, fetch_time, source_used)
    """
    import concurrent.futures

    # Detect format (new vs old)
    first_value = next(iter(urls.values()))
    is_new_format = isinstance(first_value, tuple)

    if use_failover and is_new_format and match_id:
        # NEW FORMAT with failover support
        logger.info(f"🚀 Fetching {len(urls)} URLs for match {match_id} with failover")

        results = []
        failed_keys = {}  # {key: endpoint_template} - Lambda'da başarısız olanlar

        # ================================================================
        # STEP 1: Batch Lambda ile tüm URL'leri tek çağrıda dene
        # ================================================================
        if USE_LAMBDA:
            # Primary source üzerinden tüm URL'leri hazırla
            source_manager = get_source_manager()
            primary_source = source_manager.get_prioritized_sources()[0]

            batch_urls = {}
            key_to_template = {}
            for key, (endpoint_template, _) in urls.items():
                full_url = f"{primary_source}{endpoint_template.format(match_id=match_id)}"
                batch_urls[key] = full_url
                key_to_template[key] = endpoint_template

            # Tek Lambda çağrısı
            batch_results = fetch_batch_via_lambda(batch_urls)

            # Sonuçları işle
            for key, lambda_result in batch_results.items():
                if isinstance(lambda_result, dict) and lambda_result.get('statusCode') == 200:
                    response_text = lambda_result['body']
                    # Parse response
                    if key == 'h2h_details':
                        results.append((key, response_text, 'html', 0, primary_source))
                    else:
                        try:
                            json_data = json.loads(response_text)
                            results.append((key, json_data, 'json', 0, primary_source))
                        except (json.JSONDecodeError, ValueError):
                            results.append((key, response_text, 'text', 0, primary_source))

                    source_manager.record_success(primary_source)
                    logger.debug(f"   ✅ [BATCH] {key} successful from Lambda")
                else:
                    # Bu key Lambda'da başarısız oldu, failover'a gönder
                    failed_keys[key] = key_to_template[key]
                    status = lambda_result.get('statusCode', 'unknown') if isinstance(lambda_result, dict) else 'missing'
                    logger.warning(f"   ⚠️ [BATCH] {key} failed in Lambda (status={status}), will try failover")

            # Batch'te hiç olmayan key'ler (Lambda tamamen başarısızsa)
            for key in urls:
                if key not in batch_results and key not in failed_keys:
                    failed_keys[key] = key_to_template.get(key, urls[key][0])
        else:
            # Lambda yok, tümünü failover'a gönder
            for key, (endpoint_template, _) in urls.items():
                failed_keys[key] = endpoint_template

        # ================================================================
        # STEP 2: Başarısız URL'leri failover ile dene (direct HTTP)
        # ================================================================
        if failed_keys:
            logger.info(f"   🔄 {len(failed_keys)} URLs need failover: {list(failed_keys.keys())}")

            executor = get_global_thread_pool()
            future_to_key = {}
            for key, endpoint_template in failed_keys.items():
                future = executor.submit(
                    fetch_with_failover,
                    key,
                    endpoint_template,
                    match_id,
                    use_failover,
                    skip_lambda=True  # Batch'te Lambda zaten denendi
                )
                future_to_key[future] = key

            completed_keys = set()
            try:
                for future in concurrent.futures.as_completed(future_to_key, timeout=30):
                    key = future_to_key[future]
                    completed_keys.add(key)
                    try:
                        result = future.result(timeout=5)
                        results.append(result)
                        logger.debug(f"   ✅ Completed {key} via failover")
                    except concurrent.futures.TimeoutError:
                        logger.warning(f"   ⏱️ Future result timeout for {key}")
                        results.append((key, {"error": "Request timeout"}, 'error', 0, None))
                    except Exception as e:
                        logger.warning(f"   💥 Exception in future for {key}: {str(e)}")
                        results.append((key, {"error": str(e)}, 'error', 0, None))
            except concurrent.futures.TimeoutError:
                all_keys = set(future_to_key.values())
                unfinished_keys = all_keys - completed_keys
                if unfinished_keys:
                    logger.warning(f"   ⏱️ Timeout: {len(unfinished_keys)} futures unfinished: {unfinished_keys}")
                    for key in unfinished_keys:
                        results.append((key, {"error": "Request timeout"}, 'error', 0, None))

        return results

    else:
        # OLD FORMAT or failover disabled - use original logic
        logger.debug(f"Fetching {len(urls)} URLs without failover (old format or disabled)")

        def fetch_single_url(key, url, max_retries=2):
            """Fetch a single URL synchronously with retry logic"""
            start_time = time.time()

            # Retryable status codes
            retryable_status_codes = {502, 503, 504}
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        # Exponential backoff
                        wait_time = 0.5 * (2 ** (attempt - 1))
                        logger.info(f"Retrying {key} (attempt {attempt + 1}/{max_retries + 1}) after {wait_time}s")
                        time.sleep(wait_time)

                    logger.debug(f"Fetching {key} from {url}")

                    # Get headers
                    headers = get_request_headers()

                    # Extract base URL from url for session pooling
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    base_url = f"{parsed.scheme}://{parsed.netloc}"

                    # Get session with connection pool for this base URL
                    session = get_http_session(base_url)

                    # Make request with timeout using session pool
                    response = safe_get(
                        session,
                        url,
                        headers=headers,
                        timeout=(15, 30)  # (connect_timeout, read_timeout)
                    )

                    # Check for retryable errors
                    if response.status_code in retryable_status_codes and attempt < max_retries:
                        logger.warning(f"Transient error {response.status_code} for {key}, will retry")
                        last_error = f"{response.status_code} {response.reason}"
                        continue

                    response.raise_for_status()

                    fetch_time = time.time() - start_time
                    logger.debug(f"Fetched {key} in {fetch_time:.2f}s")

                    # Determine content type and parse accordingly
                    if key == 'h2h_details':
                        return key, response.text, 'html', fetch_time
                    else:
                        # Try to parse as JSON
                        content_type = response.headers.get('content-type', '').lower()
                        if 'application/json' in content_type or 'text/javascript' in content_type:
                            try:
                                json_data = response.json()
                                return key, json_data, 'json', fetch_time
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse JSON for {key}")
                                return key, {"error": "Invalid JSON response"}, 'error', fetch_time
                        else:
                            # Try to parse as JSON anyway (some servers send wrong content-type)
                            try:
                                json_data = response.json()
                                return key, json_data, 'json', fetch_time
                            except:
                                logger.warning(f"Response is not JSON for {key}")
                                return key, {"error": "Response is not JSON", "content": response.text[:200]}, 'error', fetch_time

                except requests.Timeout:
                    fetch_time = time.time() - start_time
                    logger.warning(f"Timeout fetching {key}")
                    last_error = "Timeout"
                    if attempt < max_retries:
                        continue
                    return key, {"error": "Timeout on reading data from socket"}, 'error', fetch_time

                except requests.HTTPError as e:
                    fetch_time = time.time() - start_time
                    if e.response.status_code in retryable_status_codes and attempt < max_retries:
                        logger.warning(f"HTTP {e.response.status_code} for {key}, will retry")
                        last_error = str(e)
                        continue
                    else:
                        logger.warning(f"HTTP error fetching {key}: {str(e)}")
                        return key, {"error": f"HTTP {e.response.status_code} error", "details": str(e)}, 'error', fetch_time

                except requests.RequestException as e:
                    fetch_time = time.time() - start_time
                    logger.warning(f"Request error fetching {key}: {str(e)}")
                    last_error = str(e)
                    if attempt < max_retries:
                        continue
                    return key, {"error": f"Failed to fetch {url}", "details": str(e)}, 'error', fetch_time

                except Exception as e:
                    fetch_time = time.time() - start_time
                    logger.warning(f"Unexpected error fetching {key}: {str(e)}")
                    return key, {"error": f"Unexpected error: {str(e)}"}, 'error', fetch_time

            # All retries exhausted
            fetch_time = time.time() - start_time
            logger.warning(f"All retries exhausted for {key}, last error: {last_error}")
            return key, {"error": "Service temporarily unavailable", "details": last_error}, 'error', fetch_time

        # Fetch all URLs in parallel using GLOBAL ThreadPoolExecutor
        results = []
        executor = get_global_thread_pool()

        # Submit all tasks
        future_to_key = {
            executor.submit(fetch_single_url, key, url): key
            for key, url in urls.items()
        }

        # Collect results as they complete (extended timeout)
        completed_keys = set()
        try:
            for future in concurrent.futures.as_completed(future_to_key, timeout=35):
                key = future_to_key[future]
                completed_keys.add(key)
                try:
                    result = future.result(timeout=3)
                    results.append(result)
                except concurrent.futures.TimeoutError:
                    logger.warning(f"Future timeout for {key}")
                    results.append((key, {"error": "Request timeout"}, 'error', 0))
                except Exception as e:
                    logger.warning(f"Exception in future for {key}: {str(e)}")
                    results.append((key, {"error": str(e)}, 'error', 0))
        except concurrent.futures.TimeoutError:
            # as_completed timeout - handle unfinished futures gracefully
            all_keys = set(future_to_key.values())
            unfinished_keys = all_keys - completed_keys
            if unfinished_keys:
                logger.warning(f"Timeout: {len(unfinished_keys)} futures unfinished: {unfinished_keys}")
                for key in unfinished_keys:
                    results.append((key, {"error": "Request timeout"}, 'error', 0))

        return results


# REMOVED: run_async_with_new_loop() - deprecated function that raised NotImplementedError
# Use fetch_all_urls_sync() directly instead


