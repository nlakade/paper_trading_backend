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
        client_id = get_jwt_identity() 
        user = User.find_by_client_id(client_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        existing_portfolio = Portfolio.find_by_user_id(client_id)
        if existing_portfolio:
            return jsonify({'error': 'Portfolio already exists for this user'}), 409
        
        initial_margin = request.json.get('initial_margin', 100000.0)
        
        portfolio_id = Portfolio.create(client_id, initial_margin)
        if not portfolio_id:
            return jsonify({'error': 'Failed to create portfolio'}), 500
        
        logger.info(f"Portfolio created for user: {client_id}")
        
        return jsonify({
            'message': 'Portfolio created successfully',
            'portfolio_id': portfolio_id,
            'user_id': client_id,
            'initial_margin': initial_margin
        }), 201
        
    except Exception as e:
        logger.error(f"Portfolio creation error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@portfolio_bp.route('/<user_id>', methods=['GET'])
@jwt_required()
def get_portfolio(user_id):
    try:
        current_client_id = get_jwt_identity()
        if current_client_id != user_id:
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
            'user_id': user_id, 
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
    try:
        portfolio = Portfolio.find_by_user_id(user_id)
        if not portfolio:
            logger.error(f"Portfolio not found for user: {user_id}")
            return False
        
        available_margin = max(0, portfolio['available_margin'] - margin_change)
        utilized_margin = max(0, portfolio['utilized_margin'] + margin_change)
        total_pnl = portfolio['total_pnl'] + pnl_change
        
        Portfolio.update_margin(user_id, available_margin, utilized_margin, total_pnl)
        
        logger.info(f"Portfolio updated for user: {user_id} - Available: {available_margin}, Utilized: {utilized_margin}, PnL: {total_pnl}")
        return True
    except Exception as e:
        logger.error(f"Portfolio update error for user {user_id}: {str(e)}")
        return False
