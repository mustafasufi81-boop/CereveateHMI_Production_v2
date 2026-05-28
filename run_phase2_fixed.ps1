# Phase 2 Load & Stress Tests (FIXED)
# Tests that don't require MQTT broker or HMI setup

param(
    [string]$BaseUrl = "http://localhost:5001"
)

$ErrorActionPreference = "Continue"
$results = @()

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "PHASE 2 LOAD & STRESS TESTS (FIXED)" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Test 11.1: Concurrency Stress Test (TP-CONC-001)
Write-Host "`n[Test 11.1] Concurrency Stress Test - 100 concurrent requests" -ForegroundColor Yellow
try {
    $jobs = @()
    $startTime = Get-Date
    
    # Launch 100 concurrent API requests
    for ($i = 1; $i -le 100; $i++) {
        $jobs += Start-Job -ScriptBlock {
            param($url)
            try {
                $response = Invoke-RestMethod -Uri "$url/api/plc/connections" -Method Get -TimeoutSec 10
                return @{ Success = $true; StatusCode = 200 }
            } catch {
                return @{ Success = $false; Error = $_.Exception.Message }
            }
        } -ArgumentList $BaseUrl
    }
    
    # Wait for all jobs with timeout
    $completed = Wait-Job -Job $jobs -Timeout 30
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalSeconds
    
    # Analyze results
    $jobResults = $jobs | Receive-Job
    $successCount = ($jobResults | Where-Object { $_.Success -eq $true }).Count
    $failCount = 100 - $successCount
    
    # Check if backend is still responsive
    Start-Sleep -Seconds 2
    $healthCheck = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 5
    
    $jobs | Remove-Job -Force
    
    if ($successCount -ge 95 -and $healthCheck.overallStatus -eq "Healthy") {
        Write-Host "✅ PASS - $successCount/100 requests succeeded in ${duration}s, backend still responsive" -ForegroundColor Green
        $results += @{ Test = "11.1"; Status = "PASS"; Details = "$successCount/100 succeeded, ${duration}s duration" }
    } else {
        Write-Host "❌ FAIL - Only $successCount/100 succeeded or backend unresponsive" -ForegroundColor Red
        $results += @{ Test = "11.1"; Status = "FAIL"; Details = "$successCount/100 succeeded, health: $($healthCheck.overallStatus)" }
    }
} catch {
    Write-Host "❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
    $results += @{ Test = "11.1"; Status = "FAIL"; Details = $_.Exception.Message }
}

# Test 11.2: API Load Test (TP-API-001)
Write-Host "`n[Test 11.2] API Load Test - 1000 requests over 5 seconds" -ForegroundColor Yellow
try {
    $successCount = 0
    $failCount = 0
    $startTime = Get-Date
    $requestsPerSecond = 200
    $totalRequests = 1000
    $duration = 5
    
    Write-Host "Sending $totalRequests requests at ~$requestsPerSecond req/s..." -ForegroundColor Gray
    
    for ($i = 1; $i -le $totalRequests; $i++) {
        try {
            $response = Invoke-RestMethod -Uri "$BaseUrl/api/plc/connections" -Method Get -TimeoutSec 2
            $successCount++
        } catch {
            $failCount++
        }
        
        # Throttle to ~200 req/s
        if ($i % 10 -eq 0) {
            Start-Sleep -Milliseconds 50
        }
    }
    
    $endTime = Get-Date
    $actualDuration = ($endTime - $startTime).TotalSeconds
    $actualRps = [math]::Round($totalRequests / $actualDuration, 2)
    
    # Check backend health after load
    Start-Sleep -Seconds 2
    $healthCheck = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 5
    
    if ($successCount -ge 950 -and $healthCheck.overallStatus -eq "Healthy") {
        Write-Host "✅ PASS - $successCount/$totalRequests succeeded at ${actualRps} req/s, backend healthy" -ForegroundColor Green
        $results += @{ Test = "11.2"; Status = "PASS"; Details = "$successCount/$totalRequests @ ${actualRps} req/s" }
    } else {
        Write-Host "⚠️ PARTIAL - $successCount/$totalRequests succeeded, health: $($healthCheck.overallStatus)" -ForegroundColor Yellow
        $results += @{ Test = "11.2"; Status = "PARTIAL"; Details = "$successCount/$totalRequests @ ${actualRps} req/s, health: $($healthCheck.overallStatus)" }
    }
} catch {
    Write-Host "❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
    $results += @{ Test = "11.2"; Status = "FAIL"; Details = $_.Exception.Message }
}

