from app import app, socketio
from trades import start_trade_monitoring, stop_trade_monitoring
from socket_handler import start_websocket
import threading

if __name__ == '__main__':
    start_trade_monitoring()
    
    websocket_thread = threading.Thread(target=start_websocket, args=(app,))
    websocket_thread.daemon = True
    websocket_thread.start()
    
    try:
        socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        stop_trade_monitoring()
        print("Server stopped")