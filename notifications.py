from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import User, Notification
from config import Config
import logging
import smtplib
from twilio.rest import Client
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

notifications_bp = Blueprint('notifications', __name__)
logger = logging.getLogger(__name__)

# Initialize Twilio client with error handling
try:
    if hasattr(Config, 'TWILIO_ACCOUNT_SID') and hasattr(Config, 'TWILIO_AUTH_TOKEN'):
        twilio_client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
    else:
        twilio_client = None
        logger.warning("Twilio credentials not found in config")
except Exception as e:
    logger.error(f"Failed to initialize Twilio client: {str(e)}")
    twilio_client = None

def send_email(to_email, subject, message):
    """Send email notification"""
    try:
        if not all([hasattr(Config, 'SMTP_SERVER'), hasattr(Config, 'SMTP_PORT'), 
                   hasattr(Config, 'SMTP_USERNAME'), hasattr(Config, 'SMTP_PASSWORD')]):
            logger.warning("SMTP configuration incomplete")
            return False
            
        msg = MIMEMultipart()
        msg['From'] = Config.SMTP_USERNAME
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(message, 'plain'))
        
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
        server.starttls()
        server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email sending error: {str(e)}")
        return False

def send_sms(to_phone, message):
    """Send SMS notification"""
    try:
        if not twilio_client:
            logger.warning("Twilio client not available")
            return False
            
        twilio_client.messages.create(
            body=message,
            from_=Config.TWILIO_PHONE_NUMBER,
            to=to_phone
        )
        logger.info(f"SMS sent to {to_phone}")
        return True
    except Exception as e:
        logger.error(f"SMS sending error: {str(e)}")
        return False

def send_notification(user_id, notification_type, message):
    """Helper function to send notifications (not a route)"""
    try:
        user = User.find_by_client_id(user_id)  # Use find_by_client_id since user_id is email
        if not user:
            logger.error(f"User {user_id} not found for notification")
            return False

        # Create notification record
        notification_id = Notification.create(user_id, notification_type, message)
        if not notification_id:
            logger.error(f"Failed to create notification record for user {user_id}")
            return False

        # Send email and SMS
        email_sent = False
        sms_sent = False
        
        if user.get('email'):
            email_sent = send_email(user['email'], "Trade Notification", message)
        
        if user.get('phone'):
            sms_sent = send_sms(user['phone'], message)

        success = email_sent or sms_sent
        logger.info(f"Notification {'sent' if success else 'failed'} for user: {user_id}")
        return success
        
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        return False

@notifications_bp.route('/', methods=['POST'])
@jwt_required()
def send_notification_route():
    """API endpoint to send notifications"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        required_fields = ['notification_type', 'message']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'{field} is required'}), 400
        
        success = send_notification(
            user_id,
            data['notification_type'],
            data['message']
        )
        
        if success:
            return jsonify({'message': 'Notification sent successfully'}), 200
        else:
            return jsonify({'error': 'Failed to send notification'}), 500
        
    except Exception as e:
        logger.error(f"Notification route error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@notifications_bp.route('/history', methods=['GET'])
@jwt_required()
def get_notification_history():
    """Get user's notification history"""
    try:
        user_id = get_jwt_identity()
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        
        # Validate pagination parameters
        if page < 1:
            page = 1
        if limit < 1 or limit > 100:
            limit = 20
            
        notifications = Notification.get_by_user_id(user_id, page=page, limit=limit)
        
        return jsonify({
            'notifications': notifications,
            'page': page,
            'limit': limit
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching notification history: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@notifications_bp.route('/<int:notification_id>/read', methods=['PUT'])
@jwt_required()
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        user_id = get_jwt_identity()
        
        success = Notification.mark_as_read(notification_id, user_id)
        
        if success:
            return jsonify({'message': 'Notification marked as read'}), 200
        else:
            return jsonify({'error': 'Notification not found or unauthorized'}), 404
        
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@notifications_bp.route('/unread-count', methods=['GET'])
@jwt_required()
def get_unread_count():
    """Get count of unread notifications"""
    try:
        user_id = get_jwt_identity()
        count = Notification.get_unread_count(user_id)
        
        return jsonify({'unread_count': count}), 200
        
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Function to be used by other modules (like trades.py)
def notify_user(user_id, notification_type, message):
    """Function to be called by other modules to send notifications"""
    return send_notification(user_id, notification_type, message)