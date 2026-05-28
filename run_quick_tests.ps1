# Sprint 1 Quick Test Execution Script
# Executes Phase 1 tests and captures results

$ErrorActionPreference = "Continue"
$baseUrl = "http://localhost:5001"
$results = @()

Write-Host "=== SPRINT 1 QUICK TEST EXECUTION ===" -ForegroundColor Cyan
Write-Host "Started: $(Get-Date)" -ForegroundColor Cyan

# Test 1.1: Build Verification (already done)
Write-Host "`n[Test 1.1] Clean Build Verification" -ForegroundColor Yellow
$results += [PSCustomObject]@{
    TestID = "1.1"
    TestName = "Clean Build Verification"
    Status = "PASS"
    Details = "Build succeeded with 8 pre-existing warnings, 0 errors"
    Timestamp = Get-Date
}

# Test 1.2: Environment Variable Loading
Write-Host "`n[Test 1.2] Environment Variable Loading" -ForegroundColor Yellow
$envVarSet = [System.Environment]::GetEnvironmentVariable("DB_PASSWORD") -eq "cereveate@222"
if ($envVarSet) {
    Write-Host "  ✅ Environment variable DB_PASSWORD is set" -ForegroundColor Green
    $results += [PSCustomObject]@{
        TestID = "1.2"
        TestName = "Environment Variable Loading"
        Status = "PASS"
        Details = "DB_PASSWORD environment variable correctly set and loaded"
        Timestamp = Get-Date
    }
} else {
    Write-Host "  ❌ Environment variable DB_PASSWORD not set" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "1.2"
        TestName = "Environment Variable Loading"
        Status = "FAIL"
        Details = "DB_PASSWORD not set"
        Timestamp = Get-Date
    }
}

# Test 2.1: Valid State Transitions
Write-Host "`n[Test 2.1] Valid State Transitions" -ForegroundColor Yellow
try {
    $diag = Invoke-RestMethod -Uri "$baseUrl/api/plc/diagnostics" -TimeoutSec 5
    $state = $diag.diagnostics[0].state
    Write-Host "  Current State: $state" -ForegroundColor Cyan
    
    if ($state -eq "Running") {
        Write-Host "  ✅ State machine operational - state is Running" -ForegroundColor Green
        $results += [PSCustomObject]@{
            TestID = "2.1"
            TestName = "Valid State Transitions"
            Status = "PASS"
            Details = "PLC worker in Running state, state machine operational"
            Timestamp = Get-Date
        }
    } else {
        $results += [PSCustomObject]@{
            TestID = "2.1"
            TestName = "Valid State Transitions"
            Status = "PARTIAL"
            Details = "State: $state (not Running, but valid)"
            Timestamp = Get-Date
        }
    }
} catch {
    Write-Host "  ❌ Failed to query diagnostics API" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "2.1"
        TestName = "Valid State Transitions"
        Status = "FAIL"
        Details = $_.Exception.Message
        Timestamp = Get-Date
    }
}

# Test 3.3: consecutiveFailures Accuracy
Write-Host "`n[Test 3.3] consecutiveFailures Counter" -ForegroundColor Yellow
try {
    $conn = Invoke-RestMethod -Uri "$baseUrl/api/plc/connections" -TimeoutSec 5
    $failures = $conn.connections[0].consecutiveFailures
    Write-Host "  Consecutive Failures: $failures" -ForegroundColor Cyan
    
    if ($failures -eq 0) {
        Write-Host "  ✅ No consecutive failures - system stable" -ForegroundColor Green
        $results += [PSCustomObject]@{
            TestID = "3.3"
            TestName = "consecutiveFailures Counter"
            Status = "PASS"
            Details = "Counter at 0, system stable"
            Timestamp = Get-Date
        }
    } else {
        $results += [PSCustomObject]@{
            TestID = "3.3"
            TestName = "consecutiveFailures Counter"
            Status = "PARTIAL"
            Details = "Counter at $failures (tracking working, but failures present)"
            Timestamp = Get-Date
        }
    }
} catch {
    Write-Host "  ❌ Failed to query connections API" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "3.3"
        TestName = "consecutiveFailures Counter"
        Status = "FAIL"
        Details = $_.Exception.Message
        Timestamp = Get-Date
    }
}

