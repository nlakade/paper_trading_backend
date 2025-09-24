from flask import Flask
from flask_jwt_extended import JWTManager
from flask_pymongo import PyMongo
from config import Config
from auth import auth_bp
from portfolio import portfolio_bp
from trades import trades_bp
from market import market_bp
from notifications import notifications_bp
from socket_handler import socketio, start_websocket
from models import mongo, JSONEncoder
import logging
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    mongo.init_app(app)
    jwt = JWTManager(app)
    
    app.register_blueprint(notifications_bp, url_prefix='/notifications')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(portfolio_bp, url_prefix='/portfolio')
    app.register_blueprint(trades_bp, url_prefix='/trades')
    app.register_blueprint(market_bp, url_prefix='/market')
    
    app.json_encoder = JSONEncoder
    
    socketio.init_app(app, cors_allowed_origins="*")
    
    return app

app = create_app()

if __name__ == '__main__':
    websocket_thread = threading.Thread(target=start_websocket, args=(app,))
    websocket_thread.daemon = True
    websocket_thread.start()
    
    try:
        socketio.run(app, debug=False, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        logger.info("Server stopped")