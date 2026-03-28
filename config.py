"""
Application configuration settings
"""
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration"""
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Security Configuration
    API_SECRET_KEY = os.getenv('API_SECRET_KEY', 'your-super-secret-api-key-change-in-production')
    ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*').split(',')

    # JWT Configuration
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'jwt-secret-key-change-in-production')
    JWT_ACCESS_TOKEN_EXPIRES = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))  # 1 hour

    # Security - Rate Limiting ENABLED
    ENABLE_CORS = os.getenv('ENABLE_CORS', 'true').lower() == 'true'
    ENABLE_RATE_LIMITING = os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true'  # Rate limiting now active
    
    # Cache Configuration
    CACHE_TYPE = os.getenv('CACHE_TYPE', 'redis')
    CACHE_REDIS_HOST = os.getenv('CACHE_REDIS_HOST', 'localhost')
    CACHE_REDIS_PORT = int(os.getenv('CACHE_REDIS_PORT', 6379))
    CACHE_REDIS_DB = int(os.getenv('CACHE_REDIS_DB', 0))
    CACHE_DEFAULT_TIMEOUT = int(os.getenv('CACHE_DEFAULT_TIMEOUT', 1800))  # 30 minutes default
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = os.getenv('LOG_FILE', 'app.log')
    
    # API Configuration
    API_VERSION = os.getenv('API_VERSION', '1.0.0')
    MAX_CONNECTIONS = int(os.getenv('MAX_CONNECTIONS', 10))  # Reduced from 20 to 10
    CONNECTION_TIMEOUT = int(os.getenv('CONNECTION_TIMEOUT', 30))

    # Thread Pool Configuration (CRITICAL: Prevents thread exhaustion)
    MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT_REQUESTS', 100))  # Global thread pool limit (increased for Lambda 1000 concurrency)
    MAX_WORKERS_PER_REQUEST = int(os.getenv('MAX_WORKERS_PER_REQUEST', 20))   # Per-request worker limit

    # ========================================================================
    # MULTI-SOURCE DATA CONFIGURATION
    # ========================================================================
    # PRIMARY source (nowgoal.com - en stabil kaynak)
    PRIMARY_DATA_SOURCE = os.getenv('PRIMARY_DATA_SOURCE', 'https://www.nowgoal.com')

    # FALLBACK sources (virgülle ayrılmış liste, öncelik sırasına göre)
    FALLBACK_DATA_SOURCES_STR = os.getenv('FALLBACK_DATA_SOURCES', 'https://live5.nowgoal26.com,https://www.goaloo.com')
    FALLBACK_DATA_SOURCES = [s.strip() for s in FALLBACK_DATA_SOURCES_STR.split(',') if s.strip()]

    # Tüm source'ları birleştir (primary + fallbacks)
    ALL_DATA_SOURCES = [PRIMARY_DATA_SOURCE] + FALLBACK_DATA_SOURCES

    # Güvenlik: İzin verilen source hostname'leri (ALL_DATA_SOURCES + LEAGUE_DATA_SOURCE'dan otomatik türetilir)
    # Yeni domain eklemek için sadece PRIMARY_DATA_SOURCE veya FALLBACK_DATA_SOURCES'ı güncelle — buraya dokunma
    # Root domain'ler de eklenir: live5.nowgoal26.com → nowgoal26.com (subdomain redirect'leri için)
    _source_hostnames = set(
        urlparse(url).hostname
        for url in ALL_DATA_SOURCES + [os.getenv('LEAGUE_DATA_SOURCE', 'https://football.nowgoal.com')]
        if urlparse(url).hostname
    )
    # Her hostname'in root domain'ini de ekle (subdomain redirect'lerine izin vermek için)
    _root_domains = set()
    for h in _source_hostnames:
        parts = h.split('.')
        if len(parts) >= 2:
            _root_domains.add('.'.join(parts[-2:]))  # nowgoal26.com, nowgoal.com, goaloo.com
    ALLOWED_SOURCE_HOSTS = _source_hostnames | _root_domains

    # BACKWARD COMPATIBILITY - eski kod için (artık PRIMARY_DATA_SOURCE kullanılıyor)
    NOWGOAL_BASE_URL = os.getenv('NOWGOAL_BASE_URL', 'https://www.nowgoal.com')

    # ========================================================================
    # SOURCE HEALTH TRACKING
    # ========================================================================
    # Son kaç request'i takip edeceğiz (sliding window)
    SOURCE_HEALTH_WINDOW = int(os.getenv('SOURCE_HEALTH_WINDOW', 100))

    # Error rate threshold (0.0-1.0) - bu değerin üzerinde fallback'e geç
    SOURCE_HEALTH_THRESHOLD = float(os.getenv('SOURCE_HEALTH_THRESHOLD', 0.3))

    # Üst üste kaç hata alınca primary/fallback swap edilsin
    CONSECUTIVE_FAIL_THRESHOLD = int(os.getenv('CONSECUTIVE_FAIL_THRESHOLD', 10))

    # Minimum swap interval (saniye) - çok sık swap olmasın
    MIN_SWAP_INTERVAL = int(os.getenv('MIN_SWAP_INTERVAL', 300))

    # ========================================================================
    # RETRY CONFIGURATION (FAST FAILOVER: No retry, immediate source switch)
    # ========================================================================
    # Her source için kaç kez retry yapılacak
    # FAST FAILOVER: 0 retry, hemen goaloo'ya geç
    MAX_RETRIES_PER_SOURCE = int(os.getenv('MAX_RETRIES_PER_SOURCE', 0))

    # Retry backoff factor (exponential backoff için çarpan)
    RETRY_BACKOFF_FACTOR = float(os.getenv('RETRY_BACKOFF_FACTOR', 0.3))

    # ========================================================================
    # HTTP TIMEOUT CONFIGURATION (FAST FAILOVER: Short timeout for quick failover)
    # ========================================================================
    # Total request timeout (saniye)
    # FAST FAILOVER: 10s max per source attempt
    HTTP_TIMEOUT_TOTAL = int(os.getenv('HTTP_TIMEOUT_TOTAL', 10))

    # Connection timeout (saniye)
    # FAST FAILOVER: 3s connection timeout
    HTTP_TIMEOUT_CONNECT = int(os.getenv('HTTP_TIMEOUT_CONNECT', 3))

    # Read timeout (saniye)
    # FAST FAILOVER: 5s read timeout (hızlı fail, hemen goaloo dene)
    HTTP_TIMEOUT_READ = int(os.getenv('HTTP_TIMEOUT_READ', 5))

    # Proxy Configuration (for servers blocked by nowgoal)
    HTTP_PROXY = os.getenv('HTTP_PROXY', None)  # Example: http://proxy.example.com:8080
    HTTPS_PROXY = os.getenv('HTTPS_PROXY', None)  # Example: http://proxy.example.com:8080

    # ========================================================================
    # LEAGUE DATA SOURCE CONFIGURATION
    # ========================================================================
    # League data uses different subdomain (football.nowgoal26.com)
    LEAGUE_DATA_SOURCE = os.getenv('LEAGUE_DATA_SOURCE', 'https://football.nowgoal.com')

    # League data endpoints
    LEAGUE_ENDPOINTS = {
        # League page (to extract sub_league_id)
        # Example: /league/745
        'league_page': '/league/{league_id}',

        # League standings and matches - TWO formats:
        # With sub-league: /jsData/matchResult/2025-2026/s745_918_en.js
        # Without sub-league: /jsData/matchResult/2025-2026/s36_en.js
        'league_data_with_sub': '/jsData/matchResult/{season}/s{league_id}_{sub_league_id}_en.js',
        'league_data_without_sub': '/jsData/matchResult/{season}/s{league_id}_en.js',

        # League odds by round
        # Example: /ajax/LeagueOddsAjax?sclassId=34&matchSeason=2025-2026&round=17
        'league_odds': '/ajax/LeagueOddsAjax?sclassId={sclass_id}&matchSeason={season}&round={round}',
    }

    # League cache TTLs (seconds) - Updated for realistic data change frequency
    LEAGUE_CACHE_TTL_STANDINGS = int(os.getenv('LEAGUE_CACHE_TTL_STANDINGS', 43200))      # 12 hours
    LEAGUE_CACHE_TTL_MATCHES = int(os.getenv('LEAGUE_CACHE_TTL_MATCHES', 172800))         # 48 hours
    LEAGUE_CACHE_TTL_FULL = int(os.getenv('LEAGUE_CACHE_TTL_FULL', 43200))                # 12 hours
    LEAGUE_CACHE_TTL_INFO = int(os.getenv('LEAGUE_CACHE_TTL_INFO', 604800))               # 7 days
    LEAGUE_CACHE_TTL_TEAM_STATS = int(os.getenv('LEAGUE_CACHE_TTL_TEAM_STATS', 43200))    # 12 hours
    LEAGUE_CACHE_TTL_PLAYER_STATS = int(os.getenv('LEAGUE_CACHE_TTL_PLAYER_STATS', 86400))# 24 hours
    LEAGUE_CACHE_TTL_HANDICAP = int(os.getenv('LEAGUE_CACHE_TTL_HANDICAP', 43200))        # 12 hours
    LEAGUE_CACHE_TTL_CURRENT_ROUND = int(os.getenv('LEAGUE_CACHE_TTL_CURRENT_ROUND', 43200))# 12 hours
    LEAGUE_CACHE_TTL_ODDS = int(os.getenv('LEAGUE_CACHE_TTL_ODDS', 300))                  # 5 min (odds change often)

    # NowGoal API Endpoints
    NOWGOAL_ENDPOINTS = {
        # Match endpoints
        'match_h2h': '/match/h2h-{match_id}',
        'match_fixtures': '/ajax/match/fixtures-{match_id}',

        # Odds endpoints
        'odds_corner': '/ajax/soccerajax?type=14&t=4&id={match_id}',
        'odds_correct_score': '/ajax/soccerajax?type=14&t=5&id={match_id}',
        'odds_double_chance': '/ajax/soccerajax?type=14&t=7&id={match_id}',
        'odds_comp': '/ajax/soccerajax?type=14&t=1&id={match_id}',
        'odds_first_half': '/ajax/soccerajax?type=14&t=1&id={match_id}&h=1&s=0&flesh={random}',

        # Date-based endpoints
        'matches_by_date': '/ajax/SoccerAjax?type=6&date={date}&order=league&timezone=3&flesh={random}',
    }

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    FLASK_ENV = 'development'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    FLASK_ENV = 'production'

    # Production-specific settings
    # Note: CACHE_TYPE is inherited from base Config which reads from env var
    # This allows deployments without Redis to set CACHE_TYPE=simple

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    CACHE_TYPE = 'null'  # Disable cache for testing

# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
