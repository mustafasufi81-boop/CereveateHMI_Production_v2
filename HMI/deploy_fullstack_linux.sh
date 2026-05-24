#!/bin/bash
# ============================================================================
# Full Stack Deployment - React Frontend + Flask Backend (Linux)
# Deploys both frontend and backend for production
# ============================================================================

set -e

echo "============================================================================"
echo "HMI Full Stack Production Deployment (Linux)"
echo "React Frontend + Flask Backend"
echo "============================================================================"
echo ""

cd "$(dirname "$0")"

# ============================================================================
# STEP 1: Build React Frontend
# ============================================================================
echo ""
echo "============================================================================"
echo "STEP 1/2: Building React Frontend"
echo "============================================================================"
chmod +x build_react_linux.sh
./build_react_linux.sh

# ============================================================================
# STEP 2: Deploy Flask Backend
# ============================================================================
echo ""
echo "============================================================================"
echo "STEP 2/2: Deploying Flask Backend"
echo "============================================================================"

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
    read -p "Press Enter after editing..." 
fi

# Create logs directory
mkdir -p logs

# Set environment to production
export HMI_ENV=production

echo "[6/8] Validating configuration..."
python config_manager.py

echo ""
echo "============================================================================"
echo "Deployment Summary"
echo "============================================================================"
echo "✅ React frontend built: apex-hmi/dist/"
echo "✅ Flask backend configured"
echo ""
echo "Next Steps:"
echo ""
echo "Option A - Test Locally:"
echo "  Run: ./deploy_linux.sh (starts Gunicorn server)"
echo "  Visit: http://localhost:6001"
echo ""
echo "Option B - Install as systemd Service:"
echo "  Run: sudo ./install_service_linux.sh"
echo ""
echo "Option C - Deploy with nginx:"
echo "  1. Install nginx: sudo apt install nginx"
echo "  2. Copy nginx.conf: sudo cp nginx.conf /etc/nginx/sites-available/hmi-flask"
echo "  3. Update paths in nginx.conf"
echo "  4. Enable site: sudo ln -s /etc/nginx/sites-available/hmi-flask /etc/nginx/sites-enabled/"
echo "  5. Install service: sudo ./install_service_linux.sh"
echo "  6. Test nginx: sudo nginx -t"
echo "  7. Restart nginx: sudo systemctl restart nginx"
echo "  8. Visit: https://hmi.yourdomain.com"
echo ""
echo "============================================================================"

echo ""
echo "[7/8] Setting up log rotation..."
if command -v logrotate &> /dev/null; then
    echo "logrotate is installed"
else
    echo "Install logrotate: sudo apt-get install logrotate"
fi

echo "[8/8] Starting HMI Flask Application with Gunicorn..."
echo ""
echo "Press CTRL+C to stop the server"
echo "Server will start on: http://0.0.0.0:6001"
echo ""

# Start with Gunicorn
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
