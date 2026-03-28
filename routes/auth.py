"""
Authentication endpoints
"""
import hmac
import os
from flask import Blueprint, request, jsonify

from models import build_success_response
from security import generate_api_token
from rate_limiter import limiter
from audit import log_auth_attempt

# Create auth blueprint
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/auth/token', methods=['POST'])
@limiter.limit("10 per minute")
@limiter.limit("50 per hour")
def generate_token():
    """Generate JWT token for authentication"""
    data = request.get_json() or {}
    api_key = data.get('api_key') or request.headers.get('X-API-Key')

    if not api_key:
        log_auth_attempt(False, 'missing_api_key')
        return {'error': 'API key is required'}, 400

    # Validate API key (timing-safe comparison)
    expected_key = os.getenv('API_SECRET_KEY', 'default-key')
    if not hmac.compare_digest(api_key, expected_key):
        log_auth_attempt(False, 'invalid_api_key')
        return {'error': 'Invalid API key'}, 403

    log_auth_attempt(True)

    # Generate token for the API key holder
    user_id = f"api_user_{hash(api_key) % 10000}"
    token = generate_api_token(user_id, 3600)

    response = jsonify({
        'access_token': token,
        'token_type': 'Bearer',
        'expires_in': 3600
    })
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    return response
