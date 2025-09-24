from datetime import datetime
from flask_pymongo import PyMongo
from bson import ObjectId 
import json

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return json.JSONEncoder.default(self, o)

mongo = PyMongo()

class User:
    @staticmethod
    def create(client_id, name, email, phone, password):
        return mongo.db.users.insert_one({
            'client_id': client_id,  
            'name': name,
            'email': email,
            'phone': phone,
            'password': password,
            'created_at': datetime.utcnow(),
            'is_active': True
        })
    
    @staticmethod
    def find_by_client_id(client_id):
        return mongo.db.users.find_one({'client_id': client_id})
    
    @staticmethod
    def find_by_email(email):
        return mongo.db.users.find_one({'email': email})
    
    @staticmethod
    def find_by_id(user_id):
        try:
            return mongo.db.users.find_one({'_id': ObjectId(user_id)})
        except:
            return mongo.db.users.find_one({'client_id': user_id})

class Portfolio:
    @staticmethod
    def create(user_id, initial_margin=100000.0):
        return mongo.db.portfolios.insert_one({
            'user_id': user_id, 
            'available_margin': initial_margin,
            'utilized_margin': 0.0,
            'total_pnl': 0.0,
            'last_updated': datetime.utcnow()
        })
    
    @staticmethod
    def find_by_user_id(user_id):
        return mongo.db.portfolios.find_one({'user_id': user_id})
    
    @staticmethod
    def update_margin(user_id, available_margin, utilized_margin, total_pnl):
        return mongo.db.portfolios.update_one(
            {'user_id': user_id},
            {'$set': {
                'available_margin': available_margin,
                'utilized_margin': utilized_margin,
                'total_pnl': total_pnl,
                'last_updated': datetime.utcnow()
            }}
        )

class Trade:
    @staticmethod
    def create(user_id, symbol, trade_type, quantity, entry_price, current_price, margin_used, stop_loss=None, target_price=None):
        return mongo.db.trades.insert_one({
            'user_id': user_id,  
            'symbol': symbol,
            'trade_type': trade_type,
            'quantity': quantity,
            'entry_price': entry_price,
            'current_price': current_price,
            'margin_used': margin_used,
            'stop_loss': stop_loss,
            'target_price': target_price,
            'status': 'ACTIVE',
            'pnl': 0.0,
            'created_at': datetime.utcnow(),
            'closed_at': None
        })
    
    @staticmethod
    def find_by_user_id(user_id):
        return list(mongo.db.trades.find({'user_id': user_id}))
    
    @staticmethod
    def find_active_by_user_id(user_id):
        return list(mongo.db.trades.find({'user_id': user_id, 'status': 'ACTIVE'}))
    
    @staticmethod
    def update(trade_id, updates):
        try:
            if isinstance(trade_id, str) and len(trade_id) == 24:
                trade_obj_id = ObjectId(trade_id)
            else:
                trade_obj_id = trade_id
            
            return mongo.db.trades.update_one(
                {'_id': trade_obj_id},
                {'$set': updates}
            )
        except Exception as e:
            print(f"Error updating trade: {e}")
            return None

    @staticmethod
    def find_by_id(trade_id):
        try:
            if isinstance(trade_id, str) and len(trade_id) == 24:
                trade_obj_id = ObjectId(trade_id)
            else:
                trade_obj_id = trade_id
            
            return mongo.db.trades.find_one({'_id': trade_obj_id})
        except Exception as e:
            print(f"Error finding trade: {e}")
            return None

class Notification:
    @staticmethod
    def create(user_id, notification_type, message):
        return mongo.db.notifications.insert_one({
            'user_id': user_id,  
            'type': notification_type,
            'message': message,
            'sent_at': datetime.utcnow(),
            'is_read': False
        })
    
    @staticmethod
    def find_by_user_id(user_id):
        return list(mongo.db.notifications.find({'user_id': user_id}))
