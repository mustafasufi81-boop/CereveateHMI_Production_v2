# 🚀 LICENSED BI SYSTEM - STARTUP CHECKLIST

## Pre-Deployment Checklist

### ☑️ Dependencies Installed
```powershell
# Check Python version (3.8+ required)
python --version

# Install all dependencies
pip install fastapi uvicorn pandas numpy scipy pyyaml python-multipart

# Verify installations
python -c "import fastapi, pandas, numpy, scipy, yaml; print('✅ All dependencies OK')"
```

### ☑️ Configuration Ready
- [ ] `bi_engines/config/bi_config.yaml` configured for your plant
- [ ] API settings reviewed (max_workers, session_timeout)
- [ ] Baseline parameters set (window days, outlier method)
- [ ] Efficiency influencing parameters defined
- [ ] All thresholds customized for your equipment

### ☑️ Security Prepared
- [ ] Admin API key generated (use strong random key)
- [ ] Admin key stored securely (environment variable or secrets manager)
- [ ] CORS origins configured (change from "*" to specific domains)
- [ ] HTTPS certificate ready for production
- [ ] Firewall rules configured

---

## First-Time Setup (Step-by-Step)

### Step 1: Start the Server
```powershell
# Development mode (auto-reload enabled)
cd "d:\Development\New_Developement\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy\HistoricalTrends"
uvicorn bi_api_licensed:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output:**
```
INFO:     Will watch for changes in these directories: [...]
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [...]
INFO:     Started server process [...]
INFO:     Waiting for application startup.
================================================================================
🚀 INDUSTRIAL BI ENGINE API - LICENSED MULTI-USER
================================================================================
✓ Zero hardcoding - All config in bi_config.yaml
✓ Multi-user concurrent - Per-user session isolation
✓ Zero lag - Async processing with process pool
✓ Licensed system - Concurrent user limit enforcement
✓ Max workers: 4
✓ Session timeout: 30 min (idle only)
✓ License status: Not installed - Run /setup/install_license
================================================================================
INFO:     Application startup complete.
```

### Step 2: Verify Server is Running
```powershell
# Test root endpoint
Invoke-RestMethod -Uri "http://localhost:8000/"
```

**Expected Response:**
```json
{
  "status": "online",
  "service": "Industrial BI Engine API",
  "version": "2.0.0",
  "licensed": true,
  "multi_user": true,
  "async_processing": true,
  "active_sessions": 0,
  "timestamp": "2024-01-15T10:00:00"
}
```

### Step 3: Check Health
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health"
```

**Expected Response:**
```json
{
  "status": "healthy",
  "config_loaded": true,
  "active_sessions": 0,
  "max_workers": 4,
  "max_concurrent_users": "Not installed",
  "license_installed": false,
  "multi_user_support": true,
  "timestamp": "2024-01-15T10:00:00"
}
```

⚠️ **Notice:** `license_installed: false` - This is expected on first run

### Step 4: Install License (CRITICAL - Do this first!)
```powershell
# Generate admin key (SAVE THIS!)
$adminKey = [System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
Write-Output "Admin Key (SAVE THIS SECURELY): $adminKey"

# Install license with 5 concurrent users
$body = @{
    max_concurrent_users = 5
    admin_key = $adminKey
} | ConvertTo-Json

$licenseResult = Invoke-RestMethod -Uri "http://localhost:8000/setup/install_license" `
    -Method POST `
    -Body $body `
    -ContentType "application/json"

Write-Output $licenseResult
```

**Expected Response:**
```json
{
  "success": true,
  "message": "License installed successfully",
  "max_concurrent_users": 5,
  "installation_date": "2024-01-15T10:05:00"
}
```

**⚠️ IMPORTANT:** Save the `$adminKey` value securely - you'll need it to change license limits later!

### Step 5: Verify License Installed
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/license/info"
```

**Expected Response:**
```json
{
  "max_concurrent_users": 5,
  "installation_date": "2024-01-15T10:05:00",
  "license_installed": true,
  "current_active_users": 0,
  "active_sessions": [],
  "available_slots": 5
}
```

✅ **License installed successfully!**

---

## Testing the System

### Test 1: User Login
```powershell
# Login as test user
$loginBody = @{
    user_id = "test_user_1"
    ip_address = "192.168.1.100"
    metadata = @{
        test = "true"
    }
} | ConvertTo-Json

$loginResult = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" `
    -Method POST `
    -Body $loginBody `
    -ContentType "application/json"

Write-Output $loginResult

# Save session token
$sessionToken = $loginResult.session_token
$userId = $loginResult.user_id
```

**Expected Response:**
```json
{
  "success": true,
  "user_id": "test_user_1",
  "session_token": "a1b2c3d4e5f6...",
  "message": "Login successful",
  "max_concurrent_users": 5,
  "active_sessions": 1
}
```

### Test 2: View Active Sessions
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/sessions/active"
```

