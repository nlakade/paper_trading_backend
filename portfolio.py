from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Portfolio, User
import logging
from datetime import datetime

portfolio_bp = Blueprint('portfolio', __name__)
logger = logging.getLogger(__name__)

@portfolio_bp.route('/create', methods=['POST'])
@jwt_required()
def create_portfolio():
    try:
        user_id = get_jwt_identity()
        user = User.find_by_client_id(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        existing_portfolio = Portfolio.find_by_user_id(user_id)
        if existing_portfolio:
            return jsonify({'error': 'Portfolio already exists for this user'}), 409
        
        initial_margin = request.json.get('initial_margin', 100000.0)
        result = Portfolio.create(user_id, initial_margin)
        portfolio_id = str(result.inserted_id)
        
        logger.info(f"Portfolio created for user: {user_id}")
        
        return jsonify({
            'message': 'Portfolio created successfully',
            'portfolio_id': portfolio_id
        }), 201
        
    except Exception as e:
        logger.error(f"Portfolio creation error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@portfolio_bp.route('/<user_id>', methods=['GET'])
@jwt_required()
def get_portfolio(user_id):
    try:
        current_user_id = get_jwt_identity()
        if current_user_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        user = User.find_by_client_id(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        portfolio = Portfolio.find_by_user_id(user_id)
        if not portfolio:
            return jsonify({'error': 'Portfolio not found'}), 404
        
        total_margin = portfolio['available_margin'] + portfolio['utilized_margin']
        margin_utilization_percent = (portfolio['utilized_margin'] / total_margin * 100) if total_margin > 0 else 0
        
        return jsonify({
            'user_id': str(user['_id']),
            'client_id': user['client_id'],
            'available_margin': portfolio['available_margin'],
            'utilized_margin': portfolio['utilized_margin'],
            'total_pnl': portfolio['total_pnl'],
            'margin_utilization_percent': round(margin_utilization_percent, 2),
            'last_updated': portfolio.get('last_updated', datetime.utcnow()).isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Portfolio fetch error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def update_portfolio_margin(user_id, margin_change, pnl_change=0):
    """Update portfolio margins and PnL"""
    try:
        portfolio = Portfolio.find_by_user_id(user_id)
        if portfolio:
            available_margin = portfolio['available_margin'] - margin_change
            utilized_margin = portfolio['utilized_margin'] + margin_change
            total_pnl = portfolio['total_pnl'] + pnl_change
            Portfolio.update_margin(user_id, available_margin, utilized_margin, total_pnl)
            
            logger.info(f"Portfolio updated for user: {user_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Portfolio update error: {str(e)}")
        return False