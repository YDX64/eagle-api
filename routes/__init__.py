"""
Routes package - Centralized blueprint management
"""
from flask import Blueprint
import os

# Import all blueprints
from routes.health import health_bp
from routes.auth import auth_bp
from routes.matches import matches_bp
from routes.leagues import leagues_bp
# teams_bp removed - endpoints deprecated
from routes.live import live_bp
from routes.league_data import league_data_bp
from routes.eagle import eagle_bp

# Create main API blueprint
api_bp = Blueprint('api', __name__)

# Register all sub-blueprints with URL prefixes
api_bp.register_blueprint(health_bp, url_prefix='')
api_bp.register_blueprint(auth_bp, url_prefix='')
api_bp.register_blueprint(matches_bp, url_prefix='')
api_bp.register_blueprint(leagues_bp, url_prefix='')
# teams_bp removed - endpoints deprecated
api_bp.register_blueprint(live_bp, url_prefix='')
api_bp.register_blueprint(league_data_bp, url_prefix='')
api_bp.register_blueprint(eagle_bp, url_prefix='')

# Register test error endpoints only in development
# DISABLED: test_error.py file is missing
# if os.getenv('FLASK_ENV') == 'development' or os.getenv('ENABLE_TEST_ENDPOINTS', 'false').lower() == 'true':
#     from routes.test_error import test_error_bp
#     api_bp.register_blueprint(test_error_bp, url_prefix='')

# Export the main blueprint
__all__ = ['api_bp']
