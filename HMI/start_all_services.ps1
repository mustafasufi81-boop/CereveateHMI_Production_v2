# ============================================================================
# Start All HMI Services (PowerShell)
# Starts: Nginx (Frontend Proxy) + Flask Backend (Waitress)
# ============================================================================

Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Starting All HMI Services" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

# Change to script directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Create logs directory if it doesn't exist
if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" | Out-Null
}

$allSuccess = $true

# ============================================================================
# STEP 1: Start Flask Backend (Waitress)
# ============================================================================
Write-Host "[1/2] Starting Flask Backend (Waitress on port 6001)..." -ForegroundColor Yellow
Write-Host ""

# Check if backend is already running
$backendRunning = Get-NetTCPConnection -LocalPort 6001 -ErrorAction SilentlyContinue
if ($backendRunning) {
    Write-Host "[WARNING] Port 6001 is already in use!" -ForegroundColor Yellow
    Write-Host "Flask backend may already be running." -ForegroundColor Yellow
    Write-Host ""
} else {
    # Check if virtual environment exists
    if (-not (Test-Path "venv\Scripts\activate.bat")) {
        Write-Host "[ERROR] Virtual environment not found!" -ForegroundColor Red
        Write-Host "Please run: python -m venv venv" -ForegroundColor Red
        Write-Host "Then run: venv\Scripts\pip install -r requirements-production.txt" -ForegroundColor Red
        exit 1
    }

    # Start Flask backend in background
    Write-Host "Starting Flask backend in background..."
    $backendProcess = Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c venv\Scripts\activate.bat && waitress-serve --host=0.0.0.0 --port=6001 --threads=6 --channel-timeout=120 --connection-limit=1000 wsgi:application > logs\waitress.log 2>&1" `
        -WindowStyle Hidden `
        -PassThru

    # Wait for backend to start
    Write-Host "Waiting for Flask backend to start..."
    Start-Sleep -Seconds 3

    # Verify backend started
    $backendRunning = Get-NetTCPConnection -LocalPort 6001 -ErrorAction SilentlyContinue
    if ($backendRunning) {
        Write-Host "[SUCCESS] Flask backend started on http://localhost:6001" -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Flask backend failed to start!" -ForegroundColor Red
        Write-Host "Check logs\waitress.log for details" -ForegroundColor Red
        $allSuccess = $false
    }
}

Write-Host ""

# ============================================================================
# STEP 2: Start Nginx (Frontend Proxy)
# ============================================================================
Write-Host "[2/2] Starting Nginx (Port 8080 HTTP, 8443 HTTPS)..." -ForegroundColor Yellow
Write-Host ""

# Check if local nginx exists
if (-not (Test-Path "nginx-1.28.0\nginx.exe")) {
    Write-Host "[ERROR] Nginx not found at nginx-1.28.0\nginx.exe" -ForegroundColor Red
    Write-Host "Please ensure nginx is installed in the HMI\nginx-1.28.0\ folder" -ForegroundColor Red
    exit 1
}

# Check if nginx is already running
$nginxProcess = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
if ($nginxProcess) {
    Write-Host "[WARNING] Nginx is already running!" -ForegroundColor Yellow
    Write-Host ""
} else {
    # Start nginx from local folder
    Set-Location "nginx-1.28.0"
    Start-Process -FilePath "nginx.exe" -WindowStyle Hidden
    Set-Location ".."

    # Wait for nginx to start
    Start-Sleep -Seconds 2

    # Verify nginx started
    $nginxProcess = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
    if ($nginxProcess) {
        Write-Host "[SUCCESS] Nginx started successfully" -ForegroundColor Green
        Write-Host ""
        Write-Host "Nginx is serving:"
        Write-Host "  HTTP:  http://localhost:8080" -ForegroundColor Cyan
        Write-Host "  HTTPS: https://localhost:8443" -ForegroundColor Cyan
    } else {
        Write-Host "[ERROR] Nginx failed to start!" -ForegroundColor Red
        Write-Host "Check nginx-1.28.0\logs\error.log for details" -ForegroundColor Red
        $allSuccess = $false
    }
}

Write-Host ""

# ============================================================================
# SUCCESS
# ============================================================================
if ($allSuccess) {
    Write-Host "============================================================================" -ForegroundColor Green
    Write-Host "All Services Started Successfully" -ForegroundColor Green
    Write-Host "============================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Services running:"
    Write-Host "  [1] Flask Backend:  http://localhost:6001" -ForegroundColor Cyan
    Write-Host "  [2] Nginx Proxy:    http://localhost:8080 (HTTP)" -ForegroundColor Cyan
    Write-Host "  [3] Nginx Proxy:    https://localhost:8443 (HTTPS)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Access your HMI at:"
    Write-Host "  HTTP:  http://localhost:8080" -ForegroundColor Green
    Write-Host "  HTTPS: https://localhost:8443" -ForegroundColor Green
    Write-Host ""
    Write-Host "Service Management:"
    Write-Host "  Stop:    .\stop_all_services.ps1"
    Write-Host "  Restart: .\restart_all_services.ps1"
    Write-Host "  Status:  .\status_all_services.ps1"
    Write-Host ""
} else {
    Write-Host "============================================================================" -ForegroundColor Red
    Write-Host "ERROR: Failed to start all services" -ForegroundColor Red
    Write-Host "============================================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Check the following:"
    Write-Host "  1. Virtual environment is set up: venv\Scripts\activate.bat"
    Write-Host "  2. Dependencies installed: pip install -r requirements-production.txt"
    Write-Host "  3. Nginx is present: nginx-1.28.0\nginx.exe"
    Write-Host "  4. Ports 6001, 8080, 8443 are not in use"
    Write-Host "  5. Check logs: logs\waitress.log and nginx-1.28.0\logs\error.log"
    Write-Host ""
    exit 1
}
