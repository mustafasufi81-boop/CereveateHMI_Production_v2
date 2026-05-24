# HMI Flask Application - Production Deployment Guide

## 📋 Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Windows Production Deployment](#windows-production-deployment)
6. [Linux Production Deployment](#linux-production-deployment)
7. [Nginx Reverse Proxy Setup](#nginx-reverse-proxy-setup)
8. [SSL/TLS Configuration](#ssltls-configuration)
9. [Monitoring & Logging](#monitoring--logging)
10. [Security Hardening](#security-hardening)
11. [Troubleshooting](#troubleshooting)
12. [Performance Tuning](#performance-tuning)

---

## 🎯 Overview

This guide provides comprehensive instructions for deploying the HMI Flask Application to production environments on both Windows and Linux platforms.

### Key Features of Production Setup
- ✅ **Production WSGI Servers**: Gunicorn (Linux) / Waitress (Windows)
- ✅ **Environment-Based Configuration**: Separate dev/staging/production configs
- ✅ **Process Management**: systemd (Linux) / Windows Service (Windows)
- ✅ **Reverse Proxy**: nginx with SSL/TLS support
- ✅ **WebSocket Support**: Real-time bidirectional communication
- ✅ **Monitoring & Logging**: Structured logging with rotation
- ✅ **Security Hardening**: Best practices implemented
- ✅ **Auto-Restart**: Service management with automatic recovery

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Production Stack                        │
└─────────────────────────────────────────────────────────────┘

Internet/Clients
       │
       ▼
┌──────────────┐
│    nginx     │  ← Reverse Proxy (SSL/TLS, Load Balancing)
│   (Port 80)  │     Rate Limiting, Static Files
│  (Port 443)  │
└──────────────┘
       │
       ▼
┌──────────────┐
│  Gunicorn/   │  ← WSGI Server (Production)
│  Waitress    │     WebSocket Support (eventlet/gevent)
│  (Port 6001) │
└──────────────┘
       │
       ▼
┌──────────────┐
│ Flask App    │  ← Application Factory (app_factory.py)
│ (SocketIO)   │     Business Logic, APIs, WebSocket Events
└──────────────┘
       │
       ├─────────────────┬────────────────┬──────────────┐
       ▼                 ▼                ▼              ▼
┌──────────┐   ┌─────────────┐   ┌──────────┐   ┌──────────┐
│PostgreSQL│   │  MQTT Broker│   │ C# OPC   │   │File Logs │
│(Port5432)│   │  (Port 1883)│   │ SignalR  │   │          │
└──────────┘   └─────────────┘   └──────────┘   └──────────┘
```

---

## ✅ Prerequisites

### Common Requirements (All Platforms)
- Python 3.8 or higher
- PostgreSQL 12+ database
- MQTT Broker (Mosquitto or similar)
- Git (for version control)

### Windows-Specific
- Python installed and added to PATH
- NSSM (Non-Sucking Service Manager) for Windows Service
- nginx for Windows (optional but recommended)

### Linux-Specific
- systemd (standard on modern Linux distributions)
- nginx
- `sudo` privileges for service installation

---

## 🚀 Quick Start

### Test Locally (Development Mode)

**Windows:**
```cmd
cd C:\Shakil\DJangoProjects\NEW_HMI\HMI
start_dev.bat
```

**Linux:**
```bash
cd /path/to/NEW_HMI/HMI
chmod +x start_dev.sh
./start_dev.sh
```

Visit: http://localhost:6001

---

## 🪟 Windows Production Deployment

### Step 1: Prepare Environment

```cmd
cd C:\Shakil\DJangoProjects\NEW_HMI\HMI
```

### Step 2: Install Dependencies and Configure

```cmd
deploy_windows.bat
```

This script will:
1. Create virtual environment
2. Install production dependencies (Waitress, etc.)
3. Create `.env` from template
4. Validate configuration
5. Start server (for testing)

### Step 3: Configure Environment Variables

Edit `.env` file:
```env
HMI_ENV=production
DEBUG=False
SECRET_KEY=your-super-secret-production-key-change-this
DB_PASSWORD=your-secure-database-password
CORS_ORIGINS=https://yourdomain.com
```

### Step 4: Test Production Server

```cmd
deploy_windows.bat
```

Verify it starts correctly on http://localhost:6001

### Step 5: Install as Windows Service

**Option A: Using NSSM (Recommended)**

1. Download NSSM from https://nssm.cc/download
2. Extract to `C:\Tools\nssm\`
3. Run as Administrator:

```cmd
install_service_windows.bat
```

**Option B: Manual NSSM Configuration**

```cmd
nssm install HMI_Flask_Service "C:\Shakil\DJangoProjects\NEW_HMI\HMI\venv\Scripts\python.exe" ^
    -m waitress --host=0.0.0.0 --port=6001 --threads=6 wsgi:application
```

### Step 6: Manage Windows Service

```cmd
# Start
net start HMI_Flask_Service

# Stop
net stop HMI_Flask_Service

# Check status
sc query HMI_Flask_Service

# View logs
type logs\service-stdout.log
```

### Step 7: (Optional) Set Up nginx

1. Download nginx for Windows: http://nginx.org/en/download.html
2. Extract to `C:\nginx`
3. Copy `nginx.conf` to `C:\nginx\conf\sites\hmi.conf`
4. Update `C:\nginx\conf\nginx.conf` to include:
   ```nginx
   include sites/*.conf;
   ```
5. Start nginx:
   ```cmd
   cd C:\nginx
   nginx.exe
   ```

---

## 🐧 Linux Production Deployment

### Step 1: Prepare System

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3 python3-pip python3-venv nginx postgresql git

# Install MQTT broker (optional)
sudo apt install -y mosquitto mosquitto-clients
```

### Step 2: Clone or Transfer Application

```bash
# Create application directory
sudo mkdir -p /opt/hmi-flask
cd /opt/hmi-flask

# Transfer files or clone from git
# git clone https://github.com/yourusername/hmi-flask.git .
```

### Step 3: Run Deployment Script

```bash
chmod +x deploy_linux.sh
./deploy_linux.sh
```

This will:
1. Create virtual environment
2. Install Gunicorn with eventlet
3. Create `.env` from template
4. Validate configuration
5. Start server (for testing)

### Step 4: Configure Environment Variables

```bash
nano .env
```

Update production settings:
```env
HMI_ENV=production
DEBUG=False
SECRET_KEY=your-super-secret-production-key
DB_PASSWORD=your-secure-database-password
CORS_ORIGINS=https://yourdomain.com
```

### Step 5: Install as systemd Service

```bash
# Run as root or with sudo
sudo ./install_service_linux.sh
```

Follow the prompts to configure:
- Installation path (default: /home/hmi/NEW_HMI/HMI)
- Service user (default: hmi)

### Step 6: Manage systemd Service

```bash
# Start service
sudo systemctl start hmi-flask

# Stop service
sudo systemctl stop hmi-flask

# Restart service
sudo systemctl restart hmi-flask

# Check status
sudo systemctl status hmi-flask

# Enable auto-start on boot
sudo systemctl enable hmi-flask

# View logs (real-time)
sudo journalctl -u hmi-flask -f

# View logs (last 100 lines)
sudo journalctl -u hmi-flask -n 100
```

### Step 7: Configure nginx

```bash
# Copy nginx configuration
sudo cp nginx.conf /etc/nginx/sites-available/hmi-flask

# Update configuration (change domain name)
sudo nano /etc/nginx/sites-available/hmi-flask

# Enable site
sudo ln -s /etc/nginx/sites-available/hmi-flask /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

---

## 🌐 Nginx Reverse Proxy Setup

### Basic Configuration (HTTP Only - Development/Testing)

```nginx
server {
    listen 80;
    server_name hmi.yourdomain.com;
    
    location / {
        proxy_pass http://127.0.0.1:6001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    location /socket.io/ {
        proxy_pass http://127.0.0.1:6001/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### SSL/TLS Configuration (Production)

See included `nginx.conf` for complete HTTPS configuration.

---

## 🔒 SSL/TLS Configuration

### Option 1: Let's Encrypt (Free, Automated)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate (interactive)
sudo certbot --nginx -d hmi.yourdomain.com

# Auto-renewal is set up automatically
# Test renewal:
sudo certbot renew --dry-run
```

### Option 2: Commercial Certificate

1. Obtain SSL certificate from provider
2. Place files:
   - `/etc/ssl/certs/hmi.yourdomain.com.crt`
   - `/etc/ssl/private/hmi.yourdomain.com.key`
3. Update nginx.conf:
   ```nginx
   ssl_certificate /etc/ssl/certs/hmi.yourdomain.com.crt;
   ssl_certificate_key /etc/ssl/private/hmi.yourdomain.com.key;
   ```

### Option 3: Self-Signed (Testing Only)

```bash
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/hmi-selfsigned.key \
    -out /etc/ssl/certs/hmi-selfsigned.crt
```

---

## 📊 Monitoring & Logging

### Application Logs

**Location:**
- Windows: `C:\Shakil\DJangoProjects\NEW_HMI\HMI\logs\`
- Linux: `/opt/hmi-flask/logs/`

**Log Files:**
- `hmi_app.log` - General application log (5 MB rotation)
- `hmi_errors.log` - Error-only log
- `hmi_daily.log` - Daily rotating log (30-day retention)
- `gunicorn-access.log` - HTTP access log (Linux)
- `gunicorn-error.log` - WSGI server errors (Linux)
- `service-stdout.log` - Service stdout (Windows)

### Real-Time Log Monitoring

**Linux:**
```bash
# Application logs
tail -f /opt/hmi-flask/logs/hmi_app.log

# Service logs
sudo journalctl -u hmi-flask -f

# nginx logs
sudo tail -f /var/log/nginx/hmi-access.log
```

**Windows:**
```cmd
# PowerShell
Get-Content logs\hmi_app.log -Wait -Tail 50
```

### Health Check Endpoint

Check if application is running:
```bash
curl http://localhost:6001/api/system/health
```

Expected response:
```json
{
    "status": "healthy",
    "uptime": 3600,
    "version": "1.0.0"
}
```

---

## 🔐 Security Hardening

### 1. Environment Variables

**Never commit sensitive data!**
- Add `.env` to `.gitignore`
- Use strong, unique passwords
- Rotate secrets regularly

### 2. Database Security

```sql
-- Create dedicated database user
CREATE USER hmi_app WITH PASSWORD 'strong-password-here';
GRANT CONNECT ON DATABASE Cereveate TO hmi_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO hmi_app;
```

### 3. Firewall Configuration

**Linux (UFW):**
```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Block direct access to Flask (if behind nginx)
sudo ufw deny 6001/tcp

# Enable firewall
sudo ufw enable
```

**Windows Firewall:**
```cmd
# Allow inbound on port 6001 (if not using nginx)
netsh advfirewall firewall add rule name="HMI Flask" dir=in action=allow protocol=TCP localport=6001
```

### 4. Rate Limiting (nginx)

Add to nginx.conf:
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;

location /api/auth/login {
    limit_req zone=login_limit burst=3 nodelay;
    proxy_pass http://hmi_backend;
}
```

### 5. HTTPS Only (Production)

Force HTTPS redirects in nginx:
```nginx
server {
    listen 80;
    return 301 https://$server_name$request_uri;
}
```

---

## 🔧 Troubleshooting

### Service Won't Start

**Check logs:**
```bash
# Linux
sudo journalctl -u hmi-flask -n 50

# Windows
type logs\service-stderr.log
```

**Common issues:**
1. Port already in use: `netstat -ano | findstr :6001` (Windows) or `sudo lsof -i :6001` (Linux)
2. Missing dependencies: Reinstall `pip install -r requirements-production.txt`
3. Database connection: Check PostgreSQL is running and credentials in `.env`
4. Missing .env file: Copy from `.env.example`

### WebSocket Connection Fails

1. **Check nginx WebSocket configuration:**
   ```nginx
   proxy_http_version 1.1;
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection "upgrade";
   ```

2. **Verify eventlet worker:**
   ```bash
   # Should show eventlet worker
   ps aux | grep gunicorn
   ```

3. **Test direct connection (bypass nginx):**
   ```
   http://localhost:6001
   ```

### High Memory Usage

1. **Reduce worker processes:**
   - Gunicorn: `--workers 1` (for eventlet)
   - Waitress: `--threads 4`

2. **Database connection pooling:**
   ```env
   DB_POOL_MIN=2
   DB_POOL_MAX=5
   ```

### Permission Errors (Linux)

```bash
# Fix ownership
sudo chown -R hmi:hmi /opt/hmi-flask

# Fix log directory permissions
sudo chmod 755 /opt/hmi-flask/logs
```

---

## ⚡ Performance Tuning

### 1. Database Optimization

**Connection Pooling:**
```env
DB_POOL_MIN=5
DB_POOL_MAX=20
```

**PostgreSQL Configuration:**
```sql
-- Increase shared buffers
shared_buffers = 256MB

-- Increase work memory
work_mem = 16MB

-- Enable query planner statistics
max_connections = 100
```

### 2. Gunicorn/Waitress Tuning

**Gunicorn (Linux):**
```bash
gunicorn \
    --worker-class eventlet \
    --workers 1 \
    --worker-connections 1000 \
    --timeout 120 \
    --keepalive 5
```

**Waitress (Windows):**
```cmd
waitress-serve --threads=8 --channel-timeout=120 --connection-limit=1000
```

### 3. nginx Caching

```nginx
# Cache static files
location /static/ {
    expires 30d;
    add_header Cache-Control "public, immutable";
}

# Enable gzip compression
gzip on;
gzip_types text/plain text/css application/json application/javascript;
```

### 4. Redis Caching (Optional Enhancement)

Install Redis for session storage and caching:
```bash
sudo apt install redis-server
pip install redis flask-session
```

---

## 🎓 Best Practices

1. **Always use environment variables for secrets**
2. **Enable HTTPS in production**
3. **Implement rate limiting**
4. **Monitor logs regularly**
5. **Set up automated backups**
6. **Keep dependencies updated** (`pip list --outdated`)
7. **Test deployment in staging first**
8. **Document custom configurations**
9. **Use version control (Git)**
10. **Implement monitoring/alerting**

---

## 📞 Support

For issues or questions:
- Check logs first
- Review this documentation
- Consult Flask-SocketIO docs: https://flask-socketio.readthedocs.io/
- Gunicorn docs: https://docs.gunicorn.org/
- nginx docs: https://nginx.org/en/docs/

---

## 📄 License

[Your License Here]

---

**Last Updated:** February 21, 2026
**Version:** 1.0.0
