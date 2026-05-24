# LICENSED MULTI-USER BI SYSTEM - DEPLOYMENT GUIDE

## 🎯 System Overview

This industrial BI system now includes **licensed concurrent user management**:

- ✅ **Max 5 concurrent users** (configurable at installation)
- ✅ **Same user can only login once** (force logout from other locations)
- ✅ **30-minute idle timeout** (only idle sessions, not active ones)
- ✅ **Installation-time license** with admin key protection
- ✅ **Zero hardcoded values** - All config in YAML
- ✅ **Zero lag performance** - Async processing
- ✅ **Complete session isolation** - Per-user orchestrators

---

## 📋 Prerequisites

```powershell
# Python 3.8+ required
python --version

# Install dependencies
pip install -r bi_engines_requirements.txt
```

**Required packages:**
- fastapi
- uvicorn[standard]
- pandas
- numpy
- scipy
- pyyaml
- python-multipart

---

## 🚀 Installation Steps

### Step 1: Configure System (bi_config.yaml)

Edit `bi_engines/config/bi_config.yaml`:

```yaml
api:
  max_workers: 4  # CPU cores for parallel processing
  session_timeout: 30  # Idle timeout (minutes)
  cors_origins:
    - "*"  # Production: Change to specific domains

baseline:
  baseline_window_days: 30
  outlier_method: "sigma"  # sigma, iqr, mad, percentile
  outlier_threshold: 3.0
  min_data_points: 50

efficiency:
  influencing_parameters:
    - name: "Coal_GCV"
      direction: "positive"
    - name: "Condenser_Vacuum"
      direction: "positive"
    # Add your plant-specific parameters

# All plant-specific values configurable here
```

### Step 2: Start the API Server

```powershell
# Development mode (auto-reload)
uvicorn bi_api_licensed:app --reload --host 0.0.0.0 --port 8000

# Production mode with Gunicorn (Linux/Mac)
gunicorn bi_api_licensed:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Production mode with Uvicorn (Windows)
uvicorn bi_api_licensed:app --workers 4 --host 0.0.0.0 --port 8000
```

Server will start at: `http://localhost:8000`

### Step 3: Install License (ONE-TIME ONLY)

**CRITICAL: Do this immediately after first startup**

```powershell
# Using PowerShell
$body = @{
    max_concurrent_users = 5
    admin_key = "YOUR_SUPER_SECRET_ADMIN_KEY_HERE"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/setup/install_license" `
    -Method POST `
    -Body $body `
    -ContentType "application/json"
