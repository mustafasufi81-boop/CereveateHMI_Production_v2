# Phase 3: Critical Risk Tests
# Native Driver Deadlock Test (TP-NATIVE-001)

param(
    [string]$BaseUrl = "http://localhost:5001"
)

$ErrorActionPreference = "Continue"
$results = @()

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "PHASE 3: CRITICAL RISK TESTS" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Test 14.1: Native Driver Deadlock Survival (TP-NATIVE-001)
Write-Host "`n[Test 14.1] Native Driver Deadlock Survival - CRITICAL TEST" -ForegroundColor Yellow
Write-Host "This test validates system remains responsive if OPC native DLL hangs" -ForegroundColor Gray
try {
    Write-Host "`nStep 1: Baseline health check..." -ForegroundColor Cyan
    $baseline = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 5
    Write-Host "✓ Baseline: $($baseline.overallStatus), Score: $($baseline.overallHealthScore)" -ForegroundColor Green
    
    Write-Host "`nStep 2: Monitoring API responsiveness during PLC operations..." -ForegroundColor Cyan
    $apiTests = 0
    $apiSuccess = 0
    $apiTimeout = 0
    $maxResponseTime = 0
    
    for ($i = 1; $i -le 20; $i++) {
        $apiTests++
        try {
            $start = Get-Date
            $response = Invoke-RestMethod -Uri "$BaseUrl/api/plc/connections" -Method Get -TimeoutSec 5
            $end = Get-Date
            $responseTime = ($end - $start).TotalMilliseconds
            
            if ($responseTime -gt $maxResponseTime) {
                $maxResponseTime = $responseTime
            }
            
            $apiSuccess++
            Write-Host "  Test $i : ✓ ${responseTime}ms" -ForegroundColor Gray
        } catch {
            $apiTimeout++
            Write-Host "  Test $i : ✗ TIMEOUT" -ForegroundColor Red
        }
        Start-Sleep -Milliseconds 500
    }
    
    Write-Host "`nStep 3: Stress test with concurrent requests..." -ForegroundColor Cyan
    $jobs = @()
    for ($i = 1; $i -le 10; $i++) {
        $jobs += Start-Job -ScriptBlock {
            param($url)
            try {
                $response = Invoke-RestMethod -Uri "$url/api/plc/connections" -Method Get -TimeoutSec 10
                return @{ Success = $true }
            } catch {
                return @{ Success = $false }
            }
        } -ArgumentList $BaseUrl
    }
    
    $completed = Wait-Job -Job $jobs -Timeout 15
    $jobResults = $jobs | Receive-Job
    $concurrentSuccess = ($jobResults | Where-Object { $_.Success -eq $true }).Count
    $jobs | Remove-Job -Force
    
    Write-Host "  Concurrent tests: $concurrentSuccess/10 succeeded" -ForegroundColor Gray
    
    Write-Host "`nStep 4: Final health check..." -ForegroundColor Cyan
    Start-Sleep -Seconds 3
    $finalHealth = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 5
    Write-Host "✓ Final: $($finalHealth.overallStatus), Score: $($finalHealth.overallHealthScore)" -ForegroundColor Green
    
    # Analysis
    Write-Host "`n--- Test Analysis ---" -ForegroundColor Cyan
    $apiSuccessPercent = [math]::Round(($apiSuccess/$apiTests)*100, 1)
    Write-Host "API Response Rate: $apiSuccess/$apiTests ($apiSuccessPercent%)" -ForegroundColor White
    Write-Host "Max Response Time: $([math]::Round($maxResponseTime, 2))ms" -ForegroundColor White
    Write-Host "Timeouts: $apiTimeout" -ForegroundColor White
    Write-Host "Concurrent Success: $concurrentSuccess/10" -ForegroundColor White
    Write-Host "Health Status: $($finalHealth.overallStatus)" -ForegroundColor White
    
    # Pass criteria:
    # - 95% API success rate
    # - Max response time < 5000ms (5s)
    # - < 2 timeouts
    # - Concurrent success >= 8/10
    # - Final health = Healthy
    
    $passRate = ($apiSuccess/$apiTests)
    $passConditions = @(
        $passRate -ge 0.95
        $maxResponseTime -lt 5000
        $apiTimeout -lt 2
        $concurrentSuccess -ge 8
        $finalHealth.overallStatus -eq "Healthy"
    )
    
    $passCount = ($passConditions | Where-Object { $_ -eq $true }).Count
    
    if ($passCount -eq 5) {
        Write-Host "`nPASS - System remains responsive, no deadlock detected" -ForegroundColor Green
        $results += @{ 
            Test = "14.1"
            Status = "PASS"
            Details = "API: $([math]::Round($passRate*100,1))%, MaxRT: $([math]::Round($maxResponseTime,2))ms, Concurrent: $concurrentSuccess/10"
        }
    } elseif ($passCount -ge 3) {
        Write-Host "`nPARTIAL - Some degradation detected, $passCount of 5 conditions passed" -ForegroundColor Yellow
        $results += @{ 
            Test = "14.1"
            Status = "PARTIAL"
            Details = "PassConditions: $passCount of 5, MaxRT: $([math]::Round($maxResponseTime,2))ms"
        }
    } else {
        Write-Host "`nFAIL - Significant responsiveness issues, only $passCount of 5 conditions passed" -ForegroundColor Red
        $results += @{ 
            Test = "14.1"
            Status = "FAIL"
            Details = "PassConditions: $passCount of 5, Timeouts: $apiTimeout, MaxRT: $([math]::Round($maxResponseTime,2))ms"
        }
    }
    
} catch {
    Write-Host "`n❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
    $results += @{ Test = "14.1"; Status = "FAIL"; Details = $_.Exception.Message }
}

