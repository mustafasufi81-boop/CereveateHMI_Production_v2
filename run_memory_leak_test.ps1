# 12-Hour Memory Leak Test (TP-MEM-001)
# Simplified version using PowerShell performance counters

param(
    [int]$DurationHours = 12,
    [string]$ProcessName = "OpcDaWebBrowser",
    [int]$SampleIntervalSeconds = 300  # 5 minutes
)

$ErrorActionPreference = "Continue"
$startTime = Get-Date
$endTime = $startTime.AddHours($DurationHours)
$sampleCount = 0
$samples = @()

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "12-HOUR MEMORY LEAK TEST (TP-MEM-001)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Start Time: $startTime" -ForegroundColor White
Write-Host "End Time: $endTime" -ForegroundColor White
Write-Host "Sample Interval: $SampleIntervalSeconds seconds" -ForegroundColor White
Write-Host "Target Process: $ProcessName" -ForegroundColor White
Write-Host "" -ForegroundColor White

# Create log file
$logFile = "memory_leak_test_$(Get-Date -Format 'yyyyMMdd_HHmmss').csv"
"Timestamp,ElapsedHours,WorkingSetMB,PrivateBytesMB,ThreadCount,HandleCount,HealthStatus,HealthScore" | Out-File -FilePath $logFile

Write-Host "Logging to: $logFile" -ForegroundColor Cyan
Write-Host "" -ForegroundColor White
Write-Host "Starting continuous monitoring..." -ForegroundColor Yellow
Write-Host "(Press Ctrl+C to stop early)" -ForegroundColor Gray
Write-Host "" -ForegroundColor White

while ((Get-Date) -lt $endTime) {
    try {
        # Get process metrics
        $process = Get-Process -Name $ProcessName -ErrorAction Stop
        $workingSetMB = [math]::Round($process.WorkingSet64 / 1MB, 2)
        $privateBytesMB = [math]::Round($process.PrivateMemorySize64 / 1MB, 2)
        $threadCount = $process.Threads.Count
        $handleCount = $process.HandleCount
        
        # Get health status
        try {
            $health = Invoke-RestMethod -Uri "http://localhost:5001/api/health" -Method Get -TimeoutSec 5
            $healthStatus = $health.overallStatus
            $healthScore = $health.overallHealthScore
        } catch {
            $healthStatus = "Unknown"
            $healthScore = 0
        }
        
        # Calculate elapsed time
        $elapsed = (Get-Date) - $startTime
        $elapsedHours = [math]::Round($elapsed.TotalHours, 2)
        
        # Store sample
        $sample = [PSCustomObject]@{
            Timestamp = Get-Date
            ElapsedHours = $elapsedHours
            WorkingSetMB = $workingSetMB
            PrivateBytesMB = $privateBytesMB
            ThreadCount = $threadCount
            HandleCount = $handleCount
            HealthStatus = $healthStatus
            HealthScore = $healthScore
        }
        $samples += $sample
        $sampleCount++
        
        # Log to file
        "$($sample.Timestamp),$($sample.ElapsedHours),$($sample.WorkingSetMB),$($sample.PrivateBytesMB),$($sample.ThreadCount),$($sample.HandleCount),$($sample.HealthStatus),$($sample.HealthScore)" | Out-File -FilePath $logFile -Append
        
        # Display current status
        $remainingHours = [math]::Round(($endTime - (Get-Date)).TotalHours, 2)
        Write-Host "[Sample $sampleCount | $elapsedHours h elapsed | $remainingHours h remaining]" -ForegroundColor Cyan
        Write-Host "  Memory: $workingSetMB MB (WS) / $privateBytesMB MB (Private)" -ForegroundColor White
        Write-Host "  Threads: $threadCount | Handles: $handleCount" -ForegroundColor White
        Write-Host "  Health: $healthStatus ($healthScore)" -ForegroundColor White
        
        # Memory growth analysis (if we have enough samples)
        if ($sampleCount -ge 3) {
            $firstSample = $samples[0]
            $lastSample = $samples[-1]
            $memoryGrowth = $lastSample.PrivateBytesMB - $firstSample.PrivateBytesMB
            $hourlyGrowth = if ($elapsed.TotalHours -gt 0) { [math]::Round($memoryGrowth / $elapsed.TotalHours, 2) } else { 0 }
            
            Write-Host "  Growth: $memoryGrowth MB total | $hourlyGrowth MB/hour" -ForegroundColor $(if ($hourlyGrowth -gt 10) { "Yellow" } else { "Green" })
        }
        
        Write-Host "" -ForegroundColor White
        
        # Wait for next sample
        Start-Sleep -Seconds $SampleIntervalSeconds
        
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Process may have crashed or restarted. Waiting 30 seconds..." -ForegroundColor Yellow
        Start-Sleep -Seconds 30
    }
}

# Final Analysis
Write-Host "" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TEST COMPLETE - FINAL ANALYSIS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if ($samples.Count -ge 2) {
    $firstSample = $samples[0]
    $lastSample = $samples[-1]
    
    $totalMemoryGrowth = $lastSample.PrivateBytesMB - $firstSample.PrivateBytesMB
    $totalTime = $lastSample.ElapsedHours
    $hourlyGrowth = if ($totalTime -gt 0) { [math]::Round($totalMemoryGrowth / $totalTime, 2) } else { 0 }
    
    Write-Host "Total Samples: $sampleCount" -ForegroundColor White
    Write-Host "Test Duration: $totalTime hours" -ForegroundColor White
    Write-Host "" -ForegroundColor White
    Write-Host "Initial Memory: $($firstSample.PrivateBytesMB) MB" -ForegroundColor White
    Write-Host "Final Memory: $($lastSample.PrivateBytesMB) MB" -ForegroundColor White
    Write-Host "Total Growth: $totalMemoryGrowth MB" -ForegroundColor White
    Write-Host "Hourly Growth Rate: $hourlyGrowth MB/hour" -ForegroundColor White
    Write-Host "" -ForegroundColor White
    
    # Pass criteria: < 10 MB/hour growth
    if ($hourlyGrowth -lt 10) {
        Write-Host "PASS - Memory growth within acceptable limits" -ForegroundColor Green
        Write-Host "System is production-ready from memory leak perspective" -ForegroundColor Green
    } elseif ($hourlyGrowth -lt 20) {
        Write-Host "WARNING - Moderate memory growth detected" -ForegroundColor Yellow
        Write-Host "Consider investigating potential small leaks" -ForegroundColor Yellow
    } else {
        Write-Host "FAIL - Significant memory leak detected" -ForegroundColor Red
        Write-Host "Memory leak must be fixed before production deployment" -ForegroundColor Red
    }
    
    Write-Host "" -ForegroundColor White
    Write-Host "Thread Growth: $($firstSample.ThreadCount) -> $($lastSample.ThreadCount) ($($lastSample.ThreadCount - $firstSample.ThreadCount) change)" -ForegroundColor White
    Write-Host "Handle Growth: $($firstSample.HandleCount) -> $($lastSample.HandleCount) ($($lastSample.HandleCount - $firstSample.HandleCount) change)" -ForegroundColor White
    
} else {
    Write-Host "Insufficient samples collected for analysis" -ForegroundColor Red
}

Write-Host "" -ForegroundColor White
Write-Host "Detailed results saved to: $logFile" -ForegroundColor Cyan
Write-Host "Review the CSV file for complete timeline" -ForegroundColor Cyan
