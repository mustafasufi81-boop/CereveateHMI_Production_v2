# ============================================================================
# Check Status of All HMI Services (PowerShell)
# Checks: Nginx (Frontend Proxy) + Flask Backend (Waitress)
# ============================================================================

Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "HMI Services Status Check" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

# Change to script directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

$allRunning = $true

# ============================================================================
# CHECK 1: Flask Backend (Port 6001)
# ============================================================================
Write-Host "[1/2] Flask Backend Status (Port 6001)" -ForegroundColor Yellow
Write-Host "-----------------------------------------------"

$backendConnection = Get-NetTCPConnection -LocalPort 6001 -State Listen -ErrorAction SilentlyContinue
if ($backendConnection) {
    Write-Host "Status: " -NoNewline
    Write-Host "[RUNNING]" -ForegroundColor Green
    Write-Host ""
    Write-Host "Details:"
    Write-Host "  - Local Address: $($backendConnection.LocalAddress):$($backendConnection.LocalPort)"
    Write-Host "  - Process ID: $($backendConnection.OwningProcess)"
    
    # Get process details
    $process = Get-Process -Id $backendConnection.OwningProcess -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "  - Process Name: $($process.ProcessName)"
        Write-Host "  - Memory Usage: $([math]::Round($process.WorkingSet64/1MB, 2)) MB"
    }
    Write-Host ""
    
    # Check if service is responding
    Write-Host "Testing backend connectivity..."
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:6001/api/system/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
        Write-Host "  HTTP Status: $($response.StatusCode)" -ForegroundColor Green
    } catch {
        Write-Host "  [INFO] Health check endpoint not responding" -ForegroundColor Gray
        Write-Host "         (This is normal if /api/system/health is not implemented)" -ForegroundColor Gray
    }
} else {
    Write-Host "Status: " -NoNewline
    Write-Host "[STOPPED]" -ForegroundColor Red
    Write-Host ""
    Write-Host "[WARNING] Flask backend is not running!" -ForegroundColor Yellow
    $allRunning = $false
}

Write-Host ""

# ============================================================================
# CHECK 2: Nginx (Port 8080 & 8443)
# ============================================================================
Write-Host "[2/2] Nginx Status (Ports 8080, 8443)" -ForegroundColor Yellow
Write-Host "-----------------------------------------------"

$nginxProcess = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
if ($nginxProcess) {
    Write-Host "Status: " -NoNewline
    Write-Host "[RUNNING]" -ForegroundColor Green
    Write-Host ""
    Write-Host "Details:"
    foreach ($proc in $nginxProcess) {
        Write-Host "  - Process ID: $($proc.Id)"
        Write-Host "  - Memory Usage: $([math]::Round($proc.WorkingSet64/1MB, 2)) MB"
    }
    Write-Host ""
    
    # Check HTTP port 8080
    $port8080 = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
    if ($port8080) {
        Write-Host "  - HTTP Port 8080: " -NoNewline
        Write-Host "[LISTENING]" -ForegroundColor Green
    } else {
        Write-Host "  - HTTP Port 8080: " -NoNewline
        Write-Host "[NOT LISTENING]" -ForegroundColor Yellow
    }
    
    # Check HTTPS port 8443
    $port8443 = Get-NetTCPConnection -LocalPort 8443 -State Listen -ErrorAction SilentlyContinue
    if ($port8443) {
        Write-Host "  - HTTPS Port 8443: " -NoNewline
        Write-Host "[LISTENING]" -ForegroundColor Green
    } else {
        Write-Host "  - HTTPS Port 8443: " -NoNewline
        Write-Host "[NOT LISTENING]" -ForegroundColor Yellow
    }
    
    Write-Host ""
    
    # Test nginx connectivity
    Write-Host "Testing nginx connectivity..."
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8080" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        Write-Host "  HTTP Status: $($response.StatusCode)" -ForegroundColor Green
    } catch {
        Write-Host "  [INFO] Nginx is running but not responding on port 8080" -ForegroundColor Gray
        Write-Host "         Error: $($_.Exception.Message)" -ForegroundColor Gray
    }
} else {
    Write-Host "Status: " -NoNewline
    Write-Host "[STOPPED]" -ForegroundColor Red
    Write-Host ""
    Write-Host "[WARNING] Nginx is not running!" -ForegroundColor Yellow
    $allRunning = $false
}

Write-Host ""

# ============================================================================
# SUMMARY
# ============================================================================
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

if ($allRunning) {
    Write-Host "[SUCCESS] All services are running!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Access Points:"
    Write-Host "  - HMI UI (HTTP):   " -NoNewline
    Write-Host "http://localhost:8080" -ForegroundColor Cyan
    Write-Host "  - HMI UI (HTTPS):  " -NoNewline
    Write-Host "https://localhost:8443" -ForegroundColor Cyan
    Write-Host "  - Backend API:     " -NoNewline
    Write-Host "http://localhost:6001/api/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Service Management:"
    Write-Host "  - Stop:    .\stop_all_services.ps1"
    Write-Host "  - Restart: .\restart_all_services.ps1"
    Write-Host ""
} else {
    Write-Host "[WARNING] Some services are not running!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To start all services: .\start_all_services.ps1"
    Write-Host ""
}

# ============================================================================
# ADDITIONAL DIAGNOSTICS
# ============================================================================
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Recent Log Files" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path "logs\waitress.log") {
    Write-Host "Flask Backend Log (last 5 lines):" -ForegroundColor Yellow
    Write-Host "-----------------------------------------------"
    Get-Content "logs\waitress.log" -Tail 5 -ErrorAction SilentlyContinue
    Write-Host ""
} else {
    Write-Host "[INFO] No Flask backend log found: logs\waitress.log" -ForegroundColor Gray
    Write-Host ""
}

if (Test-Path "nginx-1.28.0\logs\error.log") {
    Write-Host "Nginx Error Log (last 5 lines):" -ForegroundColor Yellow
    Write-Host "-----------------------------------------------"
    Get-Content "nginx-1.28.0\logs\error.log" -Tail 5 -ErrorAction SilentlyContinue
    Write-Host ""
} else {
    Write-Host "[INFO] No Nginx error log found: nginx-1.28.0\logs\error.log" -ForegroundColor Gray
    Write-Host ""
}

Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Status Check Complete" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
