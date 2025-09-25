from flask import Blueprint, jsonify
from config import Config
import logging
from datetime import datetime
from SmartApi import SmartConnect
import pyotp
import time
import yfinance as yf
import random
import redis
import json

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

market_bp = Blueprint('market', __name__)

request_count = 0
last_request_time = 0
yahoo_request_count = 0
redis_client = redis.Redis.from_url(Config.REDIS_URL, decode_responses=True)

def get_angel_session():
    global request_count, last_request_time
    
    try:
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

        obj = SmartConnect(api_key=Config.ANGEL_API_KEY)
        totp = pyotp.TOTP(Config.ANGEL_TOTP_SECRET).now()
        data = obj.generateSession(Config.ANGEL_CLIENT_CODE, Config.ANGEL_PASSWORD, totp)
        
        if not data['status']:
            raise Exception(f"Login failed: {data['message']}")
        
        logger.info("Created new Angel One session for market")
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

@market_bp.route('/live/<symbol>', methods=['GET'])
def get_live_price(symbol):
    logger.info(f"Fetching live price for symbol: {symbol}")
    try:
        cache_key = f"price:{symbol}"
        cached_price = redis_client.get(cache_key)
        if cached_price:
            logger.info(f"Cache hit for {symbol}: {cached_price}")
            return jsonify({
                'symbol': symbol,
                'price': float(cached_price),
                'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
            }), 200
        
        client = get_angel_session()
        if not client:
            raise Exception("Angel One connection failed")
        
        symbol_map = {
            '^NSEI': [('NSE', '99926000')],
            '^BSESN': [('BSE', '1'), ('BSE', '99926009')]
        }
        if symbol not in symbol_map:
            raise Exception(f"Unknown symbol: {symbol}")
        
        tokens = symbol_map[symbol]
        
        for exchange, token in tokens:
            for attempt in range(5):
                data = client.ltpData(exchange, symbol, token)
                if data['status'] and 'data' in data and 'ltp' in data['data']:
                    price = data['data']['ltp']
                    redis_client.setex(cache_key, Config.REDIS_CACHE_TTL, price)
                    logger.info(f"Price fetched for {symbol} (token: {token}, attempt {attempt + 1}): {price}")
                    return jsonify({
                        'symbol': symbol,
                        'price': float(price),
                        'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
                    }), 200
                error_msg = data.get('message', 'Unknown error')
                logger.error(f"ltpData attempt {attempt + 1} failed for {symbol} (token: {token}): {error_msg}")
                if "exceeding access rate" in error_msg.lower():
                    time.sleep(2)
        
        if symbol == '^BSESN':
            price = get_yahoo_price(symbol)
            if price:
                return jsonify({
                    'symbol': symbol,
                    'price': price,
                    'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
                }), 200
        
        raise Exception(f"No data available for {symbol} after retries")
    except Exception as e:
        logger.error(f"Error fetching price for {symbol}: {str(e)}")
        mock_prices = {'^NSEI': 25000.0, '^BSESN': 80000.0}
        if symbol in mock_prices:
            price = mock_prices[symbol] * (1 + random.uniform(-0.01, 0.01))
            redis_client.setex(cache_key, Config.REDIS_CACHE_TTL, price)
            logger.info(f"Using mock price for {symbol}: {price}")
            return jsonify({
                'symbol': symbol,
                'price': price,
                'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S'),
                'warning': 'Using mock price due to API failure'
            }), 200
        return jsonify({'error': f'Failed to fetch price: {str(e)}'}), 500
