#!/usr/bin/env python3
"""
REST API layer for the Handelsregister scraper.
Provides endpoints to search companies via HTTP requests.
"""

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import argparse
import sys
import os
import jwt
from functools import wraps
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from handelsregister import HandelsRegister, schlagwortOptionen, bundeslaender, get_bundesland_code

app = Flask(__name__)

# Configuration
class Config:
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'default-secret-key-change-in-production')
    RATE_LIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', '100 per hour')
    REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', '30'))  # seconds

app.config.from_object(Config)

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[Config.RATE_LIMIT_DEFAULT],
    storage_uri="memory://"
)


def require_jwt(f):
    """Decorator to require JWT authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
        # Check for token in Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            try:
                # Expected format: "Bearer <token>"
                token = auth_header.split(' ')[1] if auth_header.startswith('Bearer ') else auth_header
            except IndexError:
                return jsonify({'error': 'Invalid Authorization header format'}), 401
        
        if not token:
            return jsonify({'error': 'Missing authentication token'}), 401
        
        try:
            # Verify token (no expiration check for service-to-service)
            jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
        except jwt.InvalidTokenError as e:
            return jsonify({'error': f'Invalid token: {str(e)}'}), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit exceeded errors."""
    return jsonify({
        'error': 'Rate limit exceeded',
        'message': str(e.description)
    }), 429


@app.route('/api/search', methods=['GET'])
@require_jwt
@limiter.limit(Config.RATE_LIMIT_DEFAULT)
def search_companies():
    """
    Search for companies by keywords.
    
    Requires JWT authentication via Authorization header.
    
    Query Parameters:
    - keywords (required): Search keywords
    - mode (optional): Search mode - all|min|exact (default: all)
    - bundesland (optional): Filter by German state(s). Comma-separated state codes (e.g., "BW,BY")
    - force (optional): Force fresh pull, skip cache (default: false)
    - debug (optional): Enable debug mode (default: false)
    
    Returns:
    JSON array of company objects
    """
    try:
        # Get query parameters
        keywords = request.args.get('keywords')
        if not keywords:
            return jsonify({
                'error': 'Missing required parameter: keywords'
            }), 400
        
        keyword_mode = request.args.get('mode', 'all')
        if keyword_mode not in schlagwortOptionen:
            return jsonify({
                'error': f'Invalid mode parameter. Must be one of: {", ".join(schlagwortOptionen.keys())}'
            }), 400
        
        force = request.args.get('force', 'false').lower() == 'true'
        debug = request.args.get('debug', 'false').lower() == 'true'
        
        # Parse bundesland parameter
        bundesland_param = request.args.get('bundesland')
        bundesland_list = None
        if bundesland_param:
            bundesland_list = [code.strip().upper() for code in bundesland_param.split(',')]
            # Validate bundesland codes
            invalid_codes = [code for code in bundesland_list if code not in bundeslaender]
            if invalid_codes:
                return jsonify({
                    'error': f'Invalid bundesland code(s): {", ".join(invalid_codes)}. Valid codes: {", ".join(bundeslaender.keys())}'
                }), 400
        
        # Create args object for HandelsRegister
        args = argparse.Namespace(
            schlagwoerter=keywords,
            schlagwortOptionen=keyword_mode,
            bundesland=bundesland_list,
            force=force,
            debug=debug,
            json=True
        )
        
        # Enable debugging if requested
        if debug:
            import logging
            logger = logging.getLogger("mechanize")
            logger.addHandler(logging.StreamHandler(sys.stdout))
            logger.setLevel(logging.DEBUG)
        
        # Perform search with timeout using ThreadPoolExecutor
        def perform_search():
            h = HandelsRegister(args)
            h.open_startpage()
            return h.search_company()
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(perform_search)
            try:
                companies = future.result(timeout=Config.REQUEST_TIMEOUT)
            except FuturesTimeoutError:
                raise TimeoutError(f'Request exceeded timeout of {Config.REQUEST_TIMEOUT} seconds')
        
        if companies is None:
            return jsonify([]), 200
        
        return jsonify(companies), 200
        
    except TimeoutError as e:
        return jsonify({
            'error': str(e)
        }), 504
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@app.route('/api/token', methods=['POST'])
def generate_token():
    """
    Generate a JWT token for service-to-service authentication.
    
    Request body (JSON):
    - service_name (required): Name of the service requesting the token
    
    Returns:
    JSON object with token
    """
    data = request.get_json()
    if not data or 'service_name' not in data:
        return jsonify({'error': 'Missing service_name in request body'}), 400
    
    service_name = data['service_name']
    
    # Create token payload (no expiration for service-to-service)
    payload = {
        'service': service_name,
        'iat': datetime.utcnow().timestamp()
    }
    
    token = jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'service': service_name
    }), 200


