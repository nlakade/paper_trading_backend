from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Trade, User, Portfolio
from market import get_live_price
from portfolio import update_portfolio_margin
import logging
from datetime import datetime
import json
import threading
import time
from notifications import notify_user as send_notification_helper  
from socket_handler import notify_user  
from bson import ObjectId

trades_bp = Blueprint('trades', __name__)
logger = logging.getLogger(__name__)

active_trades = {}
monitor_thread = None
stop_monitoring = False

@trades_bp.route('/create', methods=['POST'])
@jwt_required()
def create_trade():
    try:
        client_id = get_jwt_identity()  
        user = User.find_by_client_id(client_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        portfolio = Portfolio.find_by_user_id(client_id) 
        if not portfolio:
            return jsonify({'error': 'Portfolio not found. Please create a portfolio first.'}), 404

        data = request.get_json()
        
        required_fields = ['symbol', 'trade_type', 'quantity']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'{field} is required'}), 400
        
        if data['trade_type'] not in ['BUY', 'SELL']:
            return jsonify({'error': 'Trade type must be BUY or SELL'}), 400
        
        try:
            quantity = int(data['quantity'])
            if quantity <= 0:
                return jsonify({'error': 'Quantity must be positive'}), 400
        except ValueError:
            return jsonify({'error': 'Quantity must be a valid number'}), 400
        
        price_response, status_code = get_live_price(data['symbol'])
        if status_code != 200:
            return jsonify({'error': 'Failed to fetch market price for the symbol'}), 400
        
        price_data = json.loads(price_response.get_data(as_text=True))
        current_price = price_data['price']
        
        margin_required = current_price * quantity * 0.2  
        
        if portfolio['available_margin'] < margin_required:
            return jsonify({
                'error': 'Insufficient margin',
                'available_margin': portfolio['available_margin'],
                'required_margin': margin_required
            }), 400
        
        trade_id = Trade.create(
            client_id, 
            data['symbol'].upper(),
            data['trade_type'],
            quantity,
            current_price,
            current_price,
            margin_required,
            data.get('stop_loss'),
            data.get('target_price')
        )
        if not trade_id:
            return jsonify({'error': 'Failed to create trade'}), 500
        
        new_available_margin = portfolio['available_margin'] - margin_required
        new_utilized_margin = portfolio['utilized_margin'] + margin_required
        
        Portfolio.update_margin(
            client_id,  
            new_available_margin,
            new_utilized_margin,
            portfolio['total_pnl']
        )
        
        active_trades[trade_id] = {
            'trade_id': trade_id,
            'last_checked': datetime.utcnow()
        }
        
        start_trade_monitoring()
        
        message = f"Trade created: {data['trade_type']} {quantity} {data['symbol']} at {current_price}"
        send_notification_helper(
            client_id,
            'TRADE_CREATE',
            message
        )
        
        notify_user(client_id, 'trade_created', {
            'trade_id': trade_id,
            'symbol': data['symbol'],
            'trade_type': data['trade_type'],
            'quantity': quantity,
            'entry_price': current_price
        })
        
        logger.info(f"Trade created: {trade_id} for user: {client_id}")
        
        return jsonify({
            'message': 'Trade created successfully',
            'trade_id': trade_id,
            'entry_price': current_price,
            'margin_used': margin_required,
            'remaining_margin': new_available_margin
        }), 201
        
    except Exception as e:
        logger.error(f"Trade creation error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@trades_bp.route('/exit/<trade_id>', methods=['POST'])
@jwt_required()
def exit_trade(trade_id):
    try:
        client_id = get_jwt_identity() 
        user = User.find_by_client_id(client_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404

        trade = Trade.find_by_id(trade_id)
        if not trade or trade.get('user_id') != client_id:  
            return jsonify({'error': 'Trade not found or unauthorized'}), 404
        
        if trade.get('status') != 'ACTIVE':
            return jsonify({'error': 'Trade is not active'}), 400
        
        price_response, status_code = get_live_price(trade['symbol'])
        if status_code != 200:
            return jsonify({'error': 'Failed to fetch market price'}), 500
        
        price_data = json.loads(price_response.get_data(as_text=True))
        exit_price = price_data['price']
        
        if trade['trade_type'] == 'BUY':
            pnl = (exit_price - trade['entry_price']) * trade['quantity']
        else:  
            pnl = (trade['entry_price'] - exit_price) * trade['quantity']
        
        updates = {
            'status': 'CLOSED',
            'current_price': exit_price,
            'pnl': pnl,
            'closed_at': datetime.utcnow()
        }
        Trade.update(trade_id, updates)
        
        update_portfolio_margin(client_id, -trade['margin_used'], pnl)
        
        if trade_id in active_trades:
            del active_trades[trade_id]
        
        message = f"Trade exited: {trade['trade_type']} {trade['quantity']} {trade['symbol']} at {exit_price}, PnL: {pnl}"
        send_notification_helper(
            client_id,
            'TRADE_EXIT',
            message
        )
        
        notify_user(client_id, 'trade_exited', {
            'trade_id': trade_id,
            'symbol': trade['symbol'],
            'exit_price': exit_price,
            'pnl': pnl
        })
        
        logger.info(f"Trade exited: {trade_id} for user: {client_id}")
        
        return jsonify({'message': 'Trade exited successfully', 'pnl': pnl}), 200
        
    except Exception as e:
        logger.error(f"Trade exit error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@trades_bp.route('/exit-all/<user_id>', methods=['POST'])
@jwt_required()
def exit_all_trades(user_id):
    try:
        client_id = get_jwt_identity()
        if client_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        active_trades_list = Trade.find_active_by_user_id(user_id)
        for trade in active_trades_list:
            trade_id = str(trade['_id'])
            price_response, status_code = get_live_price(trade['symbol'])
            if status_code != 200:
                continue  
            
            price_data = json.loads(price_response.get_data(as_text=True))
            exit_price = price_data['price']
            
            if trade['trade_type'] == 'BUY':
                pnl = (exit_price - trade['entry_price']) * trade['quantity']
            else:
                pnl = (trade['entry_price'] - exit_price) * trade['quantity']
            
            updates = {
                'status': 'CLOSED',
                'current_price': exit_price,
                'pnl': pnl,
                'closed_at': datetime.utcnow()
            }
            Trade.update(trade_id, updates)
            
            update_portfolio_margin(user_id, -trade['margin_used'], pnl)
            
            message = f"Trade exited: {trade['trade_type']} {trade['quantity']} {trade['symbol']} at {exit_price}, PnL: {pnl}"
            send_notification_helper(
                user_id,
                'TRADE_EXIT_ALL',
                message
            )
            
            notify_user(user_id, 'trade_exited', {
                'trade_id': trade_id,
                'symbol': trade['symbol'],
                'exit_price': exit_price,
                'pnl': pnl
            })
            
            if trade_id in active_trades:
                del active_trades[trade_id]
        
        return jsonify({'message': 'All active trades exited successfully'}), 200
        
    except Exception as e:
        logger.error(f"Exit all trades error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@trades_bp.route('/<user_id>', methods=['GET'])
@jwt_required()
def get_user_trades(user_id):
    try:
        client_id = get_jwt_identity()
        if client_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        trades = Trade.find_by_user_id(user_id)
        
        return jsonify({'trades': trades}), 200
        
    except Exception as e:
        logger.error(f"Get trades error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@trades_bp.route('/performance/<user_id>', methods=['GET'])
@jwt_required()
def get_trade_performance(user_id):
    try:
        client_id = get_jwt_identity()
        if client_id != user_id:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        performance = Trade.get_performance_by_user_id(user_id)
        
        total_trades = performance.get('total_trades', 0)
        active_trades_count = performance.get('active_trades', 0)
        closed_trades_count = total_trades - active_trades_count
        total_pnl = performance.get('total_pnl', 0)
        winning_trades = performance.get('winning_trades', 0)
        losing_trades = performance.get('losing_trades', 0)
        
        portfolio = Portfolio.find_by_user_id(user_id)
        if portfolio:
            total_margin = portfolio['available_margin'] + portfolio['utilized_margin']
            margin_utilization_percent = (portfolio['utilized_margin'] / total_margin * 100) if total_margin > 0 else 0
            available_margin = portfolio.get('available_margin', 0)
            utilized_margin = portfolio.get('utilized_margin', 0)
        else:
            margin_utilization_percent = 0
            available_margin = utilized_margin = 0
        
        return jsonify({
            'user_id': user_id,
            'total_trades': total_trades,
            'active_trades': active_trades_count,
            'closed_trades': closed_trades_count,
            'total_pnl': total_pnl,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': (winning_trades / closed_trades_count * 100) if closed_trades_count > 0 else 0,
            'margin_utilization_percent': round(margin_utilization_percent, 2),
            'available_margin': available_margin,
            'utilized_margin': utilized_margin
        }), 200
        
    except Exception as e:
        logger.error(f"Trade performance error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def monitor_active_trades():
    global stop_monitoring
    
    while not stop_monitoring:
        try:
            trade_ids_to_remove = []
            
            for trade_id in list(active_trades.keys()):
                trade = Trade.find_by_id(trade_id)
                if not trade or trade.get('status') != 'ACTIVE':
                    trade_ids_to_remove.append(trade_id)
                    continue
                
                price_response, status_code = get_live_price(trade['symbol'])
                if status_code != 200:
                    continue
                
                price_data = json.loads(price_response.get_data(as_text=True))
                current_price = price_data['price']
                
                Trade.update(trade_id, {'current_price': current_price})
                
                stop_loss_hit = False
                target_hit = False
                
                if trade.get('stop_loss'):
                    if trade['trade_type'] == 'BUY' and current_price <= trade['stop_loss']:
                        stop_loss_hit = True
                    elif trade['trade_type'] == 'SELL' and current_price >= trade['stop_loss']:
                        stop_loss_hit = True
                
                if trade.get('target_price'):
                    if trade['trade_type'] == 'BUY' and current_price >= trade['target_price']:
                        target_hit = True
                    elif trade['trade_type'] == 'SELL' and current_price <= trade['target_price']:
                        target_hit = True
                
                if trade['trade_type'] == 'BUY':
                    pnl = (current_price - trade['entry_price']) * trade['quantity']
                else:
                    pnl = (trade['entry_price'] - current_price) * trade['quantity']
                
                if stop_loss_hit or target_hit:
                    status = 'STOP_LOSS_HIT' if stop_loss_hit else 'TARGET_HIT'
                    updates = {
                        'status': status,
                        'pnl': pnl,
                        'closed_at': datetime.utcnow()
                    }
                    Trade.update(trade_id, updates)
                    
                    user_id = trade.get('user_id')
                    if user_id:
                        update_portfolio_margin(user_id, -trade['margin_used'], pnl)
                        
                        reason = "stop loss" if stop_loss_hit else "target"
                        message = f"Trade closed due to {reason}: {trade['trade_type']} {trade['quantity']} {trade['symbol']} at {current_price}, PnL: {pnl}"
                        send_notification_helper(
                            user_id, 
                            status, 
                            message
                        )
                        
                        notify_user(user_id, 'trade_auto_closed', {
                            'trade_id': trade_id,
                            'symbol': trade['symbol'],
                            'reason': reason,
                            'exit_price': current_price,
                            'pnl': pnl
                        })
                    else:
                        logger.warning(f"User ID not found for trade {trade_id} during auto-close")
                    
                    trade_ids_to_remove.append(trade_id)
                    logger.info(f"Trade auto-closed: {trade_id} for {reason}")
            
            for trade_id in trade_ids_to_remove:
                active_trades.pop(trade_id, None)
            
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Trade monitoring error: {str(e)}")
            time.sleep(60)

def start_trade_monitoring():
    global monitor_thread, stop_monitoring, active_trades
    
    all_active = Trade.find_all_active()
    active_trades = {str(t['_id']): {'trade_id': str(t['_id']), 'last_checked': datetime.utcnow()} for t in all_active}
    logger.info(f"Loaded {len(active_trades)} active trades from DB")
    
    stop_monitoring = False
    if monitor_thread is None or not monitor_thread.is_alive():
        monitor_thread = threading.Thread(target=monitor_active_trades)
        monitor_thread.daemon = True
        monitor_thread.start()
        logger.info("Trade monitoring started")

def stop_trade_monitoring():
    global stop_monitoring
    stop_monitoring = True
    logger.info("Trade monitoring stopped")
