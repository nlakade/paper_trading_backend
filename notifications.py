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

twilio_client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)

def send_email(to_email, subject, message):
    try:
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
    try:
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

@notifications_bp.route('/', methods=['POST'])
@jwt_required()
def send_notification(user_id, notification_type, message):
    user = User.find_by_id(user_id)
    if not user:
        logger.error(f"User {user_id} not found for notification")
        return False

    # Create notification record
    Notification.create(user_id, notification_type, message)

    # Send email and SMS
    email_sent = send_email(user['email'], "Trade Notification", message)
    sms_sent = send_sms(user['phone'], message)

    logger.info(f"Notification sent for user: {user_id}")
    return email_sent or sms_sent


@notifications_bp.route('/', methods=['POST'])
@jwt_required()
def send_notification_route():
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
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
            return jsonify({'message': 'Notification sent'}), 200
        else:
            return jsonify({'error': 'Failed to send notification'}), 500
        
    except Exception as e:
        logger.error(f"Notification error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500