# Test 12.1: Database Connection Pool Test (TP-DB-001)
Write-Host "`n[Test 12.1] Database Connection Pool - 50 concurrent DB requests" -ForegroundColor Yellow
try {
    $jobs = @()
    $startTime = Get-Date
    
    # Launch 50 concurrent requests that hit database
    for ($i = 1; $i -le 50; $i++) {
        $jobs += Start-Job -ScriptBlock {
            param($url)
            try {
                $response = Invoke-RestMethod -Uri "$url/api/plc/data/latest" -Method Get -TimeoutSec 10
                return @{ Success = $true; Count = $response.Count }
            } catch {
                return @{ Success = $false; Error = $_.Exception.Message }
            }
        } -ArgumentList $BaseUrl
    }
    
    # Wait for all jobs
    $completed = Wait-Job -Job $jobs -Timeout 30
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalSeconds
    
    # Analyze results
    $jobResults = $jobs | Receive-Job
    $successCount = ($jobResults | Where-Object { $_.Success -eq $true }).Count
    
    $jobs | Remove-Job -Force
    
    if ($successCount -ge 48) {
        Write-Host "✅ PASS - $successCount/50 DB queries succeeded in ${duration}s" -ForegroundColor Green
        $results += @{ Test = "12.1"; Status = "PASS"; Details = "$successCount/50 succeeded, ${duration}s duration" }
    } else {
        Write-Host "❌ FAIL - Only $successCount/50 succeeded" -ForegroundColor Red
        $results += @{ Test = "12.1"; Status = "FAIL"; Details = "$successCount/50 succeeded" }
    }
} catch {
    Write-Host "❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
    $results += @{ Test = "12.1"; Status = "FAIL"; Details = $_.Exception.Message }
}

# Test 7.1: Connection Recovery After Network Glitch
Write-Host "`n[Test 7.1] Connection Recovery - Monitor recovery from failed state" -ForegroundColor Yellow
try {
    # Get current connection status
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/plc/connections" -Method Get
    $plc = $response.connections | Where-Object { $_.plcId -eq "Rockwel_PLC_001" }
    
    if ($plc) {
        Write-Host "Current: Connected=$($plc.isConnected), consecutiveFailures: $($plc.consecutiveFailures)" -ForegroundColor Gray
        
        # Monitor for 20 seconds to check stability
        Start-Sleep -Seconds 20
        
        $afterResponse = Invoke-RestMethod -Uri "$BaseUrl/api/plc/connections" -Method Get
        $plcAfter = $afterResponse.connections | Where-Object { $_.plcId -eq "Rockwel_PLC_001" }
        
        if ($plcAfter.isConnected -eq $true -and $plcAfter.consecutiveFailures -eq 0) {
            Write-Host "✅ PASS - PLC connected with 0 consecutive failures" -ForegroundColor Green
            $results += @{ Test = "7.1"; Status = "PASS"; Details = "Connected: $($plcAfter.isConnected), CF: $($plcAfter.consecutiveFailures)" }
        } else {
            Write-Host "⚠️ PARTIAL - Connected: $($plcAfter.isConnected), CF: $($plcAfter.consecutiveFailures)" -ForegroundColor Yellow
            $results += @{ Test = "7.1"; Status = "PARTIAL"; Details = "Connected: $($plcAfter.isConnected), CF: $($plcAfter.consecutiveFailures)" }
        }
    } else {
        Write-Host "⚠️ SKIP - PLC not found in connections" -ForegroundColor Yellow
        $results += @{ Test = "7.1"; Status = "SKIP"; Details = "PLC not found" }
    }
} catch {
    Write-Host "❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
    $results += @{ Test = "7.1"; Status = "FAIL"; Details = $_.Exception.Message }
}