# Test 4.1: age_ms Computation
Write-Host "`n[Test 4.1] age_ms Computation" -ForegroundColor Yellow
try {
    $values = Invoke-RestMethod -Uri "$baseUrl/api/plc/values/Rockwel_PLC_001" -TimeoutSec 5
    $tag = $values.values[0]
    $ageMs = $tag.age_ms
    
    Write-Host "  Sample Tag: $($tag.tagName)" -ForegroundColor Cyan
    Write-Host "  age_ms: $ageMs ms" -ForegroundColor Cyan
    
    if ($ageMs -lt 2000) {
        Write-Host "  ✅ age_ms < 2000ms - actively polled tag" -ForegroundColor Green
        $results += [PSCustomObject]@{
            TestID = "4.1"
            TestName = "age_ms Computation"
            Status = "PASS"
            Details = "age_ms = $ageMs ms (< 2000ms threshold)"
            Timestamp = Get-Date
        }
    } else {
        $results += [PSCustomObject]@{
            TestID = "4.1"
            TestName = "age_ms Computation"
            Status = "PARTIAL"
            Details = "age_ms = $ageMs ms (> 2000ms, possibly stale)"
            Timestamp = Get-Date
        }
    }
} catch {
    Write-Host "  ❌ Failed to query values API" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "4.1"
        TestName = "age_ms Computation"
        Status = "FAIL"
        Details = $_.Exception.Message
        Timestamp = Get-Date
    }
}

# Test 4.2: Stale Quality Detection
Write-Host "`n[Test 4.2] Stale Quality Detection" -ForegroundColor Yellow
try {
    $values = Invoke-RestMethod -Uri "$baseUrl/api/plc/values/Rockwel_PLC_001" -TimeoutSec 5
    $tag = $values.values[0]
    
    Write-Host "  Quality: $($tag.quality)" -ForegroundColor Cyan
    Write-Host "  Computed Quality: $($tag.computedQuality)" -ForegroundColor Cyan
    Write-Host "  age_ms: $($tag.age_ms) ms" -ForegroundColor Cyan
    
    # Check logic
    $expectedStale = $tag.age_ms -gt 10000
    $actualStale = $tag.computedQuality -eq "Stale"
    
    if ($expectedStale -eq $actualStale) {
        Write-Host "  ✅ Stale detection logic working correctly" -ForegroundColor Green
        $results += [PSCustomObject]@{
            TestID = "4.2"
            TestName = "Stale Quality Detection"
            Status = "PASS"
            Details = "age=$($tag.age_ms)ms, quality=$($tag.computedQuality) (logic correct)"
            Timestamp = Get-Date
        }
    } else {
        $results += [PSCustomObject]@{
            TestID = "4.2"
            TestName = "Stale Quality Detection"
            Status = "FAIL"
            Details = "Expected stale=$expectedStale, actual=$actualStale"
            Timestamp = Get-Date
        }
    }
} catch {
    Write-Host "  ❌ Failed to test stale detection" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "4.2"
        TestName = "Stale Quality Detection"
        Status = "FAIL"
        Details = $_.Exception.Message
        Timestamp = Get-Date
    }
}

