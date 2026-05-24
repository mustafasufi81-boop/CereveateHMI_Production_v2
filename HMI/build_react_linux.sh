#!/bin/bash
# ============================================================================
# React Frontend - Production Build Script (Linux)
# Builds optimized production bundle for deployment
# ============================================================================

set -e

echo "============================================================================"
echo "React HMI Frontend - Production Build"
echo "============================================================================"
echo ""

cd "$(dirname "$0")/apex-hmi"

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed!"
    echo "Install with: sudo apt-get install nodejs npm"
    exit 1
fi

echo "[1/4] Node.js version:"
node --version

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "[ERROR] npm is not installed!"
    echo "Install with: sudo apt-get install npm"
    exit 1
fi

echo "[2/4] Installing dependencies..."
npm install

echo "[3/4] Building production bundle..."
npm run build

echo "[4/4] Build complete!"
echo ""
echo "============================================================================"
echo "Production build created in: apex-hmi/dist/"
echo "============================================================================"
echo ""
echo "Files created:"
ls -lh dist/
echo ""
echo "Next steps:"
echo "1. Deploy backend: cd ../HMI && ./deploy_linux.sh"
echo "2. Configure nginx to serve dist folder"
echo "3. Access app at: https://hmi.yourdomain.com"
echo "============================================================================"