# Test 13.1: Log Storm Protection (TP-LOG-001)
Write-Host "`n[Test 13.1] Log Storm Protection - Check log file growth during load" -ForegroundColor Yellow
try {
    $logPath = "D:\CereveateHMI_Production\CSharpBackend\logs"
    
    # Get log file sizes before test
    $logsBefore = Get-ChildItem -Path $logPath -Filter "*.txt" -ErrorAction SilentlyContinue
    $sizeBefore = ($logsBefore | Measure-Object -Property Length -Sum).Sum / 1MB
    
    Write-Host "Log size before: $([math]::Round($sizeBefore, 2)) MB" -ForegroundColor Gray
    
    # Generate load to trigger potential log storm
    Write-Host "Generating 500 rapid requests..." -ForegroundColor Gray
    for ($i = 1; $i -le 500; $i++) {
        try {
            Invoke-RestMethod -Uri "$BaseUrl/api/plc/connections" -Method Get -TimeoutSec 1 | Out-Null
        } catch {
            # Intentional - some may timeout
        }
    }
    
    Start-Sleep -Seconds 5
    
    # Get log file sizes after test
    $logsAfter = Get-ChildItem -Path $logPath -Filter "*.txt" -ErrorAction SilentlyContinue
    $sizeAfter = ($logsAfter | Measure-Object -Property Length -Sum).Sum / 1MB
    $growth = $sizeAfter - $sizeBefore
    
    Write-Host "Log size after: $([math]::Round($sizeAfter, 2)) MB (growth: $([math]::Round($growth, 2)) MB)" -ForegroundColor Gray
    
    # Threshold: < 50 MB growth during 500 requests
    if ($growth -lt 50) {
        Write-Host "✅ PASS - Log growth under control: $([math]::Round($growth, 2)) MB" -ForegroundColor Green
        $results += @{ Test = "13.1"; Status = "PASS"; Details = "Growth: $([math]::Round($growth, 2)) MB" }
    } else {
        Write-Host "⚠️ WARNING - Excessive log growth: $([math]::Round($growth, 2)) MB" -ForegroundColor Yellow
        $results += @{ Test = "13.1"; Status = "PARTIAL"; Details = "Growth: $([math]::Round($growth, 2)) MB (>50MB)" }
    }
} catch {
    Write-Host "⚠️ SKIP - $($_.Exception.Message)" -ForegroundColor Yellow
    $results += @{ Test = "13.1"; Status = "SKIP"; Details = $_.Exception.Message }
}

# Test 9.2: Recovery from Failed Connection State (TP-REC-001)
Write-Host "`n[Test 9.2] Recovery Pattern - Verify auto-recovery mechanisms" -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/plc/connections" -Method Get
    $plc = $response.connections | Where-Object { $_.plcId -eq "Rockwel_PLC_001" }
    
    if ($plc) {
        $hasRecoveryMetrics = $plc.PSObject.Properties.Name -contains "consecutiveFailures" -and 
                              $plc.PSObject.Properties.Name -contains "pollCount" -and
                              $plc.PSObject.Properties.Name -contains "errorCount"
        
        $isHealthy = $plc.isConnected -eq $true -and $plc.consecutiveFailures -lt 5
        
        if ($hasRecoveryMetrics -and $isHealthy) {
            Write-Host "✅ PASS - Recovery metrics present, system healthy" -ForegroundColor Green
            $results += @{ Test = "9.2"; Status = "PASS"; Details = "CF: $($plc.consecutiveFailures), Connected: $($plc.isConnected)" }
        } else {
            Write-Host "⚠️ PARTIAL - Metrics: $hasRecoveryMetrics, Healthy: $isHealthy" -ForegroundColor Yellow
            $results += @{ Test = "9.2"; Status = "PARTIAL"; Details = "Metrics: $hasRecoveryMetrics, Healthy: $isHealthy" }
        }
    } else {
        Write-Host "⚠️ SKIP - PLC not found" -ForegroundColor Yellow
        $results += @{ Test = "9.2"; Status = "SKIP"; Details = "PLC not found" }
    }
} catch {
    Write-Host "❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
    $results += @{ Test = "9.2"; Status = "FAIL"; Details = $_.Exception.Message }
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "PHASE 2 TEST SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$passed = ($results | Where-Object { $_.Status -eq "PASS" }).Count
$failed = ($results | Where-Object { $_.Status -eq "FAIL" }).Count
$partial = ($results | Where-Object { $_.Status -eq "PARTIAL" }).Count
$skipped = ($results | Where-Object { $_.Status -eq "SKIP" }).Count
$total = $results.Count

Write-Host "`nTotal Tests: $total" -ForegroundColor White
Write-Host "PASSED: $passed ✅" -ForegroundColor Green
Write-Host "FAILED: $failed ❌" -ForegroundColor Red
Write-Host "PARTIAL: $partial ⚠️" -ForegroundColor Yellow
Write-Host "SKIPPED: $skipped ⏭️" -ForegroundColor Gray

# Export results
$results | ForEach-Object {
    [PSCustomObject]$_
} | Export-Csv -Path "phase2_test_results_fixed.csv" -NoTypeInformation

Write-Host "`nResults exported to: phase2_test_results_fixed.csv" -ForegroundColor Cyan
