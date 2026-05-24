# ============================================================================
# Stop All HMI Services (PowerShell)
# Stops: Nginx (Frontend Proxy) + Flask Backend (Waitress)
# ============================================================================

Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Stopping All HMI Services" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

# Change to script directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# ============================================================================
# STEP 1: Stop Nginx
# ============================================================================
Write-Host "[1/2] Stopping Nginx..." -ForegroundColor Yellow

$nginxProcess = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
if ($nginxProcess) {
    # Try graceful shutdown first
    if (Test-Path "nginx-1.28.0\nginx.exe") {
        Write-Host "Attempting graceful shutdown..."
        Set-Location "nginx-1.28.0"
        & .\nginx.exe -s quit
        Set-Location ".."
        Start-Sleep -Seconds 2
    }
    
    # Force kill if still running
    $nginxProcess = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
    if ($nginxProcess) {
        Write-Host "Force stopping nginx..."
        Stop-Process -Name "nginx" -Force -ErrorAction SilentlyContinue
        Write-Host "[SUCCESS] Nginx stopped" -ForegroundColor Green
    } else {
        Write-Host "[SUCCESS] Nginx stopped gracefully" -ForegroundColor Green
    }
} else {
    Write-Host "[INFO] Nginx is not running" -ForegroundColor Gray
}

Write-Host ""

# ============================================================================
# STEP 2: Stop Flask Backend (Waitress)
# ============================================================================
Write-Host "[2/2] Stopping Flask Backend (Waitress)..." -ForegroundColor Yellow

# Find processes listening on port 6001
$backendConnection = Get-NetTCPConnection -LocalPort 6001 -ErrorAction SilentlyContinue
if ($backendConnection) {
    $processId = $backendConnection.OwningProcess | Select-Object -First 1
    Write-Host "Stopping process on port 6001 (PID: $processId)..."
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    
    if ($?) {
        Write-Host "[SUCCESS] Flask backend stopped (PID: $processId)" -ForegroundColor Green
    } else {
        Write-Host "[WARNING] Could not stop process PID: $processId" -ForegroundColor Yellow
    }
} else {
    Write-Host "[INFO] Flask backend is not running on port 6001" -ForegroundColor Gray
}

# Also kill any python processes that might be running flask/waitress
$pythonProcesses = Get-Process -Name "python" -ErrorAction SilentlyContinue
foreach ($proc in $pythonProcesses) {
    $connections = Get-NetTCPConnection -OwningProcess $proc.Id -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -eq 6001 }
    if ($connections) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Write-Host "[SUCCESS] Stopped Python process (PID: $($proc.Id))" -ForegroundColor Green
    }
}

Write-Host ""

# ============================================================================
# VERIFY SHUTDOWN
# ============================================================================
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Verifying All Services Stopped" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

$allStopped = $true

# Check Nginx
$nginxProcess = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
if ($nginxProcess) {
    Write-Host "[WARNING] Nginx is still running!" -ForegroundColor Yellow
    $allStopped = $false
} else {
    Write-Host "[OK] Nginx stopped" -ForegroundColor Green
}

# Check Flask Backend
$backendConnection = Get-NetTCPConnection -LocalPort 6001 -ErrorAction SilentlyContinue
if ($backendConnection) {
    Write-Host "[WARNING] Port 6001 is still in use!" -ForegroundColor Yellow
    $allStopped = $false
} else {
    Write-Host "[OK] Flask backend stopped" -ForegroundColor Green
}

Write-Host ""

if ($allStopped) {
    Write-Host "============================================================================" -ForegroundColor Green
    Write-Host "All Services Stopped Successfully" -ForegroundColor Green
    Write-Host "============================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "To start services: .\start_all_services.ps1"
    Write-Host ""
} else {
    Write-Host "============================================================================" -ForegroundColor Yellow
    Write-Host "WARNING: Some Services May Still Be Running" -ForegroundColor Yellow
    Write-Host "============================================================================" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Please check manually:"
    Write-Host "  Get-Process -Name nginx"
    Write-Host "  Get-NetTCPConnection -LocalPort 6001"
    Write-Host ""
    Write-Host "You may need to restart your computer if services won't stop."
    Write-Host ""
}
