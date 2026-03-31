"""
Security utilities and authentication decorators
"""
import hmac
import os
import uuid
import jwt
import time
import random
from collections import defaultdict, deque
from functools import wraps
from flask import request, jsonify, current_app, g
import logging

logger = logging.getLogger(__name__)

# --- Authentication Decorators ---

def require_auth(f):
    """JWT Token authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
        # Bearer Token kontrolü
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                token = auth_header.split(" ")[1]  # "Bearer TOKEN"
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        # API Key kontrolü (alternatif)
        if not token:
            token = request.headers.get('X-API-Key')
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            # JWT doğrulama
            payload = jwt.decode(
                token, 
                current_app.config['JWT_SECRET_KEY'], 
                algorithms=['HS256']
            )
            current_user = payload.get('user_id')
            g.current_user = current_user
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated_function


def require_api_key(f):
    """API Key authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 401
        
        # API key kontrolü (timing-safe comparison)
        expected_key = current_app.config.get('API_SECRET_KEY', '')
        if not hmac.compare_digest(api_key, expected_key):
            return jsonify({'error': 'Invalid API key'}), 403
        
        g.api_authenticated = True
        return f(*args, **kwargs)

    return decorated_function


def require_role(required_role):
    """Rol tabanlı yetkilendirme decorator'ı"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # API key ile giriş yaptıysa admin sayılır
            if getattr(g, 'api_authenticated', False):
                return f(*args, **kwargs)
            # JWT ile giriş yaptıysa role kontrol et
            user_role = getattr(g, 'user_role', 'user')
            if user_role != required_role and user_role != 'admin':
                return jsonify({'error': f'{required_role} privileges required', 'success': False}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

require_admin = require_role('admin')


# --- Rate Limiting Classes ---

class AdvancedRateLimit:
    """Advanced rate limiting with IP blocking"""
    
    def __init__(self):
        self.requests = defaultdict(deque)
        self.blocked_ips = {}
    
    def is_allowed(self, ip, limit=60, window=3600):  # 60 req/hour default
        now = time.time()
        
        # Blocked IP kontrolü
        if ip in self.blocked_ips:
            if now - self.blocked_ips[ip] < 3600:  # 1 saat block
                return False
            else:
                del self.blocked_ips[ip]
        
        # Request geçmişini temizle
        while self.requests[ip] and now - self.requests[ip][0] > window:
            self.requests[ip].popleft()
        
        # Limit kontrolü
        if len(self.requests[ip]) >= limit:
            self.blocked_ips[ip] = now  # IP'yi blokla
            logger.warning(f"IP {ip} blocked due to rate limit exceeded")
            return False
        
        self.requests[ip].append(now)
        return True


# --- Request Quality Manager ---

class RequestQualityManager:
    """Professional request headers and quality management"""
    
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0'
        ]
        
        self.referers = [
            'https://www.google.com/',
            'https://www.bing.com/',
            'https://duckduckgo.com/',
            'https://yandex.com/',
            'https://www.yahoo.com/'
        ]
    
    def get_quality_headers(self):
        """Kaliteli ve gerçekçi HTTP headers üret"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
            'Referer': random.choice(self.referers)
        }
    
    def add_random_delay(self, min_delay=1, max_delay=3):
        """İstekler arası rastgele gecikme"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
        return delay


# --- Security Utilities ---

def get_real_ip():
    """Client IP'sini al - sadece 127.0.0.1 (Nginx) proxy'sine güven."""
    remote = request.remote_addr
    # Sadece localhost'tan gelen proxy header'larına güven (Nginx/trusted proxy)
    if remote in ('127.0.0.1', '::1'):
        forwarded = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        if forwarded:
            return forwarded
        real_ip = request.headers.get('X-Real-IP', '').strip()
        if real_ip:
            return real_ip
    return remote


# --- Rate Limit Whitelist ---

WHITELIST_IPS = [
    '127.0.0.1',
    '::1',
]

WHITELIST_DOMAINS = [
    'golsinyali.com',
    'www.golsinyali.com',
    'localhost',
    '127.0.0.1'
]


def is_whitelisted():
    """Check if request is from whitelisted source"""
    # 1. IP whitelist check (for trusted servers only)
    client_ip = get_real_ip()
    if client_ip in WHITELIST_IPS:
        return True

    # 2. API Key check (recommended for production) - timing-safe comparison
    api_key = request.headers.get('X-API-Key')
    expected_key = os.getenv('API_SECRET_KEY', '')
    if api_key and expected_key and hmac.compare_digest(api_key, expected_key):
        return True

    # Note: Origin/Referer checks removed because requests come from users' browsers
    # CORS already handles domain restrictions
    return False


def get_rate_limit_key():
    """
    Custom key function for rate limiting.
    Always returns the client's real IP address.
    Whitelisted sources are exempt via request_filter on the Limiter (see app.py).
    """
    ip = get_real_ip()
    # flask-limiter logs logger.error() when key is None/empty, which floods Sentry.
    return ip or '0.0.0.0'


def generate_api_token(user_id, expires_in=3600):
    """Generate JWT token for user"""
    payload = {
        'user_id': user_id,
        'jti': str(uuid.uuid4()),
        'exp': time.time() + expires_in,
        'iat': time.time()
    }
    
    token = jwt.encode(
        payload, 
        current_app.config['JWT_SECRET_KEY'], 
        algorithm='HS256'
    )
    
    return token





# --- Security Middleware ---

class SecurityMiddleware:
    """Security middleware for request validation"""
    
    def __init__(self, app=None):
        self.app = app
        self.rate_limiter = AdvancedRateLimit()
        self.quality_manager = RequestQualityManager()
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize middleware with Flask app"""
        app.before_request(self.before_request)
        app.after_request(self.after_request)
    
    def before_request(self):
        """Execute before each request"""
        client_ip = get_real_ip()
        
        # --- API Key Authentication (Global) ---
        # Skip API key check for health and accuracy GET endpoints
        _exempt_paths = [
            '/health', '/api/v1/health', '/api/v1/health/detailed', '/',
            '/api/v1/auth/token',  # Token almak için key gerekmez (giriş endpoint'i)
        ]
        _exempt_prefixes = [
            '/api/v1/accuracy/',  # Accuracy GET endpoints (POST /calculate has its own auth)
            '/api/v1/reports',    # ML Monitor compat endpoints
            '/api/v1/report/',    # ML Monitor compat: /report/{date}
            '/api/v1/latest',     # ML Monitor compat: latest report
        ]
        _is_exempt = (
            request.path in _exempt_paths
            or any(request.path.startswith(p) for p in _exempt_prefixes)
        )
        if not _is_exempt:
            api_key = request.headers.get('X-API-Key')
            expected_key = current_app.config.get('API_SECRET_KEY', '')
            
            # If API_SECRET_KEY is configured and not empty, require validation
            if expected_key and expected_key not in ['', 'your-super-secret-api-key-change-in-production']:
                if not api_key:
                    return jsonify({'error': 'API key is required', 'success': False}), 401
                if not hmac.compare_digest(api_key, expected_key):
                    logger.warning(f"Invalid API key attempt from {client_ip}")
                    return jsonify({'error': 'Invalid API key', 'success': False}), 403
        
        # Rate limiting kontrolü - DISABLED
        # if not self.rate_limiter.is_allowed(client_ip):
        #     return jsonify({'error': 'Rate limit exceeded'}), 429
        
        # Security headers validation
        self._validate_security_headers()
        
        # Log security info
        g.start_time = time.time()
        g.client_ip = client_ip
    
    def after_request(self, response):
        """Execute after each request"""
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'"
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), camera=(), microphone=()'

        # Server header'ı gizle
        response.headers.pop('Server', None)

        # Add API version header
        response.headers['X-API-Version'] = current_app.config.get('API_VERSION', '1.0.0')

        return response
    
    def _validate_security_headers(self):
        """Validate important security headers"""
        suspicious_headers = [
            'X-Forwarded-Host',
            'X-Original-URL',
            'X-Rewrite-URL'
        ]
        
        for header in suspicious_headers:
            if request.headers.get(header):
                logger.warning(f"Suspicious header detected: {header} from {get_real_ip()}")


# --- Global instances ---
rate_limiter = AdvancedRateLimit()
quality_manager = RequestQualityManager()
security_middleware = SecurityMiddleware()
