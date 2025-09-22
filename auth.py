from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from models import User
from config import Config
import logging
import re

auth_bp = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    pattern = r'^[6-9]\d{9}$'
    return re.match(pattern, phone) is not None

@auth_bp.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        
        # Generate client_id if not provided
        data['client_id'] = data.get('client_id', data['email'])
        
        required_fields = ['name', 'email', 'phone', 'password']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'{field} is required'}), 400
        
        if not validate_email(data['email']):
            return jsonify({'error': 'Invalid email format'}), 400
        
        if not validate_phone(data['phone']):
            return jsonify({'error': 'Invalid phone number format'}), 400
        
        if User.find_by_client_id(data['client_id']):
            return jsonify({'error': 'Client ID already exists'}), 409
        
        if User.find_by_email(data['email']):
            return jsonify({'error': 'Email already exists'}), 409
        
        hashed_password = generate_password_hash(data['password'])
        result = User.create(data['client_id'], data['name'], data['email'], data['phone'], hashed_password)
        user_id = str(result.inserted_id)
        
        logger.info(f"New user registered: {data['client_id']}")
        
        return jsonify({
            'message': 'User registered successfully',
            'user_id': user_id
        }), 201
        
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        
        if 'client_id' not in data or not data['client_id']:
            return jsonify({'error': 'Client ID is required'}), 400
        
        if 'password' not in data or not data['password']:
            return jsonify({'error': 'Password is required'}), 400
        
        user = User.find_by_client_id(data['client_id'])
        if not user or not check_password_hash(user['password'], data['password']):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user.get('is_active', True):
            return jsonify({'error': 'Account is deactivated'}), 401
        
        access_token = create_access_token(identity=data['client_id'])
        
        logger.info(f"User logged in: {data['client_id']}")
        
        return jsonify({
            'access_token': access_token,
            'user_id': str(user['_id']),
            'client_id': user['client_id'],
            'name': user['name']
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500