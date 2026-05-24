# React + Flask HMI - Complete Production Deployment Guide

## 📋 Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Request Flow](#request-flow)
4. [Prerequisites](#prerequisites)
5. [Local Development Setup](#local-development-setup)
6. [Production Build Process](#production-build-process)
7. [Windows Production Deployment](#windows-production-deployment)
8. [Linux Production Deployment](#linux-production-deployment)
9. [nginx Configuration](#nginx-configuration)
10. [SSL/TLS Setup](#ssltls-setup)
11. [Testing & Verification](#testing--verification)
12. [Troubleshooting](#troubleshooting)

---

## 🏗️ Architecture Overview

### Production Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     HTTPS Production Stack                       │
└─────────────────────────────────────────────────────────────────┘

User Browser (Client)
       │
       │ HTTPS (443)
       ▼
┌──────────────────────────────────┐
│   nginx Reverse Proxy            │
│   • SSL/TLS Termination         │
│   • Serves React Static Files   │  ← apex-hmi/dist/
│   • Proxies API to Backend      │
│   • WebSocket Upgrade           │
└──────────────────────────────────┘
       │
       ├─────────────────┬───────────────────┬──────────────┐
       │                 │                   │              │
       │ Static          │ /api/*           │ /socket.io/* │
       ▼                 ▼                   ▼              │
┌──────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ React App    │  │ Flask Backend   │  │ Flask-SocketIO  │
│ (HTML/JS/CSS)│  │ Gunicorn/       │  │ Real-time       │
│              │  │ Waitress        │  │ WebSocket       │
│ apex-hmi/    │  │ Port 6001       │  │                 │
│ dist/        │  │                 │  │                 │
└──────────────┘  └─────────────────┘  └─────────────────┘
                         │
                         ├─────────┬──────────┬────────┐
                         ▼         ▼          ▼        ▼
                  ┌──────────┐ ┌─────┐  ┌─────────┐ ┌────┐
                  │PostgreSQL│ │MQTT │  │C# OPC   │ │Logs│
                  └──────────┘ └─────┘  └─────────┘ └────┘
```

### Key Architectural Principles

1. **Separation of Concerns**
   - React handles UI/UX in the browser
   - Flask handles business logic and data
   - nginx handles SSL, static files, and routing

2. **Single Domain Architecture**
   - Frontend and backend share same domain
   - No CORS issues
   - /api/* → Backend
   - Everything else → React

3. **WebSocket Real-Time Communication**
   - Persistent connection for live data
   - Bidirectional communication
   - MQTT → Flask → WebSocket → React

---

## 🔧 Technology Stack

### Frontend (Client-Side)
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **UI Components**: shadcn/ui + Radix UI
- **State Management**: React Query (TanStack)
- **HTTP Client**: Axios
- **WebSocket**: Socket.IO Client
- **Styling**: Tailwind CSS

### Backend (Server-Side)
- **Framework**: Flask 3.0
- **WSGI Server**: 
  - Gunicorn + eventlet (Linux)
  - Waitress (Windows)
- **WebSocket**: Flask-SocketIO
- **Database**: PostgreSQL with psycopg2
- **MQTT**: paho-mqtt
- **Authentication**: JWT with PyJWT

### Infrastructure
- **Reverse Proxy**: nginx
- **SSL/TLS**: Let's Encrypt (Certbot)
- **Process Manager**: 
  - systemd (Linux)
  - NSSM (Windows)
- **Monitoring**: Application logs with rotation

---

## 🔄 Request Flow

### 1. Initial Page Load
```
User → https://hmi.yourdomain.com/
  ↓
nginx serves: /opt/hmi/apex-hmi/dist/index.html
  ↓
Browser downloads: React app bundle (JS, CSS)
  ↓
React initializes in browser
  ↓
React establishes WebSocket connection
```

### 2. API Request Flow
```
React Component → axios.get('/api/tags/list')
  ↓
Request: https://hmi.yourdomain.com/api/tags/list
  ↓
nginx: location /api/ → proxy_pass http://127.0.0.1:6001/api/
  ↓
Gunicorn/Waitress → Flask app
  ↓
Flask controller → Service layer → Database
  ↓
Response: JSON data
  ↓
React updates state → UI re-renders
```

### 3. WebSocket Real-Time Data
```
React: socket.connect()
  ↓
Request: wss://hmi.yourdomain.com/socket.io/
  ↓
nginx: location /socket.io/ → WebSocket upgrade
  ↓
Flask-SocketIO: Persistent connection established
  ↓
MQTT publishes data → Flask receives
  ↓
Flask emits: socketio.emit('live_data', data)
  ↓
React receives: socket.on('live_data', callback)
  ↓
React updates UI in real-time
```

### 4. React Router Navigation (SPA)
```
User clicks link: /dashboard → /trends
  ↓
React Router handles navigation (no page reload)
  ↓
If user refreshes or direct URL access:
  https://hmi.yourdomain.com/trends
  ↓
nginx: try_files $uri $uri/ /index.html
  ↓
Serves index.html → React Router takes over
```

---

## ✅ Prerequisites

### Common Requirements
- **Python 3.8+** (Backend)
- **Node.js 18+** and npm (Frontend build)
- **PostgreSQL 12+** (Database)
- **MQTT Broker** (Mosquitto or similar)
- **Git** (Version control)

### Windows-Specific
- Python in PATH
- Node.js in PATH
- NSSM for Windows Service
- nginx for Windows (optional)

### Linux-Specific
- `sudo` privileges
- nginx (`sudo apt install nginx`)
- systemd (standard on modern distros)
- Build tools (`sudo apt install build-essential`)

---

## 🚀 Local Development Setup

### Start Backend (Flask)
```bash
cd HMI/
python -m venv venv
source venv/bin/activate  # Linux
venv\Scripts\activate     # Windows
pip install -r requirements.txt
python app.py
# Backend runs on http://localhost:6001
```

### Start Frontend (React)
```bash
cd apex-hmi/
npm install
npm run dev
# Frontend runs on http://localhost:5173
```

**Development Mode:**
- React dev server: `http://localhost:5173` (with hot reload)
- Flask backend: `http://localhost:6001`
- React makes API calls to Flask via CORS
- `.env.development` configures backend URL

---

## 📦 Production Build Process

### Full Stack Build
```bash
# Windows
deploy_fullstack_windows.bat

# Linux
chmod +x deploy_fullstack_linux.sh
./deploy_fullstack_linux.sh
```

This will:
1. **Build React** → `apex-hmi/dist/`
2. **Install Flask dependencies** → Production WSGI servers
3. **Configure environment** → Create `.env` file
4. **Start backend** → Test locally

### Manual Build Steps

**React Build:**
```bash
cd apex-hmi/
npm run build
# Creates optimized bundle in dist/
# - index.html
# - assets/index-[hash].js
# - assets/index-[hash].css
```

**Flask Setup:**
```bash
cd HMI/
pip install -r requirements-production.txt
cp .env.example .env
# Edit .env with production settings
```

---

## 🪟 Windows Production Deployment

### Step 1: Build Full Stack
```cmd
cd C:\Shakil\DJangoProjects\NEW_HMI\HMI
deploy_fullstack_windows.bat
```

### Step 2: Configure Environment
Edit `.env`:
```env
HMI_ENV=production
DEBUG=False
SECRET_KEY=your-production-secret-key
DB_PASSWORD=your-database-password
CORS_ORIGINS=https://hmi.yourdomain.com
```

### Step 3: Test Locally
```cmd
# Backend starts on http://localhost:6001
# React build served from apex-hmi/dist/
```

Visit: `http://localhost:6001`

### Step 4: Install as Windows Service
```cmd
# As Administrator
install_service_windows.bat
```

### Step 5: (Optional) nginx Setup

**Download nginx:**
- https://nginx.org/en/download.html
- Extract to `C:\nginx`

**Configure:**
```cmd
# Edit nginx.conf and update path:
# root C:/Shakil/DJangoProjects/NEW_HMI/HMI/apex-hmi/dist;

copy nginx.conf C:\nginx\conf\sites\hmi.conf
```

**Edit `C:\nginx\conf\nginx.conf`:**
```nginx
http {
    include sites/*.conf;
}
```

**Start nginx:**
```cmd
cd C:\nginx
start nginx.exe
```

---

## 🐧 Linux Production Deployment

### Step 1: Install System Dependencies
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm nginx postgresql git
```

### Step 2: Clone/Transfer Application
```bash
sudo mkdir -p /opt/hmi-flask
cd /opt/hmi-flask
# Transfer files or git clone
```

### Step 3: Build Full Stack
```bash
chmod +x deploy_fullstack_linux.sh
./deploy_fullstack_linux.sh
```

### Step 4: Configure Environment
```bash
nano .env
```

Update:
```env
HMI_ENV=production
DEBUG=False
SECRET_KEY=your-production-secret-key
DB_PASSWORD=your-database-password
CORS_ORIGINS=https://hmi.yourdomain.com
```

### Step 5: Install systemd Service
```bash
sudo ./install_service_linux.sh
```

This creates and starts:
- Service: `hmi-flask.service`
- Running on: `http://localhost:6001`

### Step 6: Configure nginx

**Copy configuration:**
```bash
sudo cp nginx.conf /etc/nginx/sites-available/hmi-flask
```

**Edit paths:**
```bash
sudo nano /etc/nginx/sites-available/hmi-flask
```

Update:
```nginx
root /opt/hmi-flask/HMI/apex-hmi/dist;
```

**Enable site:**
```bash
sudo ln -s /etc/nginx/sites-available/hmi-flask /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 🌐 nginx Configuration

### Key Configuration Sections

#### 1. React Static Files
```nginx
location / {
    root /opt/hmi-flask/HMI/apex-hmi/dist;
    try_files $uri $uri/ /index.html;  # SPA routing support
}
```

#### 2. React Build Assets (Cached)
```nginx
location /assets/ {
    alias /opt/hmi-flask/HMI/apex-hmi/dist/assets/;
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

#### 3. API Proxy to Flask
```nginx
location /api/ {
    proxy_pass http://127.0.0.1:6001/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

#### 4. WebSocket Proxy
```nginx
location /socket.io/ {
    proxy_pass http://127.0.0.1:6001/socket.io/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### URL Routing Table

| URL | Handler | Description |
|-----|---------|-------------|
| `/` | nginx → React index.html | Main entry point |
| `/dashboard` | nginx → React (SPA) | React Router handles |
| `/assets/*` | nginx → Static files | JS, CSS, cached 1 year |
| `/api/*` | nginx → Flask:6001 | REST API endpoints |
| `/socket.io/*` | nginx → Flask:6001 | WebSocket connection |

---

## 🔒 SSL/TLS Setup

### Let's Encrypt (Free, Automated - Linux)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d hmi.yourdomain.com

# Auto-renewal (test)
sudo certbot renew --dry-run
```

Certbot automatically:
- Updates nginx configuration
- Adds SSL certificates
- Sets up auto-renewal cron job

### Manual SSL Certificate

1. Place certificates:
   ```
   /etc/ssl/certs/hmi.yourdomain.com.crt
   /etc/ssl/private/hmi.yourdomain.com.key
   ```

2. Update nginx.conf:
   ```nginx
   ssl_certificate /etc/ssl/certs/hmi.yourdomain.com.crt;
   ssl_certificate_key /etc/ssl/private/hmi.yourdomain.com.key;
   ```

3. Restart nginx:
   ```bash
   sudo nginx -t
   sudo systemctl restart nginx
   ```

---

## ✅ Testing & Verification

### 1. Backend Health Check
```bash
curl http://localhost:6001/api/system/health
# Expected: {"status":"healthy","uptime":123}
```

### 2. React Build Verification
```bash
ls -lh apex-hmi/dist/
# Should see:
# index.html
# assets/index-[hash].js
# assets/index-[hash].css
```

### 3. nginx Configuration Test
```bash
sudo nginx -t
# Expected: syntax is ok, test is successful
```

### 4. Full Stack Test
```bash
# Access via nginx
curl -I https://hmi.yourdomain.com
# Expected: 200 OK, served from nginx

# Test API
curl https://hmi.yourdomain.com/api/system/health
# Expected: JSON response from Flask

# Test React
curl https://hmi.yourdomain.com/dashboard
# Expected: HTML (index.html served by nginx)
```

### 5. WebSocket Test (Browser Console)
```javascript
// Open https://hmi.yourdomain.com in browser
// F12 → Console

// Check Socket.IO connection
if (typeof socket !== 'undefined') {
    console.log('Connected:', socket.connected);
} else {
    console.log('Socket.IO not loaded');
}
```

### 6. Performance Test
```bash
# Check React bundle size
du -sh apex-hmi/dist/
# Should be < 5MB for production build

# Check backend response time
time curl https://hmi.yourdomain.com/api/tags/list
```

---

## 🔧 Troubleshooting

### Issue: React App Shows Blank Page

**Symptoms:**
- Browser shows white screen
- Network tab shows 404 for assets

**Solutions:**
1. Verify React build exists:
   ```bash
   ls apex-hmi/dist/index.html
   ```

2. Check nginx root path:
   ```bash
   sudo nginx -T | grep "root"
   # Should match: /opt/hmi-flask/HMI/apex-hmi/dist
   ```

3. Check file permissions:
   ```bash
   sudo chmod -R 755 /opt/hmi-flask/HMI/apex-hmi/dist
   ```

4. Check nginx error log:
   ```bash
   sudo tail -f /var/log/nginx/error.log
   ```

### Issue: API Calls Return 502 Bad Gateway

**Symptoms:**
- React loads but API calls fail
- nginx error: "Connection refused"

**Solutions:**
1. Check backend is running:
   ```bash
   sudo systemctl status hmi-flask
   curl http://localhost:6001/api/system/health
   ```

2. Check backend logs:
   ```bash
   sudo journalctl -u hmi-flask -n 50
   tail -f /opt/hmi-flask/HMI/logs/hmi_app.log
   ```

3. Verify port 6001 is listening:
   ```bash
   sudo netstat -tlnp | grep 6001
   ```

### Issue: WebSocket Connection Fails

**Symptoms:**
- Real-time updates don't work
- Browser console: "WebSocket connection failed"

**Solutions:**
1. Check nginx WebSocket config:
   ```bash
   sudo nginx -T | grep -A 5 "socket.io"
   # Must have: proxy_set_header Upgrade $http_upgrade
   ```

2. Test WebSocket directly:
   ```bash
   curl -i -N -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     http://localhost:6001/socket.io/
   ```

3. Check Flask-SocketIO logs:
   ```bash
   sudo journalctl -u hmi-flask | grep socket
   ```

### Issue: React Router Routes Return 404

**Symptoms:**
- Direct URL access (e.g., /dashboard) returns 404
- Works when navigating from home page

**Solution:**
Verify nginx try_files directive:
```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

### Issue: CORS Errors in Console

**Symptom:**
- "Access-Control-Allow-Origin" error

**Solution:**
Should NOT happen in production (same domain). If it does:
1. Verify API calls use relative paths (`/api/` not `http://localhost:6001/api/`)
2. Check React `.env.production`:
   ```env
   VITE_API_BASE_URL=/api
   ```

### Issue: Slow Initial Load

**Solutions:**
1. Enable gzip in nginx (already in config)
2. Check bundle size:
   ```bash
   du -sh apex-hmi/dist/assets/*.js
   ```
3. Consider code splitting in React
4. Enable nginx caching for static assets

---

## 📊 Performance Optimization

### React Build Optimization
- Tree shaking (automatic with Vite)
- Minification (automatic in production)
- Code splitting by route
- Lazy loading components

### nginx Optimization
- Gzip compression (enabled in config)
- Static asset caching (1 year for /assets/)
- Connection keep-alive
- HTTP/2 enabled

### Backend Optimization
- Database connection pooling
- Redis caching (optional)
- Rate limiting in nginx
- Efficient MQTT handling

---

## 📁 Directory Structure (Production)

```
/opt/hmi-flask/HMI/
├── apex-hmi/                        # React Frontend
│   ├── src/                         # Source code (dev only)
│   ├── dist/                        # Production build ← nginx serves this
│   │   ├── index.html
│   │   └── assets/
│   │       ├── index-abc123.js
│   │       └── index-xyz789.css
│   ├── .env.production              # React production config
│   └── package.json
│
├── app_factory.py                   # Flask application factory
├── wsgi.py                          # WSGI entry point
├── config_manager.py                # Environment config
├── .env                             # Backend secrets
├── requirements-production.txt
├── nginx.conf                       # nginx configuration
│
├── controllers/                     # Flask API endpoints
├── services/                        # Business logic
├── logs/                            # Application logs
│
├── deploy_fullstack_windows.bat     # Full deployment (Windows)
├── deploy_fullstack_linux.sh        # Full deployment (Linux)
├── build_react_windows.bat          # React build only
└── build_react_linux.sh             # React build only
```

---

## 🎓 Best Practices

1. **Always build React for production** (`npm run build`)
2. **Never serve React dev server in production**
3. **Use environment variables** for configuration
4. **Enable HTTPS in production** (Let's Encrypt)
5. **Implement rate limiting** in nginx
6. **Monitor logs regularly**
7. **Set up automated backups** (database + .env)
8. **Keep dependencies updated**
9. **Test in staging before production**
10. **Use systemd/Windows Service** (don't run manually)

---

## 📞 Support Resources

- **Flask**: https://flask.palletsprojects.com/
- **Flask-SocketIO**: https://flask-socketio.readthedocs.io/
- **React**: https://react.dev/
- **Vite**: https://vitejs.dev/
- **nginx**: https://nginx.org/en/docs/
- **Gunicorn**: https://docs.gunicorn.org/

---

**Version:** 1.0.0  
**Last Updated:** February 21, 2026  
**Architecture:** React (Vite) + Flask + nginx
