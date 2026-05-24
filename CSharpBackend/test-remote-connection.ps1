# Test remote OPC server connection
$url = "http://localhost:6100"

Write-Host "Testing remote OPC connection to 172.16.160.16..." -ForegroundColor Cyan

# Install SignalR client if needed
# Install-Package Microsoft.AspNetCore.SignalR.Client

# Create a simple HTTP test using Invoke-WebRequest to simulate the connection
try {
    # Step 1: Test if server is running
    Write-Host "`n1. Testing server status..." -ForegroundColor Yellow
    $response = Invoke-WebRequest -Uri "$url" -Method GET -UseBasicParsing -TimeoutSec 5
    Write-Host "   Server is UP: $($response.StatusCode)" -ForegroundColor Green
    
    # Step 2: Try to get servers list
    Write-Host "`n2. Getting OPC servers list..." -ForegroundColor Yellow
    try {
        $servers = Invoke-RestMethod -Uri "$url/api/opc/servers" -Method GET -TimeoutSec 5
        Write-Host "   Available servers:" -ForegroundColor Green
        $servers | ForEach-Object { Write-Host "   - $_" }
    } catch {
        Write-Host "   API not available: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    
    # Step 3: Test connection using JavaScript in the browser (manual step required)
    Write-Host "`n3. To test the connection manually:" -ForegroundColor Yellow
    Write-Host "   a) Open browser: $url" -ForegroundColor White
    Write-Host "   b) Login: opcadmin / Cereveate@222" -ForegroundColor White
    Write-Host "   c) Remote Server tab" -ForegroundColor White
    Write-Host "   d) Hostname: 172.16.160.16" -ForegroundColor White
    Write-Host "   e) Server: MCS.OPCServer.1" -ForegroundColor White
    Write-Host "   f) Click Connect and Browse Tags" -ForegroundColor White
    
    Write-Host "`n4. Opening browser..." -ForegroundColor Yellow
    Start-Process "$url"
    
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
}
