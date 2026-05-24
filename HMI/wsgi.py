"""
Production WSGI Entry Point for HMI Flask Application
Supports both Gunicorn (Linux) and Waitress (Windows) deployment
"""

import os
import sys
import logging
from pathlib import Path

# Add the HMI directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set environment (production/staging/development)
os.environ.setdefault('HMI_ENV', 'production')

# Import the application factory
from app_factory import create_app, socketio

# Create the application instance
application = create_app()
app = application  # Some WSGI servers expect 'app' variable

# For SocketIO-aware servers
def get_socketio_app():
    """
    Returns SocketIO application for eventlet/gevent workers
    """
    return socketio

if __name__ == "__main__":
    """
    For testing the WSGI app directly (not recommended for production)
    """
    print("[WARNING] Running WSGI app in development mode")
    print("For production, use: gunicorn wsgi:application or waitress-serve")
    socketio.run(application, host='0.0.0.0', port=6001, debug=False)