**Expected Response:**
```json
{
  "active_sessions": [
    {
      "user_id": "test_user_1",
      "login_time": "2024-01-15T10:10:00",
      "last_activity": "2024-01-15T10:10:00"
    }
  ],
  "total_count": 1,
  "max_allowed": 5,
  "available_slots": 4
}
```

### Test 3: Calculate Baseline (BI Analysis)
```powershell
# Create test data
$testData = @{
    data = @(
        @{Timestamp = "2024-01-01T00:00:00"; Load = 500},
        @{Timestamp = "2024-01-01T00:01:00"; Load = 505},
        @{Timestamp = "2024-01-01T00:02:00"; Load = 510}
    )
    tag = "Load"
} | ConvertTo-Json -Depth 10

# Make API call with session headers
$headers = @{
    "X-User-ID" = $userId
    "X-Session-Token" = $sessionToken
    "Content-Type" = "application/json"
}

$baselineResult = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/calculate/baseline" `
    -Method POST `
    -Headers $headers `
    -Body $testData

Write-Output $baselineResult
```

**Expected Response:**
```json
{
  "success": true,
  "user_id": "test_user_1",
  "session_token": "a1b2c3d4e5f6...",
  "result": {
    "baseline_value": 505.0,
    "outlier_method": "sigma",
    "data_points_used": 3,
    "clean_data_percentage": 100.0
  },
  "timestamp": "2024-01-15T10:15:00"
}
```

### Test 4: User Logout
```powershell
$logoutHeaders = @{
    "X-User-ID" = $userId
}

$logoutResult = Invoke-RestMethod -Uri "http://localhost:8000/auth/logout" `
    -Method POST `
    -Headers $logoutHeaders

Write-Output $logoutResult
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Logout successful"
}
```

### Test 5: Verify Session Removed
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/sessions/active"
```

**Expected Response:**
```json
{
  "active_sessions": [],
  "total_count": 0,
  "max_allowed": 5,
  "available_slots": 5
}
```

✅ **All tests passed!**

---

## Multi-User Testing

### Test Concurrent Users (5 users)
```powershell
# Login 5 users
for ($i=1; $i -le 5; $i++) {
    $body = @{user_id = "user_$i"} | ConvertTo-Json
    $result = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" `
        -Method POST -Body $body -ContentType "application/json"
    Write-Output "User $i logged in: $($result.session_token)"
}

