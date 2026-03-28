"""
Global rate limiter instance - circular import önlemek için ayrı modül.
app.py'de init_app(app) ile başlatılır.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# storage_uri app.py'de Redis şifresiyle override edilir
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["3000 per hour", "200 per minute"],
    storage_uri="memory://",
)
