"""
Güvenlik audit logging - admin işlemlerini ve auth denemelerini loglar.
"""
import json
import logging
from datetime import datetime

from flask import request

logger = logging.getLogger('audit')

# Audit log handler - varsa app.log'a ek olarak audit.log'a yazar
_audit_handler = logging.FileHandler('logs/audit.log')
_audit_handler.setFormatter(logging.Formatter('%(message)s'))
if not logger.handlers:
    logger.addHandler(_audit_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def _get_client_ip():
    """Client IP'sini al (proxy header'larına dikkat et)."""
    try:
        from security import get_real_ip
        return get_real_ip()
    except Exception:
        return request.remote_addr or 'unknown'


def log_admin_action(action: str, endpoint: str, details: dict = None):
    """Admin işlemlerini logla."""
    try:
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'type': 'ADMIN_ACTION',
            'action': action,
            'endpoint': endpoint,
            'ip': _get_client_ip(),
            'api_key_prefix': (
                request.headers.get('X-API-Key', '')[:8] + '...'
                if request.headers.get('X-API-Key') else 'none'
            ),
            'user_agent': request.headers.get('User-Agent', 'unknown')[:100],
            'details': details,
        }
        logger.info(json.dumps(entry))
    except Exception:
        pass  # Log hatası API'yi durdurmamalı


def log_auth_attempt(success: bool, reason: str = None):
    """Auth denemelerini logla (başarılı ve başarısız)."""
    try:
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'type': 'AUTH_ATTEMPT',
            'success': success,
            'ip': _get_client_ip(),
            'endpoint': request.path,
            'reason': reason,
        }
        logger.info(json.dumps(entry))
    except Exception:
        pass
