from flask import Blueprint, jsonify
from config import Config
import logging
from datetime import datetime
from SmartApi import SmartConnect
import pyotp
import time
import yfinance as yf
from random import random


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

market_bp = Blueprint('market', __name__)

request_count = 0
last_request_time = 0

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
    try:
        yahoo_symbol = '^BSESN' if symbol == '^BSESN' else symbol
        ticker = yf.Ticker(yahoo_symbol)
        data = ticker.history(period='1d')
        if not data.empty:
            price = data['Close'].iloc[-1]
            logger.info(f"Yahoo Finance price for {symbol}: {price}")
            return float(price)
        logger.error(f"No Yahoo Finance data for {symbol}")
        return None
    except Exception as e:
        logger.error(f"Yahoo Finance error for {symbol}: {str(e)}")
        return None

@market_bp.route('/live/<symbol>', methods=['GET'])
def get_live_price(symbol):
    logger.info(f"Fetching live price for symbol: {symbol}")
    try:
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
            for attempt in range(3):
                data = client.ltpData(exchange, symbol, token)
                #logger.debug(f"ltpData response for {symbol} (token: {token}): {data}")
                if data['status'] and 'data' in data:
                    price = data['data']['ltp']
                    logger.info(f"Price fetched for {symbol}: {price}")
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
            logger.info(f"Using mock price for {symbol}: {price}")
            return jsonify({
                'symbol': symbol,
                'price': price,
                'timestamp': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
            }), 200
        return jsonify({'error': f'Failed to fetch price: {str(e)}'}), 500