```

**Expected Response:**
```json
{
  "success": true,
  "message": "License installed successfully",
  "max_concurrent_users": 5,
  "installation_date": "2024-01-15T10:00:00"
}
```

**IMPORTANT:**
- This can only be called ONCE during installation
- Save the `admin_key` securely - required to change limits later
- License is stored in encrypted `.bi_license.json` file

---

## 👤 User Authentication Flow

### 1. User Login

**Frontend JavaScript:**
```javascript
// Login request
async function loginUser(userId) {
    const response = await fetch('http://localhost:8000/auth/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            user_id: userId,
            ip_address: window.location.hostname,
            metadata: {
                browser: navigator.userAgent,
                login_time: new Date().toISOString()
            }
        })
    });
    
    const result = await response.json();
    
    if (result.success) {
        // Store session token and user ID
        localStorage.setItem('session_token', result.session_token);
        localStorage.setItem('user_id', result.user_id);
        
        console.log('Login successful:', result.message);
        console.log(`Active users: ${result.active_sessions}/${result.max_concurrent_users}`);
        
        return result;
    } else {
        throw new Error('Login failed: ' + result.detail);
    }
}
```

**What happens:**
- ✅ Checks if max concurrent users reached (5)
- ✅ If same user logged in elsewhere, **forces logout** of old session
- ✅ Creates new session token (SHA256 hash)
- ✅ Returns session token to frontend

### 2. Making API Calls

**All BI analysis endpoints require session headers:**

```javascript
async function performAnalysis(data) {
    const userId = localStorage.getItem('user_id');
    const sessionToken = localStorage.getItem('session_token');
    
    const response = await fetch('http://localhost:8000/api/v1/analyze/full', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-User-ID': userId,
            'X-Session-Token': sessionToken
        },
        body: JSON.stringify({
            data: data,
            production_tag: "Load",
            influencing_tags: ["Vibration", "NOx", "Coal_GCV"],
            rated_capacity: 660
        })
    });
    
    const result = await response.json();
    
    if (response.status === 403) {
        // Concurrent user limit reached
        console.error('Maximum users reached:', result.detail);
        // Redirect to waiting page or show error
        return;
    }
    
    return result;
}
```

### 3. User Logout

```javascript
async function logoutUser() {
    const userId = localStorage.getItem('user_id');
    
    const response = await fetch('http://localhost:8000/auth/logout', {
        method: 'POST',
        headers: {
            'X-User-ID': userId
        }
    });
    
    const result = await response.json();
    
    if (result.success) {
        // Clear local storage
        localStorage.removeItem('session_token');
        localStorage.removeItem('user_id');
        
        console.log('Logout successful');
    }
}
```

---

## ⏱️ Session Management

### Idle Timeout (30 Minutes)

**Background task runs every 5 minutes:**
- Checks last activity timestamp for each session
- If idle > 30 minutes → Session removed
- **Active sessions are NEVER removed**

**How it works:**
```python
# Every API call updates last_activity
user_sessions[user_id]['last_accessed'] = datetime.now()
license_manager.update_session_activity(user_id)

# Background cleanup only removes IDLE sessions
if idle_time > 30 minutes:
    # Remove session
```

**Keep session active:**
```javascript
// Frontend: Heartbeat every 5 minutes
setInterval(async () => {
    const userId = localStorage.getItem('user_id');
    const sessionToken = localStorage.getItem('session_token');
    
    // Any API call keeps session alive
    await fetch('http://localhost:8000/health', {
        headers: {
            'X-User-ID': userId,
            'X-Session-Token': sessionToken
        }
    });
}, 5 * 60 * 1000); // Every 5 minutes
```

### Single Session Per User

**Scenario:** User A logs in from Computer 1, then logs in from Computer 2

**What happens:**
1. Computer 2 login request detected
2. **System automatically logs out Computer 1**
3. Computer 2 gets new session token
4. Computer 1 next API call returns 403 (session invalid)

**Frontend should handle:**
```javascript
// Detect session invalidation
if (response.status === 403) {
    alert('You have been logged in from another location');
    // Redirect to login page
    window.location.href = '/login';
}
```

---

## 📊 License Management

### View License Info (Read-Only)

```powershell
# Get current license status
Invoke-RestMethod -Uri "http://localhost:8000/license/info" -Method GET
```

**Response:**
```json
{
  "max_concurrent_users": 5,
  "installation_date": "2024-01-15T10:00:00",
  "license_installed": true,
  "current_active_users": 3,
  "active_sessions": [
    {
      "user_id": "john.doe",
      "login_time": "2024-01-15T11:00:00",
      "last_activity": "2024-01-15T11:25:00",
      "ip_address": "192.168.1.100"
    },
    // ... more users
  ],
  "available_slots": 2
}
```

### View Active Sessions

```powershell
# See who's currently logged in
Invoke-RestMethod -Uri "http://localhost:8000/sessions/active" -Method GET
```

**Response:**
```json
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

### Update License Limit (Admin Only)

**Requires admin API key:**

```powershell
$body = @{
    new_max_users = 10
    admin_key = "YOUR_SUPER_SECRET_ADMIN_KEY_HERE"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/admin/update_license" `
    -Method POST `
    -Body $body `
    -ContentType "application/json"
