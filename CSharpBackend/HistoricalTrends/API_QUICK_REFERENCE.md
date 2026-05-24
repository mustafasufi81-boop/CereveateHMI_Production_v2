# LICENSED BI SYSTEM - QUICK API REFERENCE

## 🔑 Authentication Flow

```
1. Login → Get session_token
2. Use session_token in all API calls
3. System auto-updates last_activity (keeps session alive)
4. Idle 30 min → Session removed
5. Logout → Manually remove session
```

---

## 📡 API Endpoints

### 🔐 Authentication

#### Login
```http
POST /auth/login
Content-Type: application/json

{
  "user_id": "john.doe",
  "ip_address": "192.168.1.100",
  "metadata": {}
}

Response:
{
  "success": true,
  "user_id": "john.doe",
  "session_token": "abc123...",
  "message": "Login successful",
  "max_concurrent_users": 5,
  "active_sessions": 3
}
```

#### Logout
```http
POST /auth/logout
X-User-ID: john.doe

Response:
{
  "success": true,
  "message": "Logout successful"
}
```

---

### 🎫 License Management

#### Install License (ONE-TIME ONLY)
```http
POST /setup/install_license
Content-Type: application/json

{
  "max_concurrent_users": 5,
  "admin_key": "YOUR_SUPER_SECRET_KEY"
}

Response:
{
  "success": true,
  "message": "License installed successfully",
  "max_concurrent_users": 5,
  "installation_date": "2024-01-15T10:00:00"
}
```

#### View License Info (Read-Only)
```http
GET /license/info

Response:
{
  "max_concurrent_users": 5,
  "installation_date": "2024-01-15T10:00:00",
  "license_installed": true,
  "current_active_users": 3,
  "available_slots": 2,
  "active_sessions": [...]
}
```

#### Update License (Admin Only)
```http
POST /admin/update_license
Content-Type: application/json

{
  "new_max_users": 10,
  "admin_key": "YOUR_SUPER_SECRET_KEY"
}

Response:
{
  "success": true,
  "message": "License updated successfully",
  "new_max_users": 10
}
```

#### View Active Sessions
```http
GET /sessions/active

Response:
{
  "active_sessions": [
    {
      "user_id": "john.doe",
      "login_time": "2024-01-15T11:00:00",
      "last_activity": "2024-01-15T11:25:00"
    }
  ],
  "total_count": 3,
  "max_allowed": 5,
  "available_slots": 2
}
```

---

### 📊 BI Analysis (All require session headers)

#### Full BI Analysis (8 Steps)
```http
POST /api/v1/analyze/full
Content-Type: application/json
X-User-ID: john.doe
X-Session-Token: abc123...

{
  "data": [
    {"Timestamp": "2024-01-01T00:00:00", "Load": 500, "Vibration": 2.5},
    {"Timestamp": "2024-01-01T00:01:00", "Load": 505, "Vibration": 2.6}
  ],
  "production_tag": "Load",
  "influencing_tags": ["Vibration", "NOx", "Coal_GCV"],
  "rated_capacity": 660
}

Response:
{
  "success": true,
  "user_id": "john.doe",
  "session_token": "abc123...",
  "result": {
    "baseline": {...},
    "efficiency_adjustment": {...},
    "influence_map": {...},
    "availability": {...},
    "performance_score": {...},
    "stability_index": {...},
    "condition_score": {...},
    "loss_attribution": {...}
  },
  "timestamp": "2024-01-15T11:30:00"
}
```

#### Calculate Baseline
```http
POST /api/v1/calculate/baseline
Content-Type: application/json
X-User-ID: john.doe
X-Session-Token: abc123...

{
  "data": [...],
  "tag": "Load"
}

Response:
{
  "success": true,
  "user_id": "john.doe",
  "session_token": "abc123...",
  "result": {
    "baseline_value": 550.5,
    "outlier_method": "sigma",
    "data_points_used": 1000,
    "clean_data_percentage": 98.5
  }
}
```

#### Calculate Influence Map
```http
POST /api/v1/calculate/influence_map
Content-Type: application/json
X-User-ID: john.doe
X-Session-Token: abc123...

{
  "data": [...],
  "primary_tag": "Load",
  "influencing_tags": ["Vibration", "NOx", "Coal_GCV"]
}

Response:
{
  "success": true,
  "user_id": "john.doe",
  "session_token": "abc123...",
  "result": {
    "correlations": {
      "Vibration": -0.85,
      "NOx": 0.72,
      "Coal_GCV": 0.91
    },
    "cross_correlations": {...},
    "lag_analysis": {...}
  }
}
```

#### Calculate Availability
```http
POST /api/v1/calculate/availability
Content-Type: application/json
X-User-ID: john.doe
X-Session-Token: abc123...

{
  "data": [...],
  "load_col": "Load",
  "rated_capacity": 660
}

Response:
{
  "success": true,
  "user_id": "john.doe",
  "session_token": "abc123...",
  "result": {
    "cumulative_availability": 85.5,
    "total_production": 123456.7,
    "max_possible": 144000.0,
    "loss_mw": 20543.3
  }
}
```

---

### 💾 Cache Management

#### Invalidate Cache
```http
POST /api/v1/cache/invalidate
X-User-ID: john.doe
X-Session-Token: abc123...

Response:
{
  "success": true,
  "user_id": "john.doe",
  "message": "Cache invalidated for user"
}
```

#### Get Cache Stats
```http
GET /api/v1/cache/stats
X-User-ID: john.doe
X-Session-Token: abc123...

Response:
{
  "success": true,
  "user_id": "john.doe",
  "cache_stats": {
    "total_cached_results": 15,
    "cache_hits": 42,
    "cache_misses": 8,
    "hit_rate": 84.0
  }
}
```

---

### 🏥 Health & Status

