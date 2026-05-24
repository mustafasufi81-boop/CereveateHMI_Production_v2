#!/bin/bash
# ============================================================================
# HMI Flask Application - Linux Development/Testing Script
# Starts the app in development mode for local testing
# ============================================================================

set -e

echo "============================================================================"
echo "HMI Flask Application - Development Server"
echo "============================================================================"
echo ""

cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --upgrade

# Set environment to development
export HMI_ENV=development
export DEBUG=True

# Create .env if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
fi

# Create logs directory
mkdir -p logs

echo ""
echo "============================================================================"
echo "Starting Development Server on http://localhost:6001"
echo "Press CTRL+C to stop"
echo "============================================================================"
echo ""

# Start in development mode using original app.py
python app.py
