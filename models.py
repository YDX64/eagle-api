"""
Data models, validation schemas, and custom exceptions
"""
from marshmallow import Schema, fields

# --- Custom Exceptions ---

class APIError(Exception):
    """Custom API Exception"""
    def __init__(self, message, status_code=400, payload=None):
        super().__init__(message)  # Pass message to parent for str() support
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def __str__(self):
        """Return error message when converting to string"""
        return self.message

# --- Validation Schemas ---

class MatchRequestSchema(Schema):
    """Schema for match request validation"""
    match_id = fields.Integer(
        required=True, 
        validate=lambda x: x > 0, 
        error_messages={'invalid': 'Match ID must be a positive integer'}
    )

class DateRequestSchema(Schema):
    """Schema for date-based requests"""
    date = fields.Date(
        required=True,
        error_messages={'invalid': 'Date must be in YYYY-MM-DD format'}
    )

class TokenRequestSchema(Schema):
    """Schema for token generation requests"""
    api_key = fields.String(
        required=True,
        validate=lambda x: len(x) > 0,
        error_messages={'invalid': 'API key cannot be empty'}
    )

# --- Data Models ---



# --- Validation Helper Functions ---

def validate_match_id(match_id):
    """Validate match ID parameter"""
    if not isinstance(match_id, int) or match_id <= 0:
        raise APIError("Invalid match ID. Must be a positive integer.", 400)
    return match_id

def validate_date_string(date_str):
    """Validate date string format"""
    from datetime import datetime
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj
    except ValueError:
        raise APIError("Invalid date format. Use YYYY-MM-DD", 400)

# --- Response Builders ---

def build_success_response(data, cached=False, extra_fields=None):
    """Build successful API response"""
    from datetime import datetime
    
    response = {
        'data': data,
        'timestamp': datetime.utcnow().isoformat(),
        'success': True
    }
    
    if cached:
        response['cached'] = True
    
    if extra_fields:
        response.update(extra_fields)
    
    return response

def build_error_response(message, status_code=400, details=None):
    """Build error API response"""
    from datetime import datetime
    
    response = {
        'error': message,
        'timestamp': datetime.utcnow().isoformat(),
        'success': False
    }
    
    if details:
        response['details'] = details
    
    return response

# --- Schema Instances ---
match_request_schema = MatchRequestSchema()
date_request_schema = DateRequestSchema()
token_request_schema = TokenRequestSchema()
