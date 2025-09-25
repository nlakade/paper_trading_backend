# Paper Trading Platform Backend Documentation

## Overview
This is a Flask-based backend for a paper trading platform, allowing users to register, manage portfolios, execute trades, track performance, and receive real-time market updates via WebSocket. It uses MongoDB (Atlas) for data storage, Angel One SmartAPI for market data (with mock fallbacks for demo reliability), and Flask-SocketIO for real-time notifications. The application supports user authentication (JWT), trade execution with margin validation, auto-closure (stop-loss/target), and notifications (SMS/email).

Key Features:
- **User Authentication**: Register/login with JWT.
- **Portfolio Management**: Create/update margin and PnL.
- **Market Data**: Live prices for NSEI/BSESN (REST + WebSocket).
- **Trade Execution**: Create/exit trades with validation.
- **Performance Tracking**: Active/total PnL, margin utilization.
- **Real-Time Updates**: WebSocket for prices and trade events.
- **Notifications**: Mock/real SMS/email for events.
- **Error Handling**: Rate limiting, validation, logging.

## Setup Instructions
1. **Prerequisites**:
   - Python 3.12
   - MongoDB Atlas (or local MongoDB)
   - Node.js (for WebSocket client testing)

2. **Clone/Navigate**:
   ```bash
   cd C:\Users\NITESH DNYANDEV LAKA\Downloads\paper_trading_backend
   ```

3. **Virtual Environment**:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure `.env`**:
   ```
   MONGO_URI=mongodb+srv:/net/paper_trading
   SECRET_KEY=your-secret-key-here
   ANGEL_API_KEY=your_angel_api_key
   ANGEL_CLIENT_CODE=your_client_code
   ANGEL_PASSWORD=your_password
   ANGEL_TOTP_SECRET=your_totp_secret
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your-email@gmail.com
   SMTP_PASSWORD=your-app-password
   TWILIO_ACCOUNT_SID=your-twilio-sid
   TWILIO_AUTH_TOKEN=your-twilio-token
   TWILIO_PHONE_NUMBER=your-twilio-number
   JWT_SECRET_KEY=jwt-secret-key
   REDIS_URL=redis://localhost:6379/0
   ```
   - Replace placeholders with real values.
   - For demo, use mock data (set `ANGEL_*` to `demo`).

6. **Run MongoDB Atlas**:
   - No local `mongod` needed; Atlas URI is used.

7. **Run Server**:
   ```bash
   python run.py
   ```
   - Confirm: `* Running on http://127.0.0.1:5000`

8. **Test with Postman**:
   - Import the provided Postman collection (`paper_trading_collection.json`).
   - Set environment variables: `jwt_token`, `user_id` (`john@example.com`), `trade_id`.
   - Run collection runner.

Output :

