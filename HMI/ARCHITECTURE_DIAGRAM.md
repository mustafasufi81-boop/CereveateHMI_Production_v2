# Production Architecture - React + Flask HMI System

## 🎯 Complete System Overview

This document provides a comprehensive view of the production architecture for the Industrial HMI system using React frontend and Flask backend.

---

## 📐 System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                    PRODUCTION DEPLOYMENT STACK                        │
└──────────────────────────────────────────────────────────────────────┘

LAYER 1: CLIENT (Browser)
─────────────────────────────────
┌─────────────────────────────────────────────────┐
│          User's Web Browser                     │
│  ┌───────────────────────────────────────────┐  │
│  │  React Application (SPA)                  │  │
│  │  • React 18 + TypeScript                  │  │
│  │  • Vite Build Tool                        │  │
│  │  • shadcn/ui Components                   │  │
│  │  • Axios (HTTP Client)                    │  │
│  │  • Socket.IO Client (WebSocket)           │  │
│  │  • React Query (State Management)         │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │ HTTPS (443)
         │ • REST API calls (/api/*)
         │ • WebSocket (/socket.io/*)
         ▼

LAYER 2: REVERSE PROXY & LOAD BALANCER
─────────────────────────────────────────
┌─────────────────────────────────────────────────┐
│              nginx (Port 80/443)                 │
│  ┌───────────────────────────────────────────┐  │
│  │  SSL/TLS Termination                      │  │
│  │  • Let's Encrypt Certificates             │  │
│  │  • TLS 1.2/1.3                           │  │
│  │  • HTTP/2 Support                         │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Routing Logic:                           │  │
│  │  ✓ /              → React dist/           │  │
│  │  ✓ /dashboard     → React (SPA routing)   │  │
│  │  ✓ /assets/*      → Static files (cached) │  │
│  │  ✓ /api/*         → Proxy to Flask:6001   │  │
│  │  ✓ /socket.io/*   → WebSocket to :6001    │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Security Features:                       │  │
│  │  • Rate Limiting                          │  │
│  │  • Security Headers (HSTS, CSP, etc.)    │  │
│  │  • Gzip Compression                       │  │
│  │  • DDoS Protection                        │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │
         ├──────────────┬──────────────┬─────────────┐
         │              │              │             │
         │ Static       │ API          │ WebSocket   │
         ▼              ▼              ▼             │

┌──────────────┐  ┌─────────────────────────────────────┐
│ React Build  │  │    WSGI Application Server          │
│              │  │  ┌─────────────────────────────┐    │
│ apex-hmi/    │  │  │ Gunicorn (Linux)            │    │
│ dist/        │  │  │ or Waitress (Windows)       │    │
│              │  │  │ • Port 6001                 │    │
│ index.html   │  │  │ • eventlet/gevent workers   │    │
│ assets/      │  │  │ • WebSocket support         │    │
│  ├─ JS       │  │  └─────────────────────────────┘    │
│  ├─ CSS      │  └─────────────────────────────────────┘
│  └─ Images   │              │
└──────────────┘              │
                              ▼

LAYER 3: APPLICATION SERVER
─────────────────────────────────────────
┌─────────────────────────────────────────────────┐
│         Flask Application (Python)               │
│  ┌───────────────────────────────────────────┐  │
│  │  Flask Core                               │  │
│  │  • RESTful API Endpoints                  │  │
│  │  • JWT Authentication                     │  │
│  │  • RBAC Authorization                     │  │
│  │  • Session Management                     │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Flask-SocketIO                           │  │
│  │  • Real-time WebSocket Events             │  │
│  │  • Bidirectional Communication            │  │
│  │  • Event Broadcasting                     │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Business Logic Layer                     │  │
│  │  • Tag Management Service                 │  │
│  │  • Alarm Processing Service               │  │
│  │  • Historical Data Service                │  │
│  │  • User Management Service                │  │
│  │  • MQTT Client Service                    │  │
│  │  • SignalR Listener Service               │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │
         ├─────────────┬──────────────┬──────────────┬─────────┐
         ▼             ▼              ▼              ▼         ▼

LAYER 4: DATA SOURCES & EXTERNAL SERVICES
─────────────────────────────────────────────────
┌──────────────┐ ┌─────────────┐ ┌──────────────┐ ┌────────┐ ┌────────┐
│ PostgreSQL   │ │ MQTT Broker │ │ C# OPC/      │ │ File   │ │ Cache  │
│ Database     │ │             │ │ SignalR      │ │ Storage│ │(Redis) │
│              │ │ Mosquitto   │ │ Service      │ │        │ │Optional│
│ • Tag Master │ │ Port 1883   │ │              │ │ Logs/  │ │        │
│ • Historian  │ │             │ │ • PLC Data   │ │ Exports│ │Session │
│ • Alarms     │ │ • Live Data │ │ • Real-time  │ │ CSV/   │ │Storage │
│ • Users      │ │ • Events    │ │ • OPC Tags   │ │ JSON   │ │        │
│ • Audit Log  │ │ • Alarms    │ │              │ │        │ │        │
│ Port 5432    │ │             │ │ Port 5001    │ │        │ │        │
└──────────────┘ └─────────────┘ └──────────────┘ └────────┘ └────────┘
```

---

## 🔄 Data Flow Scenarios

### Scenario 1: User Login
```
1. User enters credentials in React form
2. React: axios.post('/api/auth/login', {username, password})
3. HTTPS → nginx → Flask backend
4. Flask: Verify credentials → Generate JWT token
5. Response: {token, user_info}
6. React: Store token in memory/localStorage
7. React: Include token in all subsequent API requests
```

### Scenario 2: Real-Time Tag Data Update
```
1. PLC/OPC → C# Service → MQTT Broker
2. MQTT publishes on topic: "data/turbine1"
3. Flask MQTT Client subscribes and receives message
4. Flask: Process data, apply business logic
5. Flask-SocketIO: socketio.emit('live_data', processed_data)
6. All connected browsers receive update via WebSocket
7. React: socket.on('live_data', data => updateState(data))
8. React: Re-render components with new data
```

### Scenario 3: Historical Trend Query
```
1. User selects date range in React Trends component
2. React: axios.get('/api/historical', {params: {start, end, tag_id}})
3. nginx → Flask backend
4. Flask: Query PostgreSQL historian table
5. Flask: Format data, apply sampling if needed
6. Response: JSON array of time-series data
7. React: Render chart using charting library
```

### Scenario 4: Alarm Acknowledgment
```
1. User clicks "Acknowledge" on alarm in React UI
2. React: axios.post('/api/alarms/:id/acknowledge')
3. Request includes JWT token in Authorization header
4. nginx → Flask backend
5. Flask: Verify JWT, check RBAC permissions
6. Flask: Update alarm status in database
7. Flask: Emit WebSocket event to all clients
8. All browsers update alarm display in real-time
9. Flask: Write audit log entry
```

---

## 🌐 Network & Port Configuration

### Production Ports

| Service | Port | Protocol | Access |
|---------|------|----------|--------|
| nginx | 80 | HTTP | Public (redirects to HTTPS) |
| nginx | 443 | HTTPS | Public |
| Flask Backend | 6001 | HTTP | Localhost only |
| PostgreSQL | 5432 | TCP | Localhost only |
| MQTT Broker | 1883 | TCP | Internal network |
| C# OPC Service | 5001 | HTTP | Internal network |

### Firewall Rules (Linux)

```bash
# Allow incoming HTTPS
sudo ufw allow 443/tcp

# Allow incoming HTTP (for Let's Encrypt)
sudo ufw allow 80/tcp

# Allow SSH (for administration)
sudo ufw allow 22/tcp

# Block direct access to backend (nginx only)
sudo ufw deny 6001/tcp

# Enable firewall
sudo ufw enable
```

---

## 📂 File System Layout (Linux Production)

```
/opt/hmi-flask/
├── HMI/
│   ├── apex-hmi/
│   │   ├── dist/                    ← nginx root (React build)
│   │   │   ├── index.html
│   │   │   └── assets/
│   │   │       ├── index-[hash].js
│   │   │       └── index-[hash].css
│   │   ├── src/                     (dev only, not needed in prod)
│   │   ├── .env.production         ← React production config
│   │   ├── .env.development        ← React dev config
│   │   └── package.json
│   │
│   ├── app_factory.py
│   ├── wsgi.py                     ← Gunicorn entry point
│   ├── config_manager.py
│   ├── .env                        ← Flask secrets (NEVER commit!)
│   ├── requirements-production.txt
│   │
│   ├── controllers/                ← Flask API endpoints
│   │   ├── auth_controller.py      → /api/auth/*
│   │   ├── tag_controller.py       → /api/tags/*
│   │   ├── alarm_controller.py     → /api/alarms/*
│   │   └── historical_controller.py → /api/historical/*
│   │
│   ├── services/
│   │   ├── mqtt_client_service.py
│   │   ├── signalr_listener.py
│   │   └── tag_cache.py
│   │
│   ├── logs/                       ← Application logs
│   │   ├── hmi_app.log
│   │   ├── hmi_errors.log
│   │   └── gunicorn-access.log
│   │
│   └── venv/                       ← Python virtual environment
│
├── nginx.conf                       → Copy to /etc/nginx/sites-available/
└── hmi-flask.service               → Copy to /etc/systemd/system/

/etc/nginx/
├── sites-available/
│   └── hmi-flask                   ← nginx configuration
└── sites-enabled/
    └── hmi-flask -> ../sites-available/hmi-flask

/etc/systemd/system/
└── hmi-flask.service               ← systemd service unit

/var/log/nginx/
├── hmi-access.log                  ← nginx access logs
└── hmi-error.log                   ← nginx error logs
```

---

## 🔐 Security Architecture

### Layer 1: Network Security (nginx)
- **SSL/TLS**: TLS 1.2+ with strong ciphers
- **HSTS**: Force HTTPS for all requests
- **Rate Limiting**: Prevent brute force attacks
- **Request Size Limits**: Prevent DoS
- **Security Headers**: XSS, clickjacking protection

### Layer 2: Application Security (Flask)
- **JWT Authentication**: Stateless token-based auth
- **RBAC**: Role-based access control
- **Input Validation**: Sanitize all inputs
- **SQL Injection Protection**: ORM/parameterized queries
- **Session Management**: Secure session handling

### Layer 3: Database Security
- **Dedicated User**: Limited permissions
- **Connection Pooling**: Prevent connection exhaustion
- **Encrypted Passwords**: bcrypt hashing
- **Audit Logging**: Track all changes

### Layer 4: Infrastructure Security
- **Firewall**: UFW/iptables rules
- **Service Isolation**: Backend not directly accessible
- **Log Monitoring**: Regular log review
- **Automated Backups**: Data protection

---

## ⚡ Performance Optimization

### Frontend (React)
- **Code Splitting**: Load only needed components
- **Lazy Loading**: Defer non-critical resources
- **Tree Shaking**: Remove unused code
- **Minification**: Reduce bundle size
- **CDN**: Serve static assets from CDN (optional)

### nginx
- **Gzip Compression**: Reduce bandwidth
- **Static Asset Caching**: 1 year cache for /assets/
- **Connection Keep-Alive**: Reuse connections
- **HTTP/2**: Multiplexing, server push

### Backend (Flask)
- **Database Connection Pooling**: Reuse connections
- **Async Processing**: eventlet/gevent workers
- **Caching**: Redis for session/frequently accessed data
- **Query Optimization**: Indexed database queries

### Database (PostgreSQL)
- **Indexes**: On frequently queried columns
- **VACUUM**: Regular maintenance
- **Connection Limits**: Prevent resource exhaustion
- **Query Performance Analysis**: EXPLAIN plans

---

## 📊 Monitoring & Observability

### Application Metrics
- Request rate (requests/second)
- Response time (p50, p95, p99)
- Error rate (5xx errors)
- WebSocket connection count
- Database query performance

### Infrastructure Metrics
- CPU usage
- Memory usage
- Disk I/O
- Network bandwidth
- Open file descriptors

### Log Aggregation
```bash
# Application logs
/opt/hmi-flask/HMI/logs/

# System logs
sudo journalctl -u hmi-flask -f

# nginx logs
/var/log/nginx/hmi-*.log
```

### Health Check Endpoints
```
GET /api/system/health
Response: {"status": "healthy", "uptime": 3600}

GET /api/system/metrics (optional)
Response: {cpu: 25%, memory: 45%, connections: 150}
```

---

## 🔄 Deployment Workflow

### Development → Staging → Production

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Development  │────▶│   Staging    │────▶│ Production   │
│ localhost    │     │ staging.hmi  │     │ hmi.yourdomain│
└──────────────┘     └──────────────┘     └──────────────┘
      │                     │                     │
      │                     │                     │
   Feature              Full System         Live Users
   Development          Testing            +Monitoring
```

### CI/CD Pipeline (Recommended)
1. Git commit/push
2. Automated tests (unit, integration)
3. Build React bundle
4. Deploy to staging
5. Smoke tests
6. Manual approval
7. Deploy to production
8. Health check verification

---

## 🎓 Summary

**This architecture provides:**

✅ **Separation of Concerns**: React (UI) ↔ Flask (API) ↔ Data Sources  
✅ **Scalability**: nginx load balancing, multiple workers  
✅ **Security**: HTTPS, JWT, RBAC, rate limiting  
✅ **Performance**: Caching, compression, connection pooling  
✅ **Reliability**: Process management, auto-restart, logging  
✅ **Real-Time**: WebSocket for live data updates  
✅ **Maintainability**: Clear structure, logging, monitoring  

**Key Technologies:**
- **Frontend**: React 18 + Vite + TypeScript
- **Backend**: Flask + Gunicorn/Waitress
- **Proxy**: nginx with SSL/TLS
- **Database**: PostgreSQL
- **Real-Time**: MQTT + Flask-SocketIO
- **Process**: systemd (Linux) / NSSM (Windows)

---

**Version:** 1.0.0  
**Date:** February 21, 2026  
**Architecture Type:** Microservices with SPA Frontend