@app.route('/api/bundesland', methods=['GET'])
def get_bundesland():
    """
    Get bundesland code from district name (German or English).
    
    Query Parameters:
    - name (required): District name in German or English
    
    Returns:
    JSON object with bundesland code and full name
    """
    name = request.args.get('name')
    if not name:
        return jsonify({
            'error': 'Missing required parameter: name'
        }), 400
    
    code = get_bundesland_code(name)
    
    if not code:
        return jsonify({
            'error': f'Unknown district name: {name}',
            'hint': 'Try German names (e.g., "Berlin", "Bayern") or English names (e.g., "Bavaria", "North Rhine-Westphalia")'
        }), 404
    
    return jsonify({
        'code': code,
        'name_de': bundeslaender[code],
        'input': name,
        'form_field': f'bundesland{code}'
    }), 200


@app.route('/api/bundesland/list', methods=['GET'])
def list_bundeslaender():
    """
    List all available bundesländer with their codes.
    
    Returns:
    JSON array of bundesland objects
    """
    result = []
    for code, name_de in bundeslaender.items():
        result.append({
            'code': code,
            'name_de': name_de,
            'form_field': f'bundesland{code}'
        })
    
    return jsonify(result), 200


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint (no authentication required)."""
    return jsonify({
        'status': 'ok',
        'service': 'handelsregister-api',
        'config': {
            'rate_limit': Config.RATE_LIMIT_DEFAULT,
            'request_timeout': Config.REQUEST_TIMEOUT
        }
    }), 200


@app.route('/api/docs', methods=['GET'])
def api_docs():
    """API documentation endpoint (no authentication required)."""
    return jsonify({
        'authentication': {
            'type': 'JWT',
            'header': 'Authorization: Bearer <token>',
            'description': 'Service-to-service authentication without expiration'
        },
        'rate_limiting': {
            'default': Config.RATE_LIMIT_DEFAULT,
            'description': 'Rate limit applied per IP address'
        },
        'request_timeout': {
            'value': f'{Config.REQUEST_TIMEOUT} seconds',
            'description': 'Maximum time allowed for request processing'
        },
        'endpoints': {
            '/api/token': {
                'method': 'POST',
                'authentication': False,
                'description': 'Generate JWT token for service authentication',
                'body': {
                    'service_name': {
                        'type': 'string',
                        'required': True,
                        'description': 'Name of the service requesting the token'
                    }
                },
                'example': 'curl -X POST http://localhost:5000/api/token -H "Content-Type: application/json" -d \'{"service_name": "my-service"}\''
            },
            '/api/search': {
                'method': 'GET',
                'authentication': True,
                'rate_limited': True,
                'description': 'Search for companies by keywords',
                'headers': {
                    'Authorization': 'Bearer <token> (required)'
                },
                'parameters': {
                    'keywords': {
                        'type': 'string',
                        'required': True,
                        'description': 'Search keywords'
                    },
                    'mode': {
                        'type': 'string',
                        'required': False,
                        'default': 'all',
                        'options': ['all', 'min', 'exact'],
                        'description': 'Search mode: all=contain all keywords; min=contain at least one keyword; exact=exact company name'
                    },
                    'bundesland': {
                        'type': 'string',
                        'required': False,
                        'description': 'Filter by German state(s). Comma-separated state codes',
                        'options': list(bundeslaender.keys()),
                        'example': 'BW,BY or just BW'
                    },
                    'force': {
                        'type': 'boolean',
                        'required': False,
                        'default': False,
                        'description': 'Force fresh pull and skip cache'
                    },
                    'debug': {
                        'type': 'boolean',
                        'required': False,
                        'default': False,
                        'description': 'Enable debug mode'
                    }
                },
                'example': 'curl -H "Authorization: Bearer <token>" "http://localhost:5000/api/search?keywords=Gasag%20AG&mode=all&bundesland=BE,HH"'
            },
            '/api/bundesland': {
                'method': 'GET',
                'authentication': False,
                'description': 'Get bundesland code from district name (German or English)',
                'parameters': {
                    'name': {
                        'type': 'string',
                        'required': True,
                        'description': 'District name in German or English',
                        'examples': ['Berlin', 'Bayern', 'Bavaria', 'North Rhine-Westphalia', 'Nordrhein-Westfalen']
                    }
                },
                'example': 'curl "http://localhost:5000/api/bundesland?name=Berlin"'
            },
            '/api/bundesland/list': {
                'method': 'GET',
                'authentication': False,
                'description': 'List all available bundesländer with their codes',
                'example': 'curl "http://localhost:5000/api/bundesland/list"'
            },
            '/api/health': {
                'method': 'GET',
                'authentication': False,
                'description': 'Health check endpoint with configuration info'
            },
            '/api/docs': {
                'method': 'GET',
                'authentication': False,
                'description': 'API documentation'
            }
        },
        'environment_variables': {
            'JWT_SECRET_KEY': 'Secret key for JWT signing (default: default-secret-key-change-in-production)',
            'RATE_LIMIT_DEFAULT': f'Rate limit string (default: {Config.RATE_LIMIT_DEFAULT})',
            'REQUEST_TIMEOUT': f'Request timeout in seconds (default: {Config.REQUEST_TIMEOUT})'
        }
    }), 200


def parse_args():
    """Parse command-line arguments for the API server."""
    parser = argparse.ArgumentParser(description='Handelsregister REST API Server')
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        default=5000,
        help='Port to run the API server on (default: 5000)'
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host to bind the API server to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Run Flask in debug mode'
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    app.run(host=args.host, port=args.port, debug=args.debug)
