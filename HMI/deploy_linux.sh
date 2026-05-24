#!/bin/bash
# ============================================================================
# HMI Flask Application - Linux Production Deployment Script
# Deploys using Gunicorn WSGI server with eventlet workers
# ============================================================================

set -e  # Exit on error

echo "============================================================================"
echo "HMI Flask Application - Production Deployment (Linux)"
echo "============================================================================"
echo ""

# Change to script directory
cd "$(dirname "$0")"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed!"
    echo "Install with: sudo apt-get install python3 python3-pip python3-venv"
    exit 1
fi

echo "[1/8] Checking Python version..."
python3 --version

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "[2/8] Creating virtual environment..."
    python3 -m venv venv
else
    echo "[2/8] Virtual environment already exists"
fi

# Activate virtual environment
echo "[3/8] Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "[4/8] Upgrading pip..."
pip install --upgrade pip

# Install production requirements
echo "[5/8] Installing production dependencies..."
pip install -r requirements-production.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "[WARNING] .env file not found!"
    echo "Creating from .env.example..."
    cp .env.example .env
    echo ""
    echo "[ACTION REQUIRED] Please edit .env file with your production settings!"
    echo "Run: nano .env"
    echo "Press any key to continue after editing..."
    read -n 1 -s
fi

# Create logs directory
mkdir -p logs

# Set environment to production
export HMI_ENV=production

echo "[6/8] Validating configuration..."
python config_manager.py

echo "[7/8] Setting up log rotation (optional)..."
if command -v logrotate &> /dev/null; then
    echo "logrotate is installed - you can configure it for HMI logs"
else
    echo "logrotate not found - install with: sudo apt-get install logrotate"
fi

echo "[8/8] Starting HMI Flask Application with Gunicorn..."
echo ""
echo "============================================================================"
echo "Server will start on: http://0.0.0.0:6001"
echo "Press CTRL+C to stop the server"
echo "============================================================================"
echo ""

# Start with Gunicorn (eventlet worker for WebSocket support)
gunicorn \
    --worker-class eventlet \
    --workers 1 \
    --bind 0.0.0.0:6001 \
    --timeout 120 \
    --keepalive 5 \
    --log-level info \
    --access-logfile logs/gunicorn-access.log \
    --error-logfile logs/gunicorn-error.log \
    --capture-output \
    wsgi:application

echo ""
echo "============================================================================"
echo "Server stopped"
echo "============================================================================"
