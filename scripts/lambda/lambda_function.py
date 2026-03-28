import json
import time
import urllib3
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# HTTP client
http = urllib3.PoolManager()
urllib3.disable_warnings()

# =============================================================================
# GLOBAL STATE (Persists across warm Lambda invocations)
# =============================================================================
_cookies = {}  # {base_url: cookie_string}
_cookie_timestamps = {}  # {base_url: timestamp}
COOKIE_TTL = 300  # 5 minutes

BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
}


def get_base_url(url):
    """Extract base URL from full URL"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def get_cookies(base_url):
    """
    Get valid cookies for base_url, fetch from homepage if needed

    Warm container + fresh cookie: Return cached (0ms overhead)
    Warm container + stale cookie: Refresh (~150ms overhead)
    Cold container: Fetch new (~200ms overhead)
    """
    global _cookies, _cookie_timestamps

    now = time.time()

    # Check if we have fresh cookies
    if base_url in _cookies:
        last_fetch = _cookie_timestamps.get(base_url, 0)
        if now - last_fetch < COOKIE_TTL:
            return _cookies[base_url]

    # Need to fetch cookies from homepage
    try:
        print(f"[WARMUP] Fetching cookies from {base_url}/")

        response = http.request(
            'GET',
            f"{base_url}/",
            headers=BROWSER_HEADERS,
            timeout=10.0,
            redirect=True
        )

        # Extract Set-Cookie header
        set_cookie = response.headers.get('Set-Cookie', '')

        if set_cookie:
            # Parse cookie (get LS_ACCESS_TOKEN or full cookie string)
            # Format: "LS_ACCESS_TOKEN=xxx; path=/; ..."
            cookie_parts = set_cookie.split(';')[0]  # Get "NAME=VALUE" part
            _cookies[base_url] = cookie_parts
            _cookie_timestamps[base_url] = now
            print(f"[WARMUP] Success, cookie: {cookie_parts[:50]}...")
            return cookie_parts
        else:
            print(f"[WARMUP] No Set-Cookie header received")
            return None

    except Exception as e:
        print(f"[WARMUP] Error: {e}")
        return None


def fetch_single_url(url):
    """
    Tek bir URL fetch et (anti-bot retry dahil).
    Returns: {"statusCode": int, "body": str}
    """
    global _cookies, _cookie_timestamps

    base_url = get_base_url(url)
    cookie = get_cookies(base_url)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Referer': f'{base_url}/',
    }

    if cookie:
        headers['Cookie'] = cookie

    try:
        start = time.time()
        response = http.request(
            'GET',
            url,
            headers=headers,
            timeout=10.0,
            redirect=True
        )
        elapsed = time.time() - start

        body = response.data.decode('utf-8')

        # Check for anti-bot error codes
        if body.startswith('{"code":'):
            try:
                error_data = json.loads(body)
                error_code = error_data.get('code')
                if error_code in [1002, 1004]:
                    print(f"[ERROR] Anti-bot code {error_code} for {url}, refreshing cookies...")

                    # Clear cached cookies and retry once
                    _cookies.pop(base_url, None)
                    _cookie_timestamps.pop(base_url, None)

                    cookie = get_cookies(base_url)
                    if cookie:
                        headers['Cookie'] = cookie

                        response = http.request(
                            'GET',
                            url,
                            headers=headers,
                            timeout=10.0,
                            redirect=True
                        )
                        body = response.data.decode('utf-8')
            except json.JSONDecodeError:
                pass

        print(f"[FETCH] {url} -> {response.status} in {elapsed:.2f}s")

        return {
            'statusCode': response.status,
            'body': body
        }

    except Exception as e:
        print(f"[ERROR] {url}: {e}")
        return {
            'statusCode': 500,
            'body': f'Error: {str(e)}'
        }


def lambda_handler(event, context):
    """
    Goaloo.com'dan veri ceker - Tekli ve Batch mod destekli.
    Cookie caching ile anti-bot bypass.

    Tekli mod:  {"url": "https://..."}
    Batch mod:  {"urls": {"key1": "https://...", "key2": "https://...", ...}}

    Tekli response: {"statusCode": 200, "body": "..."}
    Batch response:  {"statusCode": 200, "results": {"key1": {"statusCode": 200, "body": "..."}, ...}}
    """
    # ==========================================================================
    # BATCH MODE: Birden fazla URL'i paralel fetch et
    # ==========================================================================
    urls = event.get('urls')
    if isinstance(urls, dict) and len(urls) > 0:
        print(f"[BATCH] Fetching {len(urls)} URLs in parallel")
        start_total = time.time()

        results = {}

        # Paralel fetch - her URL icin ayri thread
        with ThreadPoolExecutor(max_workers=min(len(urls), 10)) as executor:
            future_to_key = {
                executor.submit(fetch_single_url, url): key
                for key, url in urls.items()
            }

            for future in as_completed(future_to_key, timeout=20):
                key = future_to_key[future]
                try:
                    results[key] = future.result(timeout=5)
                except Exception as e:
                    print(f"[BATCH] Error for {key}: {e}")
                    results[key] = {
                        'statusCode': 500,
                        'body': f'Error: {str(e)}'
                    }

        elapsed_total = time.time() - start_total
        success_count = sum(1 for r in results.values() if r.get('statusCode') == 200)
        print(f"[BATCH] Done: {success_count}/{len(urls)} successful in {elapsed_total:.2f}s")

        return {
            'statusCode': 200,
            'results': results
        }

    # ==========================================================================
    # SINGLE MODE: Geriye uyumlu tekli URL fetch (eski format)
    # ==========================================================================
    url = event.get('url', '')

    if not url:
        return {
            'statusCode': 400,
            'body': 'Missing url or urls parameter'
        }

    return fetch_single_url(url)


# Local test
if __name__ == "__main__":
    # Test single mode
    print("=== Single Mode Test ===")
    test_event = {"url": "https://www.nowgoal.com/gf/data/bf_en-idn1.js?1234567890"}
    result = lambda_handler(test_event, None)
    print(f"Status: {result['statusCode']}")
    print(f"Body (first 300): {result['body'][:300]}")

    # Test batch mode
    print("\n=== Batch Mode Test ===")
    test_batch = {
        "urls": {
            "matches": "https://www.nowgoal.com/gf/data/bf_en-idn1.js?123",
            "stats": "https://www.nowgoal.com/gf/data/detail.js?123",
        }
    }
    result = lambda_handler(test_batch, None)
    print(f"Status: {result['statusCode']}")
    for key, val in result['results'].items():
        print(f"  {key}: {val['statusCode']} ({len(val['body'])} chars)")
