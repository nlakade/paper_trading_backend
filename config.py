import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv() 

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb+srv://niteshlakde16:CXFNK4aj8bJnyKag@clusternitesh.wokud7n.mongodb.net/paper_trading'
    
    ANGEL_API_KEY = os.getenv('ANGEL_API_KEY', 'your_angel_api_key')
    ANGEL_CLIENT_CODE = os.getenv('ANGEL_CLIENT_CODE', 'your_client_code')
    ANGEL_PASSWORD = os.getenv('ANGEL_PASSWORD', 'your_password')
    ANGEL_TOTP_SECRET = os.getenv('ANGEL_TOTP_SECRET', 'your_totp_secret')
    
    SMTP_SERVER = os.environ.get('SMTP_SERVER') or 'smtp.gmail.com'
    SMTP_PORT = int(os.environ.get('SMTP_PORT') or 587)
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME') or 'your-email@gmail.com'
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD') or 'your-app-password'
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID') or 'your-twilio-sid'
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN') or 'your-twilio-token'
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER') or 'your-twilio-number'
    
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'