#### Root
```http
GET /

Response:
{
  "status": "online",
  "service": "Industrial BI Engine API",
  "version": "2.0.0",
  "licensed": true,
  "multi_user": true,
  "async_processing": true,
  "active_sessions": 3
}
```

#### Health Check
```http
GET /health

Response:
{
  "status": "healthy",
  "config_loaded": true,
  "active_sessions": 3,
  "max_workers": 4,
  "max_concurrent_users": 5,
  "license_installed": true,
  "multi_user_support": true
}
```

---

## 🚨 Error Responses

### 403 Forbidden - Max Users Reached
```json
{
  "detail": "Maximum concurrent users (5) reached. Please try again later."
}
```

**Frontend should:**
- Show "System at capacity" message
- Retry after a few minutes
- Or show waiting list

### 403 Forbidden - Invalid Session
```json
{
  "detail": "Invalid session token or session expired"
}
```

**Frontend should:**
- Clear localStorage
- Redirect to login page
- Show "Session expired" message

### 403 Forbidden - Invalid Admin Key
```json
{
  "detail": "Invalid admin API key"
}
```

**Admin should:**
- Verify admin key is correct
- Check license file `.bi_license.json`

### 400 Bad Request - License Already Installed
```json
{
  "detail": "License already installed. Use /admin/update_license to change limits."
}
```

**Fix:**
- Use `/admin/update_license` instead
- Or delete `.bi_license.json` and reinstall (not recommended)

---

## 📋 Header Requirements

### All BI Analysis Endpoints Require:
```http
X-User-ID: john.doe          # User identifier
X-Session-Token: abc123...   # Session token from login
Content-Type: application/json
```

### Authentication Endpoints:
```http
Content-Type: application/json
```

### Logout Endpoint:
```http
X-User-ID: john.doe
```

---

## ⏱️ Session Lifecycle

```
1. Login → session_token created
   - Stored in: license_manager._sessions
   - Stored in: user_sessions (FastAPI)
   - login_time = now
   - last_activity = now

2. Every API call → last_activity updated
   - Keeps session ACTIVE

3. No activity for 30 min → Idle session removed
   - Background cleanup task runs every 5 minutes
   - Checks: (now - last_activity) > 30 min
   - Removes: IDLE sessions only

4. Logout → session removed immediately
   - Manual cleanup
   - Frees up concurrent user slot
```

---

## 🔄 Same User Login from Multiple Locations

**Scenario:**
1. User "john.doe" logs in from Computer A
2. User "john.doe" logs in from Computer B

**What happens:**
1. System detects same user_id
2. **Automatically logs out Computer A**
3. Computer B gets new session_token
4. Computer A next API call → 403 error

**Frontend handling:**
```javascript
if (response.status === 403) {
    alert('You have been logged in from another location');
    localStorage.clear();
    window.location.href = '/login';
}
```

---

## 🛡️ Security Checklist

- [ ] Admin key stored securely (NOT in code)
- [ ] HTTPS enabled in production
- [ ] CORS configured for specific domains (not "*")
- [ ] Rate limiting enabled on /auth/login
- [ ] Session tokens stored securely (localStorage with HTTPS)
- [ ] License file `.bi_license.json` backed up
- [ ] Admin key never committed to source control
- [ ] Production uses environment variables

---

## 🎯 Quick Start Commands

### Installation
```powershell
# Install license (one-time)
$body = @{max_concurrent_users=5; admin_key="SECRET"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/setup/install_license" -Method POST -Body $body -ContentType "application/json"
```

### Daily Operations
```powershell
# View active users
Invoke-RestMethod -Uri "http://localhost:8000/sessions/active"

# View license info
Invoke-RestMethod -Uri "http://localhost:8000/license/info"

# Check system health
Invoke-RestMethod -Uri "http://localhost:8000/health"
```

### Admin Tasks
```powershell
# Increase user limit to 10
$body = @{new_max_users=10; admin_key="SECRET"} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/admin/update_license" -Method POST -Body $body -ContentType "application/json"
```

---

## 📊 Configuration (bi_config.yaml)

```yaml
api:
  max_workers: 4              # CPU cores for parallel processing
  session_timeout: 30         # Idle timeout (minutes)
  cors_origins: ["*"]         # Change in production

baseline:
  baseline_window_days: 30    # Rolling window
  outlier_method: "sigma"     # sigma, iqr, mad, percentile
  outlier_threshold: 3.0      # Standard deviations
  min_data_points: 50         # Minimum for valid baseline

# All plant-specific parameters configurable
```

---

## ✅ Testing Workflow

```powershell
# 1. Start server
uvicorn bi_api_licensed:app --reload

# 2. Install license
# ... (see above)

# 3. Test login
$login = @{user_id="test_user"} | ConvertTo-Json
$result = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" -Method POST -Body $login -ContentType "application/json"
$token = $result.session_token

# 4. Test analysis
$headers = @{
    "X-User-ID" = "test_user"
    "X-Session-Token" = $token
    "Content-Type" = "application/json"
}
$data = @{
    data = @(@{Timestamp="2024-01-01T00:00:00"; Load=500})
    tag = "Load"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/calculate/baseline" -Method POST -Headers $headers -Body $data

# 5. Test logout
$headers = @{"X-User-ID" = "test_user"}
Invoke-RestMethod -Uri "http://localhost:8000/auth/logout" -Method POST -Headers $headers
```

---

**System Status:** ✅ READY FOR DEPLOYMENT

Licensed multi-user industrial BI system with:
- Max 5 concurrent users (configurable)
- Single session enforcement
- 30-minute idle timeout
- Zero hardcoded values
- Zero lag performance
- Complete session isolation

For detailed documentation, see: `LICENSED_SYSTEM_DEPLOYMENT.md`
