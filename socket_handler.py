from threading import Thread, Lock
import socket
from flask_socketio import SocketIO, emit, join_room
from flask import request
from SmartApi import SmartConnect
from config import Config
import logging
from datetime import datetime
import time
import random
import pyotp
import yfinance as yf
import redis
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

socketio = SocketIO()

user_rooms = {}
angel_session = None
session_lock = Lock()
last_price_update = {}
request_count = 0
last_request_time = 0
yahoo_request_count = 0
redis_client = redis.Redis.from_url(Config.REDIS_URL, decode_responses=True)

def check_network():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        logger.error("Network connectivity check failed")
        return False

@socketio.on('connect')
def handle_connect():
    emit('status', {'msg': 'Connected to paper trading WS'})

@socketio.on('join')
def on_join(data):
    user_id = data['user_id']
    join_room(user_id)
    user_rooms[request.sid] = user_id
    emit('status', {'msg': f'Joined room {user_id}'}, room=user_id)
    logger.info(f"User {user_id} joined room with sid {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in user_rooms:
        user_id = user_rooms[request.sid]
        del user_rooms[request.sid]
        logger.info(f"User {user_id} disconnected, sid {request.sid}")

def get_angel_session():
    global angel_session, request_count, last_request_time
    
    with session_lock:
        current_time = time.time()
        if current_time - last_request_time < 1:
            request_count += 1
            if request_count > 3:
                logger.warning("Rate limit exceeded, waiting...")
                time.sleep(1 - (current_time - last_request_time))
                request_count = 1
                last_request_time = time.time()
        else:
            request_count = 1
            last_request_time = current_time

        if angel_session and time.time() - angel_session.get('created', 0) < 3600:
            angel_session['last_used'] = time.time()
            logger.info("Reusing existing Angel One session")
            return angel_session['obj']
        
        try:
            api_key = Config.ANGEL_API_KEY
            client_code = Config.ANGEL_CLIENT_CODE
            pwd = Config.ANGEL_PASSWORD
            totp_secret = Config.ANGEL_TOTP_SECRET
            
            obj = SmartConnect(api_key=api_key)
            totp = pyotp.TOTP(totp_secret).now()
            data = obj.generateSession(client_code, pwd, totp)
            
            if not data['status']:
                logger.error(f"Login failed: {data['message']}")
                return None
            
            angel_session = {
                'obj': obj,
                'created': time.time(),
                'last_used': time.time()
            }
            
            logger.info("Created new Angel One session")
            return obj
            
        except Exception as e:
            logger.error(f"Failed to create Angel One session: {str(e)}")
            return None

def get_yahoo_price(symbol):
    global yahoo_request_count
    try:
        yahoo_request_count += 1
        logger.debug(f"Yahoo Finance request #{yahoo_request_count} for {symbol}")
        
        cache_key = f"price:{symbol}"
        cached_price = redis_client.get(cache_key)
        if cached_price:
            logger.info(f"Cache hit for {symbol}: {cached_price}")
            return float(cached_price)
        
        for attempt in range(3):
            try:
                ticker = yf.Ticker(symbol)
                data = ticker.history(period='1d')
                if not data.empty:
                    price = data['Close'].iloc[-1]
                    redis_client.setex(cache_key, Config.REDIS_CACHE_TTL, price)
                    logger.info(f"Yahoo Finance price for {symbol} (attempt {attempt + 1}): {price}")
                    return float(price)
                logger.warning(f"No Yahoo Finance data for {symbol} (attempt {attempt + 1})")
            except Exception as e:
                if '429' in str(e):
                    wait_time = min(2 ** attempt * 2, 10)
                    logger.warning(f"Rate limit (429) for {symbol}, waiting {wait_time}s")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Yahoo Finance error for {symbol} (attempt {attempt + 1}): {str(e)}")
        logger.error(f"No data available for {symbol} after retries")
        return None
    except Exception as e:
        logger.error(f"Yahoo Finance error for {symbol}: {str(e)}")
        return None

def start_price_polling(app):
    def polling_loop():
        retry_count = 0
        max_retries = 3
        
        while True:
            try:
                if not check_network():
                    logger.error("No network connectivity, using mock data")
                    use_mock_data(app)
                    time.sleep(60)
                    continue
                
                obj = get_angel_session()
                if not obj:
                    logger.error("Failed to get Angel One session, using mock data")
                    use_mock_data(app)
                    time.sleep(60)
                    continue
                
                for symbol in ['^NSEI', '^BSESN']:
                    price = get_price_via_rest(obj, symbol)
                    if price:
                        with app.app_context():
                            socketio.emit('live_price', {
                                'symbol': symbol,
                                'price': price,
                                'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
                            })
                            last_price_update[symbol] = price
                
                retry_count = 0
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in polling: {str(e)}")
                retry_count += 1
                
                if retry_count >= max_retries:
                    logger.error("Max retries reached, switching to mock data")
                    use_mock_data(app)
                    retry_count = 0
                    time.sleep(300)
                else:
                    sleep_time = min(60 * (2 ** retry_count), 300)
                    logger.info(f"Retrying after {sleep_time} seconds")
                    time.sleep(sleep_time)
    
    thread = Thread(target=polling_loop, daemon=True)
    thread.start()

def get_price_via_rest(obj, symbol):
    try:
        cache_key = f"price:{symbol}"
        cached_price = redis_client.get(cache_key)
        if cached_price:
            logger.info(f"Cache hit for {symbol}: {cached_price}")
            return float(cached_price)
        
        symbol_map = {
            '^NSEI': [('NSE', '99926000')],
            '^BSESN': [('BSE', '1'), ('BSE', '99926009')]
        }
        if symbol not in symbol_map:
            logger.error(f"Unknown symbol: {symbol}")
            return get_mock_price(symbol)
        
        tokens = symbol_map[symbol]
        
        for exchange, token in tokens:
            for attempt in range(3):
                quote_data = obj.ltpData(exchange, symbol, token)
                logger.debug(f"ltpData response for {symbol} (token: {token}): {quote_data}")
                if quote_data['status'] and 'data' in quote_data and 'ltp' in quote_data['data']:
                    price = quote_data['data']['ltp']
                    redis_client.setex(cache_key, Config.REDIS_CACHE_TTL, price)
                    logger.info(f"Price fetched for {symbol} (token: {token}): {price}")
                    return float(price)
                error_msg = quote_data.get('message', 'Unknown error')
                logger.error(f"ltpData attempt {attempt + 1} failed for {symbol} (token: {token}): {error_msg}")
                if "exceeding access rate" in error_msg.lower():
                    time.sleep(2)
        
        if symbol == '^BSESN':
            price = get_yahoo_price(symbol)
            if price:
                return price
        
        raise Exception(f"No data available for {symbol} after retries")
    except Exception as e:
        logger.error(f"Error getting price for {symbol}: {str(e)}")
        return last_price_update.get(symbol) or get_mock_price(symbol)

def get_mock_price(symbol):
    mock_prices = {'^NSEI': 25000.0, '^BSESN': 80000.0}
    if symbol in mock_prices:
        price = mock_prices[symbol] * (1 + random.uniform(-0.01, 0.01))
        redis_client.setex(f"price:{symbol}", Config.REDIS_CACHE_TTL, price)
        logger.info(f"Using mock price for {symbol}: {price}")
        return price
    return None

def use_mock_data(app):
    for symbol in ['^NSEI', '^BSESN']:
        price = get_mock_price(symbol)
        if price:
            with app.app_context():
                socketio.emit('live_price', {
                    'symbol': symbol,
                    'price': price,
                    'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
                    'warning': 'Using mock price due to API failure'
                })
                last_price_update[symbol] = price

def start_websocket(app):
    logger.info("Starting price polling with rate limiting")
    start_price_polling(app)

def notify_user(user_id, event, data):
    try:
        if user_id not in user_rooms.values():
            logger.warning(f"No active WebSocket room for user {user_id}")
            return False
        socketio.emit('trade_update', {'event': event, 'data': data}, room=user_id)
        logger.info(f"WebSocket notification sent to user {user_id} for event {event}")
        return True
    except Exception as e:
        logger.error(f"Failed to send WebSocket notification to {user_id}: {str(e)}")
        return False
