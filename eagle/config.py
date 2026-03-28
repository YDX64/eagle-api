"""
Eagle Configuration
External API endpoints and weights for prediction combination
"""
import os


class EagleConfig:
    # External API URLs (same server, different ports)
    FALCON_API_URL = os.getenv("EAGLE_FALCON_URL", "http://127.0.0.1:8092")
    PREDATOR_API_URL = os.getenv("EAGLE_PREDATOR_URL", "http://127.0.0.1:8090")
    PREDATOR_V2_API_URL = os.getenv("EAGLE_PREDATOR_V2_URL", "")  # Optional

    # API Keys
    FALCON_API_KEY = os.getenv("EAGLE_FALCON_KEY", "")
    PREDATOR_API_KEY = os.getenv("EAGLE_PREDATOR_KEY", "")
    PREDATOR_V2_API_KEY = os.getenv("EAGLE_PREDATOR_V2_KEY", "")

    # Timeouts (seconds)
    FALCON_TIMEOUT = int(os.getenv("EAGLE_FALCON_TIMEOUT", "45"))
    PREDATOR_TIMEOUT = int(os.getenv("EAGLE_PREDATOR_TIMEOUT", "30"))
    DEFAULT_TIMEOUT = int(os.getenv("EAGLE_DEFAULT_TIMEOUT", "30"))

    # Falcon rate limiting
    FALCON_MAX_CONCURRENT = int(os.getenv("EAGLE_FALCON_CONCURRENT", "2"))
    FALCON_DELAY = float(os.getenv("EAGLE_FALCON_DELAY", "0.5"))

    # Source weights for ensemble (must sum to 1.0 per active source set)
    # These are base weights - dynamically re-normalized when sources are missing
    SOURCE_WEIGHTS = {
        "falcon": 0.30,      # AI-powered, good on MS/OU
        "predator": 0.25,    # Statistical analysis, good on picks
        "predator_v2": 0.20, # Second-gen predator (if available)
        "bee": 0.25,         # BumbleBee analysis (local, always available)
    }

    # Market-specific weight overrides
    # Some sources are better at specific markets
    MARKET_WEIGHTS = {
        "ms": {"falcon": 0.30, "predator": 0.25, "predator_v2": 0.20, "bee": 0.25},
        "over25": {"falcon": 0.35, "predator": 0.20, "predator_v2": 0.20, "bee": 0.25},
        "over35": {"falcon": 0.35, "predator": 0.20, "predator_v2": 0.20, "bee": 0.25},
        "btts": {"falcon": 0.25, "predator": 0.25, "predator_v2": 0.20, "bee": 0.30},
        "ht_result": {"falcon": 0.30, "predator": 0.20, "predator_v2": 0.20, "bee": 0.30},
        "ht_over05": {"falcon": 0.30, "predator": 0.20, "predator_v2": 0.20, "bee": 0.30},
        "corner": {"falcon": 0.50, "predator": 0.00, "predator_v2": 0.00, "bee": 0.50},
    }

    # Fuzzy match threshold for team name matching
    MATCH_THRESHOLD = float(os.getenv("EAGLE_MATCH_THRESHOLD", "0.80"))

    # Cache TTLs
    CACHE_TTL_MATCHES = int(os.getenv("EAGLE_CACHE_MATCHES", "300"))     # 5 min
    CACHE_TTL_ANALYSIS = int(os.getenv("EAGLE_CACHE_ANALYSIS", "600"))   # 10 min
    CACHE_TTL_EAGLE = int(os.getenv("EAGLE_CACHE_EAGLE", "300"))         # 5 min
