# MQTT Subscriber Service

Enterprise-grade MQTT Subscriber Service with comprehensive audit trails, tag validation, and OWASP security compliance.

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Monitoring](#monitoring)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

## 🎯 Overview

This service subscribes to MQTT broker topics, validates incoming messages against tag_master, and stores data in historian tables with full audit trails.

**Key Capabilities:**
- Multi-threaded message processing
- Real-time tag validation against tag_master (READ-ONLY)
- Comprehensive audit logging
- OWASP Top 10 security compliance
- Optional TLS/mTLS encryption
- Health monitoring and metrics collection
- Fail-fast design (no retry logic)

## ✨ Features

### Core Functionality
- **MQTT Client**: Eclipse Paho-based client with TLS support
- **Message Processing**: Multi-threaded worker pool (configurable)
- **Data Validation**: Schema-based validation with tag_master cache
- **Audit Trail**: Complete message lifecycle tracking
- **Historian Storage**: TimescaleDB optimized for time-series data

### Security (OWASP Compliance)
- **A01 - Broken Access Control**: TLS/mTLS authentication
- **A02 - Cryptographic Failures**: Optional credential encryption
- **A03 - Injection**: Parameterized queries, input sanitization
- **A04 - Insecure Design**: Fail-fast design, no retry logic
- **A05 - Security Misconfiguration**: Secure defaults
- **A06 - Vulnerable Components**: Regular dependency updates
- **A07 - Authentication Failures**: MQTT authentication
- **A08 - Integrity Failures**: Message checksums
- **A09 - Logging Failures**: Comprehensive audit logs
- **A10 - Server-Side Request Forgery**: Validation

### Monitoring
- Health check endpoint
- Prometheus-compatible metrics
- JSON structured logging with rotation
- Real-time performance statistics

## 🏗️ Architecture

```
┌─────────────────┐
│  MQTT Broker    │
└────────┬────────┘
         │ Messages
         ▼
┌─────────────────────────────────────────┐
│         MQTT Subscriber Service         │
│                                         │
│  ┌──────────────┐  ┌─────────────────┐ │
│  │ MQTT Client  │  │  Topic Cache    │ │
│  └──────┬───────┘  └─────────────────┘ │
│         │                               │
│         ▼                               │
│  ┌──────────────────────────────────┐  │
│  │    Thread Pool (8 workers)      │  │
│  │  ┌────────────────────────────┐ │  │
│  │  │   Message Processor        │ │  │
│  │  │  - Parse & Validate        │ │  │
│  │  │  - Tag Master Check        │ │  │
│  │  │  - Insert to Historian     │ │  │
│  │  └────────────────────────────┘ │  │
│  └──────────────────────────────────┘  │
│                                         │
└─────────────────┬───────────────────────┘
                  │
                  ▼
          ┌──────────────┐
          │  PostgreSQL  │
          │ + TimescaleDB│
          └──────────────┘
```

## 📦 Requirements

### Software
- Python 3.10 or higher
- PostgreSQL 14+
- TimescaleDB extension
- MQTT Broker (e.g., Mosquitto, HiveMQ, AWS IoT Core)

### Python Dependencies
```
paho-mqtt==1.6.1
psycopg2-binary==2.9.9
PyYAML==6.0.1
python-json-logger==2.0.7
cryptography==41.0.7
pytest==7.4.3
```

### Database Schema
- `historian_raw.mqtt_topic_config` - Topic configurations
- `historian_raw.mqtt_audit_main` - Main audit records
- `historian_raw.mqtt_audit_history` - Audit step tracking
- `historian_raw.historian_timeseries` - Time-series data
- `historian_raw.historian_events` - Event data
- `historian_meta.tag_master` - Tag definitions (READ-ONLY)

## 🚀 Installation

### Step 1: Install Dependencies

```batch
# Run the installation script
install.bat
```

Or manually:

```batch
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Database Setup

Run the SQL schema script:

```sql
psql -h localhost -U postgres -d historian_db -f sql/create_subscriber_tables.sql
```

### Step 3: Configuration

Edit `config/service_config.yaml`:

```yaml
database:
  host: localhost
  port: 5432
  database: historian_db
  user: mqtt_subscriber_user
  password: your_secure_password

mqtt:
  broker: mqtt.example.com
  port: 1883
  username: mqtt_user
  password: mqtt_password
```

## ⚙️ Configuration

### Environment Variables (Override Config)

```batch
set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=historian_db
set DB_USER=mqtt_subscriber_user
set DB_PASSWORD=your_password

set MQTT_BROKER=mqtt.example.com
set MQTT_PORT=1883
set MQTT_USERNAME=mqtt_user
set MQTT_PASSWORD=mqtt_password
```

### Service Configuration

Key configuration sections:

- **service**: Service name, version, environment
- **database**: PostgreSQL connection settings
- **mqtt**: MQTT broker connection settings
- **processing**: Worker threads, queue size, validation settings
- **security**: TLS, encryption, input sanitization
- **logging**: Log level, file rotation
- **monitoring**: Health check, metrics intervals

## 🎮 Usage

### Start Service

```batch
run_service.bat
```

Or manually:

```batch
venv\Scripts\activate.bat
python src/service_main.py
```

### Health Check

```batch
python scripts/health_check.py
```

### Stop Service

Press `Ctrl+C` or send SIGTERM signal.

## 📊 Monitoring

### Logs

Logs are stored in `logs/` directory:
- `mqtt_subscriber_service.log` - Main application log
- `mqtt_subscriber_service_error.log` - Error log only

### Metrics

Metrics are logged every 60 seconds (configurable):

```
Messages:
  - Received: 1000
  - Processed: 995
  - Failed: 5
  - Rate: 16.5 msg/s
  - Success Rate: 99.5%

Processing:
  - Avg Time: 12.5 ms
  - Min Time: 8.2 ms
  - Max Time: 45.1 ms
```

### Health Check

Service provides health status for:
- Database connectivity
- MQTT connection
- Topic cache status
- Tag master cache status
- Thread pool status

## 🔒 Security

### TLS/mTLS Configuration

Enable TLS in `config/service_config.yaml`:

```yaml
security:
  enable_tls: true
  tls:
    ca_cert: path/to/ca.crt
    client_cert: path/to/client.crt
    client_key: path/to/client.key
```

### Input Sanitization

All inputs are sanitized to prevent:
- SQL injection
- Command injection
- XSS attacks

### Credential Management

Credentials can be optionally encrypted (A02):

```yaml
security:
  enable_credential_encryption: true
  encryption_key_path: path/to/key.bin
```

## 🐛 Troubleshooting

### Database Connection Failed

```
ERROR: Database connection test failed
```

**Solution:**
1. Verify PostgreSQL is running
2. Check database credentials in config
3. Ensure `historian_raw` schema exists
4. Run `scripts/health_check.py`

### MQTT Connection Failed

```
ERROR: Failed to connect to MQTT broker
```

**Solution:**
1. Verify MQTT broker is running
2. Check broker address and port
3. Verify credentials
4. Check firewall rules

### Tag Not Found in tag_master

```
ERROR: Tag 'TAG001' not found in tag_master
```

**Solution:**
1. Verify tag exists in `historian_meta.tag_master`
2. Ensure `is_active = true` for the tag
3. Check tag_master_cache refresh interval

### High Processing Time

```
WARNING: Processing time 500ms exceeds threshold
```

**Solution:**
1. Increase worker_threads in config
2. Check database query performance
3. Review database indexes
4. Monitor database connection pool

## 📝 Message Format

Expected MQTT message payload (JSON):

```json
{
  "tag_id": "TAG001",
  "timestamp": "2024-01-15T10:30:00Z",
  "value": 123.45,
  "quality": "G",
  "source": "MQTT",
  "version": 1
}
```

Fields:
- `tag_id` (required): Tag identifier from tag_master
- `timestamp` (required): ISO 8601 timestamp
- `value` (required): Numeric, text, or boolean value
- `quality` (optional): G (Good), B (Bad), U (Uncertain)
- `source` (optional): Data source identifier
- `version` (optional): Mapping version

## 🔧 Development

### Running Tests

```batch
pytest tests/ -v
```

### Code Structure

```
mqtt_subscriber_service/
├── config/               # Configuration files
├── sql/                  # Database schema scripts
├── src/
│   ├── cache/           # Topic and tag master caches
│   ├── database/        # Database connection and DAOs
│   ├── models/          # Data models
│   ├── monitoring/      # Health check and metrics
│   ├── mqtt/            # MQTT client
│   ├── processing/      # Message processing
│   ├── utils/           # Utilities
│   ├── validation/      # Validators and sanitizers
│   └── service_main.py  # Main service entry point
├── scripts/             # Utility scripts
└── logs/                # Log files
```

## 📄 License

Copyright © 2024. All rights reserved.

## 👥 Support

For support, please contact the development team or create an issue in the project repository.

---

**Version:** 1.0.0  
**Last Updated:** 2024-01-15