# Check active sessions
$sessions = Invoke-RestMethod -Uri "http://localhost:8000/sessions/active"
Write-Output "Active users: $($sessions.total_count)/5"
```

### Test Max Users Exceeded
```powershell
# Try to login 6th user (should fail)
try {
    $body = @{user_id = "user_6"} | ConvertTo-Json
    Invoke-RestMethod -Uri "http://localhost:8000/auth/login" `
        -Method POST -Body $body -ContentType "application/json"
} catch {
    Write-Output "Expected error: $($_.Exception.Message)"
}
```

**Expected Error:**
```
Maximum concurrent users (5) reached. Please try again later.
```

### Test Same User Multiple Locations
```powershell
# Login user_1 from location A
$bodyA = @{
    user_id = "user_1"
    ip_address = "192.168.1.100"
} | ConvertTo-Json

$resultA = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" `
    -Method POST -Body $bodyA -ContentType "application/json"

Write-Output "Location A session: $($resultA.session_token)"

# Login same user_1 from location B (should logout location A)
$bodyB = @{
    user_id = "user_1"
    ip_address = "192.168.1.200"
} | ConvertTo-Json

$resultB = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" `
    -Method POST -Body $bodyB -ContentType "application/json"

Write-Output "Location B session: $($resultB.session_token)"

# Verify sessions
$sessions = Invoke-RestMethod -Uri "http://localhost:8000/sessions/active"
$user1Sessions = $sessions.active_sessions | Where-Object {$_.user_id -eq "user_1"}
Write-Output "User_1 sessions: $($user1Sessions.Count) (should be 1)"
```

---

## Production Deployment Checklist

### ☑️ Pre-Production
- [ ] All tests passed (see above)
- [ ] Configuration customized for production
- [ ] Admin key stored in environment variable
- [ ] CORS origins set to specific domains (not "*")
- [ ] HTTPS certificate configured
- [ ] Reverse proxy configured (nginx/Apache)
- [ ] Firewall rules configured
- [ ] Backup strategy for `.bi_license.json`

### ☑️ Security Hardening
```powershell
# Set admin key as environment variable (don't hardcode!)
$env:BI_ADMIN_KEY = "YOUR_ADMIN_KEY_HERE"

# Update bi_config.yaml for production
# Change cors_origins from "*" to specific domains
```

**bi_config.yaml (Production):**
```yaml
api:
  max_workers: 8  # Increase for production server
  session_timeout: 30
  cors_origins:
    - "https://yourplant.com"
    - "https://app.yourplant.com"
  # Remove "*" wildcard
```

### ☑️ Production Startup
```powershell
# Production mode with multiple workers
uvicorn bi_api_licensed:app --workers 4 --host 0.0.0.0 --port 8000 `
    --ssl-keyfile=/path/to/key.pem `
    --ssl-certfile=/path/to/cert.pem
```

**Or with Gunicorn (Linux):**
```bash
gunicorn bi_api_licensed:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### ☑️ Monitoring Setup
- [ ] Health check endpoint monitored (`/health`)
- [ ] Active sessions monitored (`/sessions/active`)
- [ ] Server logs monitored
- [ ] Error alerts configured
- [ ] Performance metrics tracked

---

## Troubleshooting Quick Reference

### Issue: Server won't start
**Check:**
```powershell
# Python version
python --version  # Should be 3.8+

# Dependencies
pip list | Select-String "fastapi|uvicorn|pandas|numpy"

# Config file exists
Test-Path "bi_engines/config/bi_config.yaml"
```

### Issue: License not installed
**Fix:**
```powershell
# Install license (see Step 4 above)
# Or check if .bi_license.json exists
Test-Path ".bi_license.json"
```

### Issue: Can't login (max users)
**Check:**
```powershell
# View active sessions
Invoke-RestMethod -Uri "http://localhost:8000/sessions/active"

# Force logout all users (admin)
# Wait 30 minutes for idle cleanup
# Or restart server (in-memory sessions cleared)
```

### Issue: Session expired
**Check:**
```powershell
# Verify session token is correct
# Check if user was logged out from another location
# Check if idle timeout (30 min) occurred
```

---

## Emergency Procedures

### Reset License (CAUTION!)
```powershell
# Stop server
# Delete license file
Remove-Item ".bi_license.json" -Force

# Restart server
# Reinstall license (see Step 4)
```

### Force Logout All Users
```powershell
# Restart server (sessions are in-memory)
# OR wait 30 minutes for idle cleanup
```

### Change License Limit
```powershell
# Use admin key (saved from installation)
$body = @{
    new_max_users = 10
    admin_key = $env:BI_ADMIN_KEY
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/admin/update_license" `
    -Method POST -Body $body -ContentType "application/json"
```

---

## Success Indicators

✅ Server starts without errors
✅ `/health` returns "healthy"
✅ License shows "installed: true"
✅ User can login and get session_token
✅ BI analysis works with session headers
✅ Max concurrent users enforced
✅ Same user force logout works
✅ Idle timeout removes inactive sessions
✅ Active sessions preserved
✅ Logout removes session immediately

---

## API Documentation

**Swagger UI (Interactive API Docs):**
```
http://localhost:8000/docs
```

**ReDoc (Alternative Docs):**
```
http://localhost:8000/redoc
```

**OpenAPI JSON:**
```
http://localhost:8000/openapi.json
```

---

## File Locations

**Critical Files:**
- Configuration: `bi_engines/config/bi_config.yaml`
- License: `.bi_license.json` (created after installation)
- Server: `bi_api_licensed.py`
- Engines: `bi_engines/*.py`

**Documentation:**
- Deployment Guide: `LICENSED_SYSTEM_DEPLOYMENT.md`
- API Reference: `API_QUICK_REFERENCE.md`
- Implementation Summary: `IMPLEMENTATION_COMPLETE.md`

**Logs:**
- Server logs: Check console output
- Error logs: Configure in `logging` module

---

## Support Contacts

**Documentation:**
- Full guide: `LICENSED_SYSTEM_DEPLOYMENT.md`
- Quick reference: `API_QUICK_REFERENCE.md`

**Configuration:**
- System settings: `bi_engines/config/bi_config.yaml`
- License info: `GET /license/info`

---

## ✅ Final Checklist

- [ ] Dependencies installed
- [ ] Server starts successfully
- [ ] License installed
- [ ] Health check passes
- [ ] User login works
- [ ] BI analysis works
- [ ] Logout works
- [ ] Multi-user tested
- [ ] Max users enforced
- [ ] Same user force logout works
- [ ] Idle timeout tested
- [ ] Production config ready
- [ ] Security hardened
- [ ] Documentation reviewed

---

**🎉 SYSTEM READY FOR PRODUCTION!**

Your licensed multi-user industrial BI system is fully operational with:
- ✅ 5 concurrent user limit
- ✅ Single session enforcement
- ✅ 30-minute idle timeout
- ✅ Zero hardcoded values
- ✅ Zero lag performance
- ✅ Complete session isolation

**Happy analyzing!** 🚀