```

**Response:**
```json
{
  "success": true,
  "message": "License updated successfully",
  "new_max_users": 10
}
```

**Error (wrong admin key):**
```json
{
  "detail": "Invalid admin API key"
}
```

---

## 🔧 API Endpoints Summary

### Authentication
- `POST /auth/login` - User login (returns session token)
- `POST /auth/logout` - User logout (frees slot)

### License Management
- `POST /setup/install_license` - ONE-TIME license installation
- `GET /license/info` - View license (read-only)
- `POST /admin/update_license` - Update license limit (admin key required)
- `GET /sessions/active` - View active users

### BI Analysis (All require session headers)
- `POST /api/v1/analyze/full` - Full 8-step BI analysis
- `POST /api/v1/calculate/baseline` - Adaptive baseline
- `POST /api/v1/calculate/influence_map` - Correlation analysis
- `POST /api/v1/calculate/availability` - Availability metrics
- `POST /api/v1/cache/invalidate` - Clear user cache
- `GET /api/v1/cache/stats` - Cache statistics

### Health & Status
- `GET /` - API root (basic info)
- `GET /health` - Detailed health check

---

## 🛡️ Security Best Practices

### 1. Admin Key Protection

```powershell
# Generate strong admin key
$adminKey = [System.Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
Write-Output $adminKey

# Example: "K7gNU3sdo+OL0wNhqoVWhr3g6s1xYv72ol/pe/Unols="
```

**Store securely:**
- Environment variable: `$env:BI_ADMIN_KEY = "..."`
- Secrets management (Azure Key Vault, AWS Secrets Manager)
- **NEVER commit to source control**

### 2. CORS Configuration

**Production setup:**
```yaml
# bi_config.yaml
api:
  cors_origins:
    - "https://yourplant.com"
    - "https://app.yourplant.com"
  # Remove "*" wildcard
```

### 3. HTTPS in Production

```powershell
# Use reverse proxy (nginx, Apache)
# Or run with HTTPS certificates
uvicorn bi_api_licensed:app --workers 4 --host 0.0.0.0 --port 8000 `
    --ssl-keyfile=/path/to/key.pem `
    --ssl-certfile=/path/to/cert.pem
```

### 4. Rate Limiting

```python
# Add to bi_api_licensed.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/auth/login")
@limiter.limit("5/minute")  # Max 5 login attempts per minute
async def login(request: LoginRequest):
    # ... existing code
```

---

## 📱 Frontend Integration Example

```javascript
// complete-bi-integration.js

class BIClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
        this.userId = null;
        this.sessionToken = null;
    }
    
    async login(userId) {
        const response = await fetch(`${this.baseUrl}/auth/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                user_id: userId,
                ip_address: window.location.hostname
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }
        
        const result = await response.json();
        this.userId = result.user_id;
        this.sessionToken = result.session_token;
        
        // Store in localStorage
        localStorage.setItem('user_id', this.userId);
        localStorage.setItem('session_token', this.sessionToken);
        
        return result;
    }
    
    async logout() {
        const response = await fetch(`${this.baseUrl}/auth/logout`, {
            method: 'POST',
            headers: {'X-User-ID': this.userId}
        });
        
        localStorage.removeItem('user_id');
        localStorage.removeItem('session_token');
        this.userId = null;
        this.sessionToken = null;
        
        return await response.json();
    }
    
    async fullAnalysis(data, productionTag, influencingTags, ratedCapacity) {
        const response = await fetch(`${this.baseUrl}/api/v1/analyze/full`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-ID': this.userId,
                'X-Session-Token': this.sessionToken
            },
            body: JSON.stringify({
                data: data,
                production_tag: productionTag,
                influencing_tags: influencingTags,
                rated_capacity: ratedCapacity
            })
        });
        
        if (response.status === 403) {
            // Session invalid or max users reached
            alert('Session expired or maximum users reached');
            window.location.href = '/login';
            return;
        }
        
        return await response.json();
    }
    
    async getLicenseInfo() {
        const response = await fetch(`${this.baseUrl}/license/info`);
        return await response.json();
    }
    
    async getActiveSessions() {
        const response = await fetch(`${this.baseUrl}/sessions/active`);
        return await response.json();
    }
    
    // Keep session alive
    startHeartbeat() {
        setInterval(async () => {
            if (this.userId && this.sessionToken) {
                await fetch(`${this.baseUrl}/health`, {
                    headers: {
                        'X-User-ID': this.userId,
                        'X-Session-Token': this.sessionToken
                    }
                });
            }
        }, 5 * 60 * 1000); // Every 5 minutes
    }
}

// Usage
const biClient = new BIClient();

// Login
await biClient.login('john.doe');

// Start heartbeat to keep session active
biClient.startHeartbeat();

// Perform analysis
const result = await biClient.fullAnalysis(
    historicalData,
    'Load',
    ['Vibration', 'NOx', 'Coal_GCV'],
    660
);

// View license info
const licenseInfo = await biClient.getLicenseInfo();
console.log(`Users: ${licenseInfo.current_active_users}/${licenseInfo.max_concurrent_users}`);

// Logout
await biClient.logout();
```

---

## 🐛 Troubleshooting

### Issue: "Maximum concurrent users reached"

**Cause:** 5 users already logged in

**Solutions:**
1. Check active sessions: `GET /sessions/active`
2. Wait for idle session cleanup (30 min)
3. Admin: Increase limit with admin key

### Issue: "Same user logged in from another location"

**Expected behavior** - This is a feature, not a bug

**What to do:**
- Frontend should detect 403 response
- Show message: "You have been logged in elsewhere"
- Redirect to login page

### Issue: Session expires too quickly

**Check:**
- Background cleanup runs every 5 minutes
- Idle timeout is 30 minutes
- Heartbeat is sending requests every 5 minutes

**Fix:**
```javascript
// Increase heartbeat frequency
setInterval(() => fetch('/health'), 2 * 60 * 1000); // Every 2 minutes
```

### Issue: License not installed

**Error:** "License not installed"

**Fix:**
```powershell
# Install license (one-time)
$body = @{
    max_concurrent_users = 5
    admin_key = "YOUR_ADMIN_KEY"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/setup/install_license" `
    -Method POST -Body $body -ContentType "application/json"
```

---

## 📈 Production Deployment

### Windows Server (IIS + FastCGI)

1. Install Python 3.8+
2. Install dependencies
3. Configure IIS with FastCGI
4. Run uvicorn as Windows Service

### Linux Server (systemd + nginx)

```bash
# Create systemd service
sudo nano /etc/systemd/system/bi-engine.service

[Unit]
Description=Industrial BI Engine API
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/bi-engine
Environment="PATH=/opt/bi-engine/venv/bin"
ExecStart=/opt/bi-engine/venv/bin/uvicorn bi_api_licensed:app --workers 4 --host 127.0.0.1 --port 8000

[Install]
WantedBy=multi-user.target

# Start service
sudo systemctl daemon-reload
sudo systemctl start bi-engine
sudo systemctl enable bi-engine
```

**nginx reverse proxy:**
```nginx
server {
    listen 80;
    server_name yourplant.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## ✅ Testing Checklist

- [ ] License installed successfully
- [ ] User can login and receive session token
- [ ] Same user force logout from other location works
- [ ] Max concurrent users (5) enforced
- [ ] Idle timeout (30 min) removes inactive sessions
- [ ] Active sessions preserved during timeout
- [ ] Full BI analysis works with session headers
- [ ] Baseline calculation with session headers
- [ ] Influence map with session headers
- [ ] Logout removes session properly
- [ ] Admin can update license limit with correct key
- [ ] Invalid admin key rejected
- [ ] /license/info shows correct information
- [ ] /sessions/active lists all users

---

## 🎉 System Ready!

Your industrial BI system is now fully licensed with:
- ✅ 5 concurrent user limit (configurable)
- ✅ Single session enforcement
- ✅ 30-minute idle timeout
- ✅ Zero hardcoding
- ✅ Zero lag performance
- ✅ Complete session isolation

**Next Steps:**
1. Install license: `POST /setup/install_license`
2. Integrate frontend login/logout
3. Test with multiple concurrent users
4. Deploy to production with HTTPS

For support or questions, refer to the source code documentation.