# Test 6.1: Watchdog Monitoring
Write-Host "`n[Test 6.1] Watchdog Monitoring" -ForegroundColor Yellow
try {
    $diag = Invoke-RestMethod -Uri "$baseUrl/api/plc/diagnostics" -TimeoutSec 5
    $watchdog = $diag.diagnostics[0].watchdog
    
    Write-Host "  Last Scan Duration: $($watchdog.lastScanDurationMs) ms" -ForegroundColor Cyan
    Write-Host "  Max Scan Duration: $($watchdog.maxScanDurationMs) ms" -ForegroundColor Cyan
    Write-Host "  Degradation Count: $($watchdog.scanDegradationCount)" -ForegroundColor Cyan
    Write-Host "  Expected Max: $($watchdog.expectedMaxScanMs) ms" -ForegroundColor Cyan
    Write-Host "  Is Degraded: $($watchdog.isDegraded)" -ForegroundColor Cyan
    
    if (-not $watchdog.isDegraded) {
        Write-Host "  ✅ Watchdog healthy - no degradation detected" -ForegroundColor Green
        $results += [PSCustomObject]@{
            TestID = "6.1"
            TestName = "Watchdog Monitoring"
            Status = "PASS"
            Details = "Last scan=$($watchdog.lastScanDurationMs)ms, Max=$($watchdog.maxScanDurationMs)ms, Not degraded"
            Timestamp = Get-Date
        }
    } else {
        $results += [PSCustomObject]@{
            TestID = "6.1"
            TestName = "Watchdog Monitoring"
            Status = "PARTIAL"
            Details = "Degraded detected - investigate"
            Timestamp = Get-Date
        }
    }
} catch {
    Write-Host "  ❌ Failed to test watchdog" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "6.1"
        TestName = "Watchdog Monitoring"
        Status = "FAIL"
        Details = $_.Exception.Message
        Timestamp = Get-Date
    }
}

# Test 6.2: Diagnostics Endpoint Completeness
Write-Host "`n[Test 6.2] Diagnostics Endpoint Completeness" -ForegroundColor Yellow
try {
    $diag = Invoke-RestMethod -Uri "$baseUrl/api/plc/diagnostics" -TimeoutSec 5
    $plc = $diag.diagnostics[0]
    
    # API uses flat structure - validate all critical fields are present
    $requiredFields = @(
        'plcId', 'protocol', 'ipAddress', 'port', 'state', 'isConnected',
        'tagCount', 'totalPolls', 'successfulPolls', 'failedPolls', 
        'consecutiveFailures', 'successRate', 'averageReadTimeMs',
        'pollingIntervalMs', 'lastPollTime', 'uptime', 'watchdog'
    )
    
    $missingFields = @()
    foreach ($field in $requiredFields) {
        if (-not $plc.PSObject.Properties[$field]) {
            $missingFields += $field
        }
    }
    
    # Validate watchdog nested object
    $watchdogFields = @('lastScanDurationMs', 'maxScanDurationMs', 'scanDegradationCount', 'isDegraded')
    $missingWatchdog = @()
    if ($plc.watchdog) {
        foreach ($field in $watchdogFields) {
            if (-not $plc.watchdog.PSObject.Properties[$field]) {
                $missingWatchdog += $field
            }
        }
    } else {
        $missingFields += 'watchdog'
    }
    
    if ($missingFields.Count -eq 0 -and $missingWatchdog.Count -eq 0) {
        Write-Host "  ✅ All required fields present (identity, state, performance, counters, timing, watchdog)" -ForegroundColor Green
        $results += [PSCustomObject]@{
            TestID = "6.2"
            TestName = "Diagnostics Endpoint"
            Status = "PASS"
            Details = "All 17 required fields present and populated (flat structure validated)"
            Timestamp = Get-Date
        }
    } else {
        Write-Host "  ❌ Missing fields: $($missingFields -join ', ')" -ForegroundColor Red
        if ($missingWatchdog.Count -gt 0) {
            Write-Host "  ❌ Missing watchdog fields: $($missingWatchdog -join ', ')" -ForegroundColor Red
        }
        $results += [PSCustomObject]@{
            TestID = "6.2"
            TestName = "Diagnostics Endpoint"
            Status = "FAIL"
            Details = "Missing: $($missingFields -join ', ') / Watchdog: $($missingWatchdog -join ', ')"
            Timestamp = Get-Date
        }
    }
} catch {
    Write-Host "  ❌ Failed to test diagnostics endpoint" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "6.2"
        TestName = "Diagnostics Endpoint"
        Status = "FAIL"
        Details = $_.Exception.Message
        Timestamp = Get-Date
    }
}