![Screenshot of console output](https://github.com/nlakade/paper_trading_backend/blob/main/logs/Screenshot_20250925_224411.png)




   

9. **Test WebSocket**:
   - Save as `client.js`:
     ```javascript
     const io = require('socket.io-client');
     const socket = io('http://localhost:5000');
     socket.on('connect', () => {
       console.log('Connected');
       socket.emit('join', { user_id: 'john@example.com' });
       socket.on('live_price', (data) => console.log('Market:', data));
       socket.on('trade_update', (data) => console.log('Trade:', data));
     });
     ```
   - Run:
     ```bash
     node client.js
     ```

## Configuration
- **.env**: Loads via `python-dotenv`. See above for structure.
- **config.py**: Defines Flask config from `.env`.
- **MongoDB**: Uses `flask-pymongo` with Atlas URI. Database: `paper_trading`; Collections: `users`, `portfolios`, `trades`, `notifications`.
- **Angel One API**: For market data; requires credentials. Rate-limited to 3 requests/second.
- **Notifications**: SMTP for email, Twilio for SMS; mock if credentials missing.
- **JWT**: 24-hour expiration; secret from `.env`.
- **Redis**: Optional for WebSocket scaling (in-memory for demo).

## Models (models.py)
Uses `flask_pymongo` for MongoDB integration. `JSONEncoder` handles `ObjectId` and `datetime` serialization.

### User
- **create(client_id, name, email, phone, password)**: Inserts new user with hashed password (use `werkzeug.security.generate_password_hash` in auth.py).
- **find_by_client_id(client_id)**: Retrieves user by client_id.
- **find_by_email(email)**: Retrieves user by email.
- **find_by_id(user_id)**: Retrieves user by ObjectId.

### Portfolio
- **create(user_id, initial_margin=100000.0)**: Creates portfolio with initial margin.
- **find_by_user_id(user_id)**: Retrieves portfolio.
- **update_margin(user_id, available_margin, utilized_margin, total_pnl)**: Updates margin and PnL.

### Trade
- **create(user_id, symbol, trade_type, quantity, entry_price, current_price, margin_used, stop_loss=None, target_price=None)**: Creates active trade.
- **find_by_user_id(user_id)**: Retrieves all trades for user.
- **find_active_by_user_id(user_id)**: Retrieves active trades.
- **update(trade_id, updates)**: Updates trade (e.g., status, PnL).
- **find_by_id(trade_id)**: Retrieves trade by ObjectId.

### Notification
- **create(user_id, notification_type, message)**: Creates unread notification.
- **find_by_user_id(user_id)**: Retrieves notifications for user.

## Endpoints
All endpoints use JSON. Authenticated routes require `Authorization: Bearer <jwt_token>`.

### Auth
- **POST /auth/register**:
  - Body: `{"name": "str", "email": "str", "phone": "str", "password": "str"}`
  - Response (201): `{"message": "User registered", "client_id": "str"}`
  - Validates required fields; checks email uniqueness.

- **POST /auth/login**:
  - Body: `{"email": "str", "password": "str"}`
  - Response (200): `{"access_token": "jwt", "client_id": "str"}`
  - Verifies password; returns JWT token.

### Portfolio
- **POST /portfolio/create** (Authenticated):
  - Body: `{}`
  - Response (201): `{"portfolio_id": "str", "user_id": "str", "available_margin": float, "utilized_margin": 0.0, "total_pnl": 0.0, "last_updated": "iso"}`
  - Creates portfolio if not exists.

- **GET /portfolio/<user_id>** (Authenticated):
  - Response (200): Same as create.
  - Validates user_id matches token; returns 404 if not found.

### Market
- **GET /market/live/<symbol>**:
  - Path: `/market/live/^NSEI` or `/market/live/^BSESN`
  - Response (200): `{"symbol": "str", "price": float, "timestamp": "iso"}`
  - Fetches live price; falls back to mock if API fails.

### Trades
- **POST /trades/create** (Authenticated):
  - Body: `{"symbol": "str", "trade_type": "BUY/SELL", "quantity": int, "stop_loss": float (optional), "target_price": float (optional)}`
  - Response (201): `{"trade_id": "str", "user_id": "str", "symbol": "str", "trade_type": "str", "quantity": int, "entry_price": float, "stop_loss": float, "target_price": float, "status": "ACTIVE", "created_at": "iso"}`
  - Validates fields, margin; fetches entry_price from market.

- **POST /trades/exit/<trade_id>** (Authenticated):
  - Body: `{}`
  - Response (200): `{"message": "Trade exited", "pnl": float}`
  - Closes trade; updates portfolio.

- **POST /trades/exit-all/<user_id>** (Authenticated):
  - Body: `{}`
  - Response (200): `{"message": "All trades exited", "total_pnl": float}`
  - Closes all active trades; updates portfolio.

- **GET /trades/performance/<user_id>** (Authenticated):
  - Response (200): `{"active_pnl": float, "total_pnl": float, "margin_utilization_pct": float, "margin_utilization_abs": float, "available_margin": float}`
  - Calculates unrealized/realized PnL and margin metrics.

### Notifications
- **POST /notifications** (Authenticated):
  - Body: `{"event": "str", "message": "str"}`
  - Response (200): `{"message": "Notification sent"}`
  - Sends SMS/email; rate-limited to 5/minute.

## WebSocket Integration
- **Events**:
  - `connect`: Client connected.
  - `join`: Client joins room (`{user_id: "str"}`).
  - `live_price`: Emitted for price updates (`{"symbol": "str", "price": float, "timestamp": "iso"}`).
  - `trade_update`: Emitted for trade events (`{"event": "str", "data": {}}`).
- **Fallback**: Mock prices (`^NSEI`: ~25000.0, `^BSESN`: ~80000.0) if API fails.

## Trade Monitoring
- **Background Thread**: Runs every 10 seconds to check active trades for stop-loss/target triggers.
- **Auto-Closure**: Updates trade status, PnL, and portfolio; notifies via WebSocket/email/SMS.

## Dependencies
- **Flask & Extensions**: Core framework, JWT, PyMongo, SocketIO, Limiter.
- **API**: `smartapi-python` for Angel One, `yfinance` for BSE fallback.
- **Other**: `pyotp` for TOTP, `logzero` for logging, `websocket-client` for WebSocket.
- **Testing**: Postman collection included for endpoints.

## Error Handling
- **Validation**: Required fields checked; returns 400.
- **Authentication**: 401 for invalid JWT.
- **Rate Limiting**: 200/day, 50/hour default; 5/minute for notifications.
- **API Fallback**: Mock data for market failures.
- **Logging**: DEBUG level for API responses; INFO for events.

## Deployment Notes
- **Production**: Use Gunicorn/NGINX, Redis for Limiter, MongoDB Atlas.
- **Scaling**: WebSocket with Redis pub/sub.
- **Security**: Hash passwords with `werkzeug.security`; validate TOTP.

"# paper_trading_bot" 
