import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    
    ENV = os.environ.get('FLASK_ENV', 'development')
    
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY and ENV == 'production':
        raise ValueError("SECRET_KEY must be set in environment variables")
    SECRET_KEY = SECRET_KEY or 'your-secret-key-here'
    
    MONGO_URI = os.environ.get('MONGO_URI')
    if not MONGO_URI and ENV == 'production':
        raise ValueError("MONGO_URI must be set in environment variables")
    MONGO_URI = MONGO_URI or 'mongodb+srv://niteshlakde16:CXFNK4aj8bJnyKag@clusternitesh.wokud7n.mongodb.net/paper_trading'
    
    
    ANGEL_API_KEY = os.environ.get('ANGEL_API_KEY')
    ANGEL_CLIENT_CODE = os.environ.get('ANGEL_CLIENT_CODE')
    ANGEL_PASSWORD = os.environ.get('ANGEL_PASSWORD')
    ANGEL_TOTP_SECRET = os.environ.get('ANGEL_TOTP_SECRET')
    if ENV == 'production' and not all([ANGEL_API_KEY, ANGEL_CLIENT_CODE, ANGEL_PASSWORD, ANGEL_TOTP_SECRET]):
        raise ValueError("Angel One API credentials must be set in environment variables")
    
   
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
    if ENV == 'production' and not (SMTP_USERNAME and SMTP_PASSWORD):
        raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be set for email notifications")
    
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    if ENV == 'production' and not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
        raise ValueError("Twilio credentials must be set for SMS notifications")
    
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    if not JWT_SECRET_KEY and ENV == 'production':
        raise ValueError("JWT_SECRET_KEY must be set in environment variables")
    JWT_SECRET_KEY = JWT_SECRET_KEY or 'jwt-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    REDIS_CACHE_TTL = int(os.environ.get('REDIS_CACHE_TTL', 300))  