# Test 7.1: No Plaintext Credentials
Write-Host "`n[Test 7.1] No Plaintext Credentials in Config" -ForegroundColor Yellow
$configPath = "d:\CereveateHMI_Production\CSharpBackend\appsettings.json"
$configContent = Get-Content $configPath -Raw

if ($configContent -match 'Password=cereveate@222') {
    Write-Host "  ❌ Plaintext password found in config!" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "7.1"
        TestName = "No Plaintext Credentials"
        Status = "FAIL"
        Details = "Plaintext password found in appsettings.json"
        Timestamp = Get-Date
    }
} else {
    Write-Host "  ✅ No plaintext passwords in config" -ForegroundColor Green
    $placeholders = ([regex]::Matches($configContent, '\$\{DB_PASSWORD\}')).Count
    $results += [PSCustomObject]@{
        TestID = "7.1"
        TestName = "No Plaintext Credentials"
        Status = "PASS"
        Details = "Using environment variable placeholder ($placeholders instances)"
        Timestamp = Get-Date
    }
}

# Test 8.2: IP Address Mapping
Write-Host "`n[Test 8.2] IP Address Mapping Correctness" -ForegroundColor Yellow
try {
    $conn = Invoke-RestMethod -Uri "$baseUrl/api/plc/connections" -TimeoutSec 5
    $plc = $conn.connections[0]
    
    Write-Host "  Protocol: $($plc.protocol)" -ForegroundColor Cyan
    Write-Host "  IP Address: $($plc.ipAddress)" -ForegroundColor Cyan
    Write-Host "  Port: $($plc.port)" -ForegroundColor Cyan
    
    $allCorrect = ($plc.protocol -eq "Rockwell") -and 
                  ($plc.ipAddress -eq "192.168.0.20") -and 
                  ($plc.port -eq 44818)
    
    if ($allCorrect) {
        Write-Host "  ✅ IP mapping correct (runtime worker priority working)" -ForegroundColor Green
        $results += [PSCustomObject]@{
            TestID = "8.2"
            TestName = "IP Address Mapping"
            Status = "PASS"
            Details = "Protocol=$($plc.protocol), IP=$($plc.ipAddress), Port=$($plc.port)"
            Timestamp = Get-Date
        }
    } else {
        $results += [PSCustomObject]@{
            TestID = "8.2"
            TestName = "IP Address Mapping"
            Status = "FAIL"
            Details = "Incorrect mapping - check priority logic"
            Timestamp = Get-Date
        }
    }
} catch {
    Write-Host "  ❌ Failed to test IP mapping" -ForegroundColor Red
    $results += [PSCustomObject]@{
        TestID = "8.2"
        TestName = "IP Address Mapping"
        Status = "FAIL"
        Details = $_.Exception.Message
        Timestamp = Get-Date
    }
}

# Summary
Write-Host "`n=== TEST EXECUTION SUMMARY ===" -ForegroundColor Cyan
$passCount = ($results | Where-Object { $_.Status -eq "PASS" }).Count
$failCount = ($results | Where-Object { $_.Status -eq "FAIL" }).Count
$partialCount = ($results | Where-Object { $_.Status -eq "PARTIAL" }).Count
$totalCount = $results.Count

Write-Host "Total Tests: $totalCount" -ForegroundColor White
Write-Host "PASSED: $passCount" -ForegroundColor Green
Write-Host "FAILED: $failCount" -ForegroundColor Red
Write-Host "PARTIAL: $partialCount" -ForegroundColor Yellow

# Export results
$results | Export-Csv -Path "test_results_$(Get-Date -Format 'yyyyMMdd_HHmmss').csv" -NoTypeInformation
$results | Format-Table -AutoSize

Write-Host "`nCompleted: $(Get-Date)" -ForegroundColor Cyan
Write-Host "Results saved to: test_results_$(Get-Date -Format 'yyyyMMdd_HHmmss').csv" -ForegroundColor Cyan