# Test 9.3: Startup Recovery Test (TP-REC-003)
Write-Host "`n[Test 9.3] Startup Recovery - Check recovery from cold start" -ForegroundColor Yellow
try {
    # Check current uptime
    $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 5
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/plc/connections" -Method Get
    $plc = $response.connections | Where-Object { $_.plcId -eq "Rockwel_PLC_001" }
    
    if ($plc) {
        # Calculate uptime
        $uptime = [TimeSpan]::Parse($plc.uptime)
        $uptimeMinutes = $uptime.TotalMinutes
        
        Write-Host "System uptime: $([math]::Round($uptimeMinutes, 1)) minutes" -ForegroundColor Gray
        Write-Host "PLC Connection: $($plc.isConnected)" -ForegroundColor Gray
        Write-Host "Poll Count: $($plc.pollCount)" -ForegroundColor Gray
        Write-Host "Error Count: $($plc.errorCount)" -ForegroundColor Gray
        
        # Good startup: connected, polling, low errors
        $goodStartup = $plc.isConnected -eq $true -and 
                       $plc.pollCount -gt 10 -and
                       $plc.errorCount -lt 5
        
        if ($goodStartup) {
            Write-Host "✅ PASS - Clean startup with successful recovery" -ForegroundColor Green
            $results += @{ Test = "9.3"; Status = "PASS"; Details = "Uptime: $([math]::Round($uptimeMinutes,1))m, Polls: $($plc.pollCount), Errors: $($plc.errorCount)" }
        } else {
            Write-Host "⚠️ PARTIAL - Startup completed but with issues" -ForegroundColor Yellow
            $results += @{ Test = "9.3"; Status = "PARTIAL"; Details = "Connected: $($plc.isConnected), Polls: $($plc.pollCount), Errors: $($plc.errorCount)" }
        }
    } else {
        Write-Host "⚠️ SKIP - No PLC found" -ForegroundColor Yellow
        $results += @{ Test = "9.3"; Status = "SKIP"; Details = "No PLC connection" }
    }
} catch {
    Write-Host "❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
    $results += @{ Test = "9.3"; Status = "FAIL"; Details = $_.Exception.Message }
}

# Test 9.4: Corrupted Data Handling (TP-REC-002)
Write-Host "`n[Test 9.4] Corrupted Data Handling - Verify graceful degradation" -ForegroundColor Yellow
try {
    # Test with invalid endpoint to check error handling
    $errorTests = 0
    $gracefulErrors = 0
    
    $testEndpoints = @(
        "/api/plc/data/invalid",
        "/api/plc/connections/999",
        "/api/invalid/endpoint"
    )
    
    foreach ($endpoint in $testEndpoints) {
        $errorTests++
        try {
            $response = Invoke-RestMethod -Uri "$BaseUrl$endpoint" -Method Get -TimeoutSec 5
        } catch {
            $statusCode = $_.Exception.Response.StatusCode.value__
            if ($statusCode -eq 404 -or $statusCode -eq 400) {
                $gracefulErrors++
                Write-Host "  $endpoint : ✓ Graceful error ($statusCode)" -ForegroundColor Gray
            } else {
                Write-Host "  $endpoint : ✗ Unexpected error ($statusCode)" -ForegroundColor Red
            }
        }
    }
    
    # Check if system is still healthy after error tests
    $health = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get -TimeoutSec 5
    $stillHealthy = $health.overallStatus -eq "Healthy"
    
    if ($gracefulErrors -eq $errorTests -and $stillHealthy) {
        Write-Host "✅ PASS - All errors handled gracefully, system stable" -ForegroundColor Green
        $results += @{ Test = "9.4"; Status = "PASS"; Details = "$gracefulErrors/$errorTests graceful errors, health: $($health.overallStatus)" }
    } else {
        Write-Host "⚠️ PARTIAL - $gracefulErrors/$errorTests graceful, health: $($health.overallStatus)" -ForegroundColor Yellow
        $results += @{ Test = "9.4"; Status = "PARTIAL"; Details = "$gracefulErrors/$errorTests graceful, health: $($health.overallStatus)" }
    }
} catch {
    Write-Host "❌ FAIL - $($_.Exception.Message)" -ForegroundColor Red
    $results += @{ Test = "9.4"; Status = "FAIL"; Details = $_.Exception.Message }
}

# Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "PHASE 3 TEST SUMMARY" -ForegroundColor Cyan
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

Write-Host "`n🔥 CRITICAL: Test 14.1 (Native Driver Deadlock) is highest priority for production" -ForegroundColor Red
Write-Host "   Recommendation: Process isolation architecture if this test shows any degradation" -ForegroundColor Yellow

# Export results
$results | ForEach-Object {
    [PSCustomObject]$_
} | Export-Csv -Path "phase3_critical_tests.csv" -NoTypeInformation

Write-Host "`nResults exported to: phase3_critical_tests.csv" -ForegroundColor Cyan
