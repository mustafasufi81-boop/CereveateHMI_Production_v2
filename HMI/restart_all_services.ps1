# ============================================================================
# Restart All HMI Services (PowerShell)
# Stops and restarts: Nginx + Flask Backend
# ============================================================================

Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Restarting All HMI Services" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

# Change to script directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# ============================================================================
# STEP 1: Stop All Services
# ============================================================================
Write-Host "[STEP 1] Stopping all services..." -ForegroundColor Yellow
Write-Host ""
& .\stop_all_services.ps1

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[WARNING] Some services may not have stopped cleanly" -ForegroundColor Yellow
    Write-Host "Continuing with restart..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "Waiting 5 seconds before restart..." -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Start-Sleep -Seconds 5

Write-Host ""

# ============================================================================
# STEP 2: Start All Services
# ============================================================================
Write-Host "[STEP 2] Starting all services..." -ForegroundColor Yellow
Write-Host ""
& .\start_all_services.ps1

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "============================================================================" -ForegroundColor Red
    Write-Host "ERROR: Failed to start services after restart" -ForegroundColor Red
    Write-Host "============================================================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Troubleshooting steps:"
    Write-Host "  1. Check if ports 6001, 8080, 8443 are free"
    Write-Host "  2. Review logs: logs\waitress.log and nginx-1.28.0\logs\error.log"
    Write-Host "  3. Try running .\stop_all_services.ps1 again"
    Write-Host "  4. Restart your computer if issues persist"
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Green
Write-Host "Restart Complete" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "All services have been restarted successfully!" -ForegroundColor Green
Write-Host "Check status with: .\status_all_services.ps1"
Write-Host ""
