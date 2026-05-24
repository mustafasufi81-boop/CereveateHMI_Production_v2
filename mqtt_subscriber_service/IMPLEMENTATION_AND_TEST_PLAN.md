# MQTT Subscriber Service - Implementation & Test Plan

## Document Information
- **Version**: 1.0.0
- **Date**: January 6, 2026
- **Status**: Implementation Ready
- **Target Platform**: Windows Server / Windows 10+
- **Language**: Python 3.10+
- **Database**: PostgreSQL 14+ with TimescaleDB

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Implementation Plan](#implementation-plan)
4. [Database Schema](#database-schema)
5. [Security Implementation](#security-implementation)
6. [Test Plan](#test-plan)
7. [Deployment Plan](#deployment-plan)
8. [Monitoring & Maintenance](#monitoring--maintenance)

---

## Executive Summary

### Purpose
Enterprise-grade MQTT data subscriber service that receives industrial IoT data, processes it through a multi-threaded pipeline, and persists time-series data and alarms to PostgreSQL historian database with comprehensive audit trails.

### Key Features
- ✅ Database-driven topic configuration with in-memory caching
- ✅ Tag master validation cache (validates against tag_master - read-only)
- ✅ Multi-threaded concurrent message processing
- ✅ Dual-layer audit system (Main + History)
- ✅ No retry logic (fail-fast with comprehensive logging)
- ✅ OWASP security compliance (configurable encryption)
- ✅ Auto-detection of existing database schema
- ✅ Test data generator based on tag_master configuration
- ✅ Integrated test publisher for end-to-end testing
- ✅ Windows service deployment ready

### Performance Targets
- **Throughput**: 1,000+ messages/second
- **Latency**: <100ms per message (receive to DB commit)
- **Availability**: 99.9% uptime
- **Thread Pool**: Configurable 4-32 worker threads
- **Database Pool**: 20 connections (configurable)

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MQTT SUBSCRIBER SERVICE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌────────────────┐      ┌────────────────┐                   │
│   │  MQTT Broker   │─────▶│  MQTT Client   │                   │
│   │  (External)    │      │  (Paho Client) │                   │
│   └────────────────┘      └────────┬───────┘                   │
│                                     │                            │
│                            ┌────────▼────────┐                  │
│                            │  Topic Cache    │◀─────────┐       │
│                            │  (In-Memory)    │          │       │
│                            └────────┬────────┘          │       │
│                                     │              Load Topics  │
│                            ┌────────▼────────┐          │       │
│                            │ Tag Master Cache│◀─────────┼───┐   │
│                            │  (In-Memory)    │   Load Tags │   │
│                            └────────┬────────┘          │   │   │
│                                     │                   │   │   │
│                     ┌───────────────┴─────────────┐     │   │   │
│                     │   Thread Manager             │     │   │   │
│                     │   (Worker Pool)              │     │   │   │
│                     └───────────┬──────────────────┘     │   │   │
│                                 │                         │   │   │
│              ┌──────────────────┼──────────────────┐     │   │   │
│              │                  │                  │     │   │   │
│         ┌────▼────┐       ┌────▼────┐       ┌────▼────┐│   │   │
│         │ Worker  │       │ Worker  │  ...  │ Worker  ││   │   │
│         │ Thread 1│       │ Thread 2│       │ Thread N││   │   │
│         └────┬────┘       └────┬────┘       └────┬────┘│   │   │
│              │                  │                  │     │   │   │
│              └──────────────────┼──────────────────┘     │   │   │
│                                 │                         │   │   │
│                        ┌────────▼────────┐               │   │   │
│                        │ Message         │               │   │   │
│                        │ Processor       │               │   │   │
│                        └────────┬────────┘               │   │   │
│                                 │                         │   │   │
│                  ┌──────────────┼──────────────┐         │   │   │
│                  │              │              │         │   │   │
│            ┌─────▼─────┐  ┌────▼─────┐  ┌────▼─────┐   │   │   │
│            │ Validator │  │ Sanitizer│  │ Parser   │   │   │   │
│            │ (uses Tag │  │          │  │          │   │   │   │
│            │  Master   │  │          │  │          │   │   │   │
│            │  Cache)   │  │          │  │          │   │   │   │
│            └─────┬─────┘  └────┬─────┘  └────┬─────┘   │   │   │
│                  │              │              │         │       │
│                  └──────────────┼──────────────┘         │       │
│                                 │                         │       │
│                        ┌────────▼────────┐               │       │
│                        │  Database DAO   │               │       │
│                        │  (Connection    │               │       │
│                        │   Pool)         │               │       │
│                        └────────┬────────┘               │       │
│                                 │                         │       │
└─────────────────────────────────┼─────────────────────────┼───────┘
                                  │                         │
                        ┌─────────▼─────────────────────────▼───────┐
                        │     PostgreSQL + TimescaleDB              │
                        ├───────────────────────────────────────────┤
                        │  historian_raw.mqtt_topic_config          │
                        │  historian_raw.mqtt_audit_main            │
                        │  historian_raw.mqtt_audit_history         │
                        │  historian_raw.historian_timeseries       │
                        │  historian_raw.historian_events           │
                        │  historian_meta.tag_master (READ-ONLY)    │
                        └───────────────────────────────────────────┘
                                        ▲
                                        │ Read tags for cache
                                        │ (Service startup only)
                        ┌───────────────┴───────────────┐
                        │                               │
                   Topic Cache                   Tag Master Cache
                   Load Topics                   Load Tag Definitions
```

### Component Interaction Flow

```
1. SERVICE STARTUP
   ├─ Load Configuration (config/service_config.yaml)
   ├─ Initialize Logging
   ├─ Connect to PostgreSQL
   ├─ Load Topics from DB → Topic Cache
   ├─ Load Tag Master from DB → Tag Master Cache (READ-ONLY)
   │  └─ Cache tag_id, data_type, enabled, validation rules
   ├─ Connect to MQTT Broker
   ├─ Subscribe to Topics from Cache
   ├─ Start Worker Thread Pool
   └─ Start Health Monitor

2. MESSAGE PROCESSING (Per Message)
   ├─ MQTT Client receives message
   ├─ Route to available Worker Thread
   │
   ├─ INSERT mqtt_audit_main (status='RECEIVED')
   ├─ INSERT mqtt_audit_history (step='RECEIVED')
   │
   ├─ Validate Payload
   │  ├─ Validate JSON structure
   │  ├─ Validate required fields (file_id, gateway_id, tags[])
   │  ├─ Validate each tag against Tag Master Cache:
   │  │  ├─ Check tag_id exists in cache
   │  │  ├─ Check tag is enabled
   │  │  ├─ Validate data_type matches (double, boolean, string)
   │  │  └─ Validate quality code (G, B, U)
   │  ├─ SUCCESS → INSERT audit_history (step='VALIDATION', status='SUCCESS')
   │  └─ FAILURE → INSERT audit_history (step='VALIDATION', status='FAILED')
   │              → UPDATE audit_main (status='VALIDATION_FAILED')
   │              → Exit
   │
   ├─ Parse & Insert historian_timeseries
   │  ├─ SUCCESS → INSERT audit_history (step='TIMESERIES_INSERT', status='SUCCESS')
   │  │          → UPDATE audit_main.tags_processed count
   │  └─ FAILURE → INSERT audit_history (step='TIMESERIES_INSERT', status='FAILED')
   │              → UPDATE audit_main (status='DB_INSERT_FAILED')
   │              → Exit
   │
   ├─ Insert historian_events (if alarms exist)
   │  ├─ SUCCESS → INSERT audit_history (step='EVENT_INSERT', status='SUCCESS')
   │  │          → UPDATE audit_main.events_generated count
   │  └─ FAILURE → INSERT audit_history (step='EVENT_INSERT', status='FAILED')
   │              → UPDATE audit_main (status='EVENT_INSERT_FAILED')
   │              → Exit
   │
   ├─ UPDATE mqtt_audit_main (status='COMPLETED', processed_time=NOW())
   ├─ INSERT audit_history (step='COMPLETED', status='SUCCESS')
   └─ COMMIT Transaction

3. CONTINUOUS OPERATION
   ├─ Process messages as they arrive
   ├─ Periodic topic cache refresh (every 5 minutes)
   ├─ Periodic tag master cache refresh (every 5 minutes)
   ├─ Health monitoring (every 60 seconds)
   ├─ Metrics collection
   └─ Log rotation

4. GRACEFUL SHUTDOWN
   ├─ Stop accepting new messages
   ├─ Wait for in-flight messages to complete (max 30 seconds)
   ├─ Disconnect from MQTT Broker
   ├─ Close database connections
   └─ Flush logs
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1)

#### 1.1 Database Setup
**Duration**: 1 day

**Tasks**:
- [ ] Create SQL schema file (`sql/create_subscriber_tables.sql`)
- [ ] Create new tables in `historian_raw` schema:
  - `mqtt_topic_config`
  - `mqtt_audit_main`
  - `mqtt_audit_history`
- [ ] Create indexes for performance
- [ ] Insert sample topic configurations
- [ ] Verify schema with existing historian tables
- [ ] Test database connections

**Deliverables**:
- SQL schema creation script
- Sample data insert script
- Database connection test script

#### 1.2 Configuration Management
**Duration**: 1 day

**Tasks**:
- [ ] Create `config/service_config.yaml`
- [ ] Create `config/logging_config.json`
- [ ] Create `config/secrets.yaml` (optional)
- [ ] Implement `utils/config_loader.py`
- [ ] Add configuration validation
- [ ] Support environment variable override

**Deliverables**:
- Configuration files
- Configuration loader module
- Configuration documentation

#### 1.3 Logging Infrastructure
**Duration**: 1 day

**Tasks**:
- [ ] Implement `monitoring/logger.py`
- [ ] Configure structured JSON logging
- [ ] Setup log rotation
- [ ] Create log directory structure
- [ ] Add security event logging
- [ ] Test logging at different levels

**Deliverables**:
- Centralized logger module
- Log configuration
- Log testing script

### Phase 2: Database Layer (Week 1-2)

#### 2.1 Database Connection
**Duration**: 1 day

**Tasks**:
- [ ] Implement `database/db_connection.py`
- [ ] Create connection pool with psycopg2
- [ ] Add connection health checks
- [ ] Implement transaction management
- [ ] Add connection retry logic on startup
- [ ] Test connection pooling

**Deliverables**:
- Database connection module
- Connection pool manager
- Health check function

#### 2.2 Schema Inspector
**Duration**: 1 day

**Tasks**:
- [ ] Implement `database/schema_inspector.py`
- [ ] Auto-detect `historian_timeseries` columns
- [ ] Auto-detect `historian_events` columns
- [ ] Auto-detect `tag_master` columns
- [ ] Build dynamic column mapping
- [ ] Cache schema metadata

**Deliverables**:
- Schema inspection module
- Dynamic column mapper
- Schema metadata cache

#### 2.3 Data Access Objects
**Duration**: 2 days

**Tasks**:
- [ ] Implement `database/audit_dao.py`
  - insert_audit_main()
  - insert_audit_history()
  - update_audit_main()
  - get_audit_by_message_id()
- [ ] Implement `database/historian_dao.py`
  - insert_timeseries_batch()
  - insert_events_batch()
  - check_message_id_exists()
- [ ] Add parameterized queries (SQL injection prevention)
- [ ] Add batch insert optimization
- [ ] Test all DAO methods

**Deliverables**:
- Audit DAO module
- Historian DAO module
- Unit tests for DAOs

### Phase 3: MQTT Client (Week 2)

#### 3.1 MQTT Connection Manager
**Duration**: 2 days

**Tasks**:
- [ ] Implement `core/mqtt_client.py`
- [ ] Initialize Eclipse Paho client
- [ ] Connect to MQTT broker
- [ ] Subscribe to topics dynamically
- [ ] Handle connection callbacks (on_connect, on_disconnect)
- [ ] Handle message callback (on_message)
- [ ] Implement reconnection logic
- [ ] Add TLS/mTLS support (optional)
- [ ] Test MQTT connectivity

**Deliverables**:
- MQTT client module
- Connection management
- Callback handlers

#### 3.2 Topic Cache
**Duration**: 1 day

**Tasks**:
- [ ] Implement `core/topic_cache.py`
- [ ] Load topics from `mqtt_topic_config` table
- [ ] Store in-memory dictionary
- [ ] Filter by `is_active=true`
- [ ] Implement cache refresh
- [ ] Add thread-safe access
- [ ] Test cache operations

**Deliverables**:
- Topic cache module
- Cache refresh mechanism
- Thread-safe accessor methods

#### 3.3 Tag Master Cache
**Duration**: 1 day

**Tasks**:
- [ ] Implement `core/tag_master_cache.py`
- [ ] Load tags from `historian_meta.tag_master` table (READ-ONLY)
- [ ] Store in-memory dictionary: {tag_id: tag_metadata}
- [ ] Filter by `enabled=true`
- [ ] Cache fields: tag_id, tag_name, data_type, enabled, plant, area, equipment
- [ ] Implement cache refresh (every 5 minutes)
- [ ] Add thread-safe access
- [ ] Provide validation methods:
  - is_tag_valid(tag_id)
  - get_tag_data_type(tag_id)
  - is_tag_enabled(tag_id)
- [ ] Test cache operations

**Deliverables**:
- Tag Master cache module
- Cache refresh mechanism
- Tag validation methods
- Thread-safe accessor methods

### Phase 4: Message Processing (Week 2-3)

#### 4.1 Thread Manager
**Duration**: 2 days

**Tasks**:
- [ ] Implement `core/thread_manager.py`
- [ ] Create thread pool
- [ ] Assign messages to worker threads
- [ ] Monitor thread health
- [ ] Implement graceful shutdown
- [ ] Add thread metrics
- [ ] Test thread pool behavior

**Deliverables**:
- Thread manager module
- Worker thread pool
- Thread health monitoring

#### 4.2 Message Processor
**Duration**: 3 days

**Tasks**:
- [ ] Implement `core/message_processor.py`
- [ ] Process method workflow:
  1. Insert audit_main (RECEIVED)
  2. Insert audit_history (RECEIVED)
  3. Validate payload
  4. Parse tags and insert timeseries
  5. Parse alarms and insert events
  6. Update audit_main (COMPLETED)
  7. Commit transaction
- [ ] Handle each failure point
- [ ] Add processing metrics
- [ ] Test with sample payloads

**Deliverables**:
- Message processor module
- Complete processing pipeline
- Error handling logic

#### 4.3 Data Models
**Duration**: 1 day

**Tasks**:
- [ ] Implement `models/domain_models.py`
- [ ] Create Topic model
- [ ] Create Message model
- [ ] Create Tag model
- [ ] Create Alarm model
- [ ] Create AuditMain model
- [ ] Create AuditHistory model
- [ ] Add data validation

**Deliverables**:
- Domain model classes
- Data validation methods

### Phase 5: Security & Validation (Week 3)

#### 5.1 Input Validation & Sanitization
**Duration**: 2 days

**Tasks**:
- [ ] Implement `security/validator.py`
- [ ] Validate JSON structure
- [ ] Validate data types
- [ ] Validate required fields (file_id, gateway_id, timestamp, tags[])
- [ ] **Validate tags against Tag Master Cache**:
  - Check tag_id exists in cache
  - Verify tag is enabled
  - Validate data_type matches (value_num for double, value_bool for boolean, value_text for string)
  - Validate quality code is G, B, or U
  - Validate timestamp format
- [ ] Implement `security/input_sanitizer.py`
- [ ] Sanitize tag_id (prevent SQL injection)
- [ ] Sanitize string values
- [ ] Test with malicious payloads
- [ ] Test with invalid tag_ids (not in tag_master)
- [ ] Test with disabled tags

**Deliverables**:
- Validator module with Tag Master Cache integration
- Input sanitizer module
- Tag validation logic
- Security test cases

#### 5.2 Credential Management (Optional)
**Duration**: 1 day

**Tasks**:
- [ ] Implement `security/credential_store.py`
- [ ] Support plain text mode (encryption_enabled=false)
- [ ] Support encrypted mode (encryption_enabled=true)
- [ ] Use Fernet encryption for passwords
- [ ] Store encrypted values in secrets.yaml
- [ ] Add configuration flag to toggle
- [ ] Test both modes

**Deliverables**:
- Credential store module
- Encryption/decryption functions
- Configuration support

#### 5.3 TLS Configuration (Optional)
**Duration**: 1 day

**Tasks**:
- [ ] Implement `security/tls_config.py`
- [ ] Support plain MQTT (tls_enabled=false)
- [ ] Support TLS/mTLS (tls_enabled=true)
- [ ] Load certificates from config paths
- [ ] Configure MQTT client with TLS
- [ ] Test both modes

**Deliverables**:
- TLS configuration module
- Certificate loading logic

### Phase 6: Monitoring & Health (Week 3)

#### 6.1 Health Check
**Duration**: 1 day

**Tasks**:
- [ ] Implement `monitoring/health_check.py`
- [ ] Check MQTT connection status
- [ ] Check database connection status
- [ ] Check worker thread status
- [ ] Check disk space
- [ ] Expose health endpoint (optional REST API)
- [ ] Test health checks

**Deliverables**:
- Health check module
- Status reporting

#### 6.2 Metrics Collection
**Duration**: 1 day

**Tasks**:
- [ ] Implement `monitoring/metrics.py`
- [ ] Track messages received
- [ ] Track messages processed
- [ ] Track processing time
- [ ] Track errors
- [ ] Track database operations
- [ ] Log metrics periodically
- [ ] Test metrics collection

**Deliverables**:
- Metrics collection module
- Periodic metrics reporting

### Phase 7: Main Service (Week 4)

#### 7.1 Service Entry Point
**Duration**: 2 days

**Tasks**:
- [ ] Implement `main.py`
- [ ] Initialize all components
- [ ] Start service lifecycle
- [ ] Implement signal handlers (SIGTERM, SIGINT)
- [ ] Implement graceful shutdown
- [ ] Add startup validation
- [ ] Test service startup/shutdown

**Deliverables**:
- Main service module
- Signal handlers
- Graceful shutdown logic

#### 7.2 Windows Service Wrapper
**Duration**: 1 day

**Tasks**:
- [ ] Create `install.bat`
- [ ] Create `start_service.bat`
- [ ] Create `stop_service.bat`
- [ ] Test Windows service installation
- [ ] Test service start/stop
- [ ] Add service logging

**Deliverables**:
- Windows service scripts
- Installation documentation

### Phase 8: Test Module (Week 4)

#### 8.1 Test Data Generator
**Duration**: 1 day

**Tasks**:
- [ ] Implement `tests/test_data_generator.py`
- [ ] **Read tag definitions from historian_meta.tag_master table**
- [ ] **Generate test messages based on actual tag_master data**:
  - Use real tag_ids from tag_master
  - Use correct data_type for each tag (double, boolean, string)
  - Respect enabled flag
  - Include plant, area, equipment metadata
- [ ] Generate realistic values based on data_type:
  - Double: Random numeric values within reasonable ranges
  - Boolean: Random true/false
  - String: Random status strings
- [ ] Vary quality codes (G, B, U)
- [ ] Generate alarms for specific tags
- [ ] Create edge cases (boundary values, null handling)
- [ ] Export to JSON
- [ ] Test data generation

**Deliverables**:
- Test data generator (reads from tag_master)
- Sample data files with real tag configurations
- Edge case test files

#### 8.2 MQTT Test Publisher
**Duration**: 2 days

**Tasks**:
- [ ] Implement `tests/mqtt_test_publisher.py`
- [ ] Connect to MQTT broker
- [ ] **Use test_data_generator to create messages from tag_master**
- [ ] Load sample payload (optional static file)
- [ ] Publish single message mode
- [ ] Publish continuous mode (generate new messages each time)
- [ ] Publish burst mode
- [ ] Multi-gateway simulation
- [ ] Add command-line arguments:
  - --use-tag-master (generate from DB)
  - --use-file (use static JSON file)
  - --tag-filter (filter specific tags)
- [ ] Test publisher modes

**Deliverables**:
- MQTT test publisher (integrates with test_data_generator)
- Publisher CLI with tag_master integration
- Usage documentation

#### 8.3 End-to-End Test
**Duration**: 2 days

**Tasks**:
- [ ] Implement `tests/end_to_end_test.py`
- [ ] Start subscriber service
- [ ] Publish test messages
- [ ] Wait for processing
- [ ] Validate database records
- [ ] Generate test report
- [ ] Create `run_end_to_end_test.bat`
- [ ] Test full E2E flow

**Deliverables**:
- E2E test orchestrator
- Test validation logic
- Test report generator

#### 8.4 Unit & Integration Tests
**Duration**: 2 days

**Tasks**:
- [ ] Implement unit tests
  - `tests/unit/test_message_processor.py`
  - `tests/unit/test_validator.py`
  - `tests/unit/test_db_operations.py`
- [ ] Implement integration tests
  - `tests/integration/test_mqtt_integration.py`
  - `tests/integration/test_db_integration.py`
- [ ] Implement security tests
  - `tests/security/test_sql_injection.py`
- [ ] Test coverage report

**Deliverables**:
- Unit test suite
- Integration test suite
- Security test suite
- Test coverage report

### Phase 9: Documentation (Week 5)

#### 9.1 Technical Documentation
**Duration**: 2 days

**Tasks**:
- [ ] Create `README.md`
- [ ] Create installation guide
- [ ] Create configuration guide
- [ ] Create troubleshooting guide
- [ ] Create API documentation
- [ ] Add code comments
- [ ] Create architecture diagrams

**Deliverables**:
- Complete documentation set
- User guides
- Developer guides

#### 9.2 Deployment Package
**Duration**: 1 day

**Tasks**:
- [ ] Create `requirements.txt`
- [ ] Create deployment checklist
- [ ] Create quick start guide
- [ ] Package all components
- [ ] Test deployment on clean system

**Deliverables**:
- Deployment package
- Installation scripts
- Quick start guide

---

## Database Schema

### New Tables (historian_raw schema)

#### 1. mqtt_topic_config
**Purpose**: Store MQTT topic configuration

```sql
CREATE TABLE IF NOT EXISTS historian_raw.mqtt_topic_config (
    topic_id SERIAL PRIMARY KEY,
    topic_name TEXT NOT NULL UNIQUE,
    qos INTEGER NOT NULL DEFAULT 1 CHECK (qos IN (0, 1, 2)),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    thread_group INTEGER NOT NULL DEFAULT 1,
    processing_rules JSONB,
    created_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_time TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_mqtt_topic_active ON historian_raw.mqtt_topic_config(is_active);
CREATE INDEX idx_mqtt_topic_name ON historian_raw.mqtt_topic_config(topic_name);

COMMENT ON TABLE historian_raw.mqtt_topic_config IS 'MQTT topic subscription configuration';
COMMENT ON COLUMN historian_raw.mqtt_topic_config.qos IS 'Quality of Service: 0=At most once, 1=At least once, 2=Exactly once';
COMMENT ON COLUMN historian_raw.mqtt_topic_config.processing_rules IS 'Optional JSON rules for message processing';
```

**Sample Data**:
```sql
INSERT INTO historian_raw.mqtt_topic_config (topic_name, qos, is_active, thread_group) VALUES
('test/gateway/data', 1, TRUE, 1),
('production/plant_a/gateway_001', 1, TRUE, 1),
('production/plant_b/gateway_002', 1, TRUE, 2),
('development/test/#', 0, TRUE, 1);
```

#### 2. mqtt_audit_main
**Purpose**: Main audit record per MQTT message (one record per message)

```sql
CREATE TABLE IF NOT EXISTS historian_raw.mqtt_audit_main (
    audit_id BIGSERIAL PRIMARY KEY,
    topic_name TEXT NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    first_received_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_time TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'RECEIVED' CHECK (
        status IN ('RECEIVED', 'VALIDATION_FAILED', 'DB_INSERT_FAILED', 
                   'EVENT_INSERT_FAILED', 'COMPLETED', 'FAILED')
    ),
    error_message TEXT,
    tags_processed INTEGER DEFAULT 0,
    events_generated INTEGER DEFAULT 0,
    processing_duration_ms INTEGER
);

CREATE INDEX idx_audit_main_msg_id ON historian_raw.mqtt_audit_main(message_id);
CREATE INDEX idx_audit_main_status ON historian_raw.mqtt_audit_main(status);
CREATE INDEX idx_audit_main_time ON historian_raw.mqtt_audit_main(first_received_time DESC);
CREATE INDEX idx_audit_main_topic ON historian_raw.mqtt_audit_main(topic_name);

COMMENT ON TABLE historian_raw.mqtt_audit_main IS 'Main audit record for each MQTT message';
COMMENT ON COLUMN historian_raw.mqtt_audit_main.message_id IS 'Unique message identifier from payload (file_id)';
COMMENT ON COLUMN historian_raw.mqtt_audit_main.status IS 'Final processing status';
```

#### 3. mqtt_audit_history
**Purpose**: Detailed processing steps per message (multiple records per message)

```sql
CREATE TABLE IF NOT EXISTS historian_raw.mqtt_audit_history (
    hist_id BIGSERIAL PRIMARY KEY,
    audit_id BIGINT NOT NULL REFERENCES historian_raw.mqtt_audit_main(audit_id),
    processing_step TEXT NOT NULL CHECK (
        processing_step IN ('RECEIVED', 'VALIDATION', 'TIMESERIES_INSERT', 
                           'EVENT_INSERT', 'COMPLETED', 'FAILED')
    ),
    step_status TEXT NOT NULL CHECK (step_status IN ('SUCCESS', 'FAILED')),
    step_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    step_details JSONB,
    error_details TEXT,
    duration_ms INTEGER
);

CREATE INDEX idx_audit_hist_audit_id ON historian_raw.mqtt_audit_history(audit_id);
CREATE INDEX idx_audit_hist_step ON historian_raw.mqtt_audit_history(processing_step);
CREATE INDEX idx_audit_hist_time ON historian_raw.mqtt_audit_history(step_time DESC);

COMMENT ON TABLE historian_raw.mqtt_audit_history IS 'Detailed audit trail for each processing step';
COMMENT ON COLUMN historian_raw.mqtt_audit_history.processing_step IS 'Processing step identifier';
```

### Existing Tables (Used by Service)

#### historian_raw.historian_timeseries
**Columns**: time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version

**Insert Pattern**:
```sql
INSERT INTO historian_raw.historian_timeseries 
(time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version)
VALUES 
($1, $2, $3, $4, $5, $6, $7, $8);
```

#### historian_raw.historian_events
**Columns**: event_id, time, tag_id, event_type, severity, message, metadata

**Insert Pattern**:
```sql
INSERT INTO historian_raw.historian_events 
(time, tag_id, event_type, severity, message, metadata)
VALUES 
($1, $2, $3, $4, $5, $6);
```

#### historian_meta.tag_master (READ-ONLY)
**Columns**: tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit, db_logging_interval_ms, enabled

**Usage Pattern**:
```sql
-- Load at service startup into Tag Master Cache
SELECT tag_id, tag_name, data_type, enabled, plant, area, equipment
FROM historian_meta.tag_master
WHERE enabled = TRUE;
```

**Purpose**:
- **Validation**: Verify incoming MQTT tags are registered and enabled
- **Data Type Checking**: Ensure value_num/value_bool/value_text matches tag data_type
- **Metadata**: Provide context for test data generation

**IMPORTANT**: 
- MQTT Subscriber Service has **READ-ONLY** access to this table
- NO INSERT, UPDATE, or DELETE operations allowed
- Tag definitions managed by separate admin process
- Service only reads at startup and periodic cache refresh

---

## Security Implementation

### OWASP Top 10 Compliance

#### A01: Broken Access Control
**Implementation**:
- Database user with minimal privileges (INSERT on specific tables only)
- No direct SQL access from application logic
- All DB operations through parameterized queries

**Configuration**:
```yaml
database:
  username: "mqtt_subscriber_user"  # Limited privilege user
  # GRANT INSERT ON historian_raw.mqtt_audit_main TO mqtt_subscriber_user;
  # GRANT INSERT ON historian_raw.mqtt_audit_history TO mqtt_subscriber_user;
  # GRANT INSERT ON historian_raw.historian_timeseries TO mqtt_subscriber_user;
  # GRANT INSERT ON historian_raw.historian_events TO mqtt_subscriber_user;
  # GRANT SELECT ON historian_raw.mqtt_topic_config TO mqtt_subscriber_user;
  # GRANT SELECT ON historian_meta.tag_master TO mqtt_subscriber_user;  (READ-ONLY)
```

#### A02: Cryptographic Failures (CONFIGURABLE)
**Implementation**:
- Optional TLS/mTLS for MQTT connections
- Optional password encryption in config

**Configuration**:
```yaml
security:
  encryption_enabled: false  # Set to true for production
  tls_enabled: false         # Set to true for production
  
  # When encryption_enabled=true:
  tls_cert_path: "C:/Certificates/client.crt"
  tls_key_path: "C:/Certificates/client.key"
  ca_cert_path: "C:/Certificates/ca.crt"
```

#### A03: Injection (MANDATORY)
**Implementation**:
- All SQL queries use parameterized statements
- Input validation before processing
- String sanitization

**Code Pattern**:
```python
# SECURE - Parameterized query
cursor.execute(
    "INSERT INTO mqtt_audit_main (topic_name, message_id, payload) VALUES (%s, %s, %s)",
    (topic_name, message_id, json.dumps(payload))
)

# NEVER - String concatenation
# cursor.execute(f"INSERT INTO mqtt_audit_main VALUES ('{message_id}')")  # DANGEROUS!
```

#### A08: Data Integrity Failures
**Implementation**:
- Message deduplication using message_id
- Audit logging for all operations
- Transaction integrity

**Code Pattern**:
```python
# Check for duplicate message_id
existing = check_message_id_exists(message_id)
if existing:
    logger.warning(f"Duplicate message_id: {message_id}")
    return  # Skip processing
```

#### A09: Security Logging & Monitoring (MANDATORY)
**Implementation**:
- Structured JSON logging
- Security event logging
- Audit trail in database

**Log Events**:
- Message received
- Validation failures
- Database errors
- Authentication failures
- Configuration changes

---

## Test Plan

### Test Strategy
- **Unit Testing**: Individual component testing
- **Integration Testing**: Component interaction testing
- **End-to-End Testing**: Full workflow testing
- **Performance Testing**: Load and stress testing
- **Security Testing**: Vulnerability testing

### Test Environment

#### Hardware Requirements
- **CPU**: 4 cores minimum
- **RAM**: 8 GB minimum
- **Disk**: 50 GB free space
- **Network**: 1 Gbps

#### Software Requirements
- **OS**: Windows 10/11 or Windows Server 2019+
- **Python**: 3.10+
- **PostgreSQL**: 14+ with TimescaleDB extension
- **MQTT Broker**: Mosquitto 2.0+ or AWS IoT Core

### Test Categories

#### 1. Unit Tests

##### 1.1 Message Processor Tests
**File**: `tests/unit/test_message_processor.py`

**Test Cases**:
```python
def test_valid_message_processing():
    """Test processing of valid MQTT message"""
    # GIVEN: Valid message payload
    # WHEN: Process message
    # THEN: Returns success, data inserted to DB

def test_invalid_json_handling():
    """Test handling of invalid JSON"""
    # GIVEN: Invalid JSON payload
    # WHEN: Process message
    # THEN: Returns validation error, audit logged

def test_missing_required_fields():
    """Test handling of missing required fields"""
    # GIVEN: Message missing file_id
    # WHEN: Process message
    # THEN: Returns validation error

def test_invalid_data_types():
    """Test handling of invalid data types"""
    # GIVEN: String value in numeric field
    # WHEN: Process message
    # THEN: Returns validation error

def test_empty_tags_array():
    """Test handling of empty tags array"""
    # GIVEN: Message with empty tags[]
    # WHEN: Process message
    # THEN: Completes but inserts 0 timeseries records
```

##### 1.2 Validator Tests
**File**: `tests/unit/test_validator.py`

**Test Cases**:
```python
def test_validate_message_structure():
    """Test message structure validation"""
    pass

def test_validate_tag_data_types():
    """Test tag data type validation"""
    pass

def test_validate_quality_codes():
    """Test quality code validation (G, B, U)"""
    pass

def test_validate_timestamp_format():
    """Test timestamp format validation"""
    pass

def test_validate_tag_exists_in_tag_master():
    """Test tag_id exists in Tag Master Cache"""
    # GIVEN: Message with tag_id that exists in tag_master
    # WHEN: Validate message
    # THEN: Validation passes
    pass

def test_validate_tag_not_in_tag_master():
    """Test tag_id does not exist in Tag Master Cache"""
    # GIVEN: Message with unknown tag_id
    # WHEN: Validate message
    # THEN: Validation fails with 'Unknown tag_id' error
    pass

def test_validate_disabled_tag():
    """Test disabled tag rejection"""
    # GIVEN: Message with tag_id that is disabled in tag_master
    # WHEN: Validate message
    # THEN: Validation fails with 'Tag disabled' error
    pass

def test_validate_data_type_mismatch():
    """Test data type mismatch"""
    # GIVEN: Tag defined as 'boolean' in tag_master
    #        But message contains value_num (should be value_bool)
    # WHEN: Validate message
    # THEN: Validation fails with 'Data type mismatch' error
    pass

def test_tag_master_cache_performance():
    """Test cache lookup is fast (no DB calls)"""
    # GIVEN: Tag Master Cache loaded
    # WHEN: Validate 1000 tags
    # THEN: No database queries, all lookups from cache
    #       Average lookup time < 1ms
    pass
```

##### 1.3 Database Operations Tests
**File**: `tests/unit/test_db_operations.py`

**Test Cases**:
```python
def test_insert_audit_main():
    """Test audit_main insert"""
    pass

def test_insert_audit_history():
    """Test audit_history insert"""
    pass

def test_insert_timeseries_batch():
    """Test batch insert to historian_timeseries"""
    pass

def test_insert_events_batch():
    """Test batch insert to historian_events"""
    pass

def test_duplicate_message_id_handling():
    """Test duplicate message_id detection"""
    pass

def test_transaction_rollback():
    """Test transaction rollback on error"""
    pass
```

#### 2. Integration Tests

##### 2.1 MQTT Integration Tests
**File**: `tests/integration/test_mqtt_integration.py`

**Test Cases**:
```python
def test_mqtt_connection():
    """Test MQTT broker connection"""
    # GIVEN: MQTT broker running
    # WHEN: Connect to broker
    # THEN: Connection successful

def test_mqtt_subscription():
    """Test topic subscription"""
    # GIVEN: Topics in database
    # WHEN: Subscribe to topics
    # THEN: Subscription successful

def test_mqtt_message_receive():
    """Test message reception"""
    # GIVEN: Subscribed to topic
    # WHEN: Publish message to topic
    # THEN: Message received by subscriber

def test_mqtt_reconnection():
    """Test automatic reconnection"""
    # GIVEN: Connected to broker
    # WHEN: Broker connection lost
    # THEN: Automatically reconnects
```

##### 2.2 Database Integration Tests
**File**: `tests/integration/test_db_integration.py`

**Test Cases**:
```python
def test_database_connection_pool():
    """Test connection pool management"""
    pass

def test_concurrent_database_operations():
    """Test concurrent inserts from multiple threads"""
    pass

def test_transaction_management():
    """Test transaction commit/rollback"""
    pass

def test_schema_auto_detection():
    """Test automatic schema detection"""
    pass
```

#### 3. End-to-End Tests

##### 3.1 Single Message E2E Test
**File**: `tests/end_to_end_test.py`

**Test Scenario**:
```python
def test_single_message_e2e():
    """
    Test complete workflow with single message
    
    STEPS:
    1. Start subscriber service
    2. Publish single test message via mqtt_test_publisher
    3. Wait for processing (max 5 seconds)
    4. Validate database records:
       - mqtt_audit_main: 1 record, status='COMPLETED'
       - mqtt_audit_history: 5 records (RECEIVED, VALIDATION, TIMESERIES_INSERT, EVENT_INSERT, COMPLETED)
       - historian_timeseries: 10 records (10 tags)
       - historian_events: 3 records (3 alarms)
    5. Stop subscriber service
    
    EXPECTED RESULT: All validations pass
    """
    pass
```

##### 3.2 Batch Message E2E Test
**Test Scenario**:
```python
def test_batch_messages_e2e():
    """
    Test complete workflow with batch messages
    
    STEPS:
    1. Start subscriber service
    2. Publish 100 test messages via mqtt_test_publisher
    3. Wait for processing (max 60 seconds)
    4. Validate database records:
       - mqtt_audit_main: 100 records, all status='COMPLETED'
       - mqtt_audit_history: 500 records (5 steps × 100 messages)
       - historian_timeseries: 1000 records (10 tags × 100 messages)
       - historian_events: 300 records (3 alarms × 100 messages)
    5. Verify no errors in logs
    6. Stop subscriber service
    
    EXPECTED RESULT: All 100 messages processed successfully
    """
    pass
```

##### 3.3 Error Handling E2E Test
**Test Scenario**:
```python
def test_error_handling_e2e():
    """
    Test error handling with invalid messages
    
    STEPS:
    1. Start subscriber service
    2. Publish message with invalid JSON
    3. Publish message with missing file_id
    4. Publish message with invalid data type
    5. Wait for processing
    6. Validate audit records show failures:
       - mqtt_audit_main: 3 records with appropriate error status
       - mqtt_audit_history: Records show failure steps
    7. Verify errors logged
    
    EXPECTED RESULT: All errors caught and logged properly
    """
    pass
```

#### 4. Performance Tests

##### 4.1 Throughput Test
**Test Scenario**:
```
OBJECTIVE: Measure maximum throughput

SETUP:
- Worker threads: 8
- Message size: ~2 KB (10 tags, 3 alarms)
- Duration: 5 minutes

TEST:
1. Publish messages at increasing rates:
   - 100 msg/sec
   - 500 msg/sec
   - 1000 msg/sec
   - 2000 msg/sec
2. Measure processing success rate
3. Measure processing latency
4. Monitor resource usage (CPU, RAM, DB connections)

SUCCESS CRITERIA:
- 1000 msg/sec with <100ms average latency
- 99% success rate
- CPU usage <80%
- Memory stable (no leaks)
```

##### 4.2 Latency Test
**Test Scenario**:
```
OBJECTIVE: Measure end-to-end latency

METRICS:
- Time from MQTT publish to DB commit
- P50, P95, P99 latencies

TEST:
1. Publish 1000 messages with timestamps
2. Record processing time for each
3. Calculate percentiles

SUCCESS CRITERIA:
- P50 latency: <50ms
- P95 latency: <100ms
- P99 latency: <200ms
```

##### 4.3 Stress Test
**Test Scenario**:
```
OBJECTIVE: Test behavior under extreme load

TEST:
1. Publish 10,000 messages as fast as possible
2. Monitor for:
   - Message loss
   - Processing failures
   - Memory leaks
   - Database connection exhaustion
3. Verify graceful degradation

SUCCESS CRITERIA:
- No message loss
- All failures properly logged
- System recovers after load
```

##### 4.4 Endurance Test
**Test Scenario**:
```
OBJECTIVE: Test long-term stability

TEST:
1. Run subscriber for 24 hours
2. Publish 100 msg/sec continuously
3. Monitor for:
   - Memory leaks
   - Connection leaks
   - Log file growth
   - Database performance degradation

SUCCESS CRITERIA:
- Stable memory usage
- No connection leaks
- Consistent performance over time
```

#### 5. Security Tests

##### 5.1 SQL Injection Test
**File**: `tests/security/test_sql_injection.py`

**Test Cases**:
```python
def test_sql_injection_in_tag_id():
    """
    Test SQL injection attempt in tag_id field
    
    PAYLOAD:
    {
      "file_id": "test",
      "tags": [{
        "tag_id": "'; DROP TABLE historian_timeseries; --"
      }]
    }
    
    EXPECTED: Sanitized, no SQL executed
    """
    pass

def test_sql_injection_in_message_id():
    """Test SQL injection in message_id"""
    pass

def test_sql_injection_in_text_value():
    """Test SQL injection in value_text"""
    pass
```

##### 5.2 Authentication Test
**Test Cases**:
```python
def test_mqtt_authentication_valid_credentials():
    """Test with valid MQTT credentials"""
    pass

def test_mqtt_authentication_invalid_credentials():
    """Test with invalid MQTT credentials"""
    pass

def test_database_authentication_valid_credentials():
    """Test with valid DB credentials"""
    pass

def test_database_authentication_invalid_credentials():
    """Test with invalid DB credentials"""
    pass
```

##### 5.3 TLS/mTLS Test
**Test Cases**:
```python
def test_tls_connection():
    """Test TLS encrypted MQTT connection"""
    pass

def test_mtls_connection():
    """Test mutual TLS authentication"""
    pass

def test_certificate_validation():
    """Test certificate validation"""
    pass
```

### Test Execution Plan

#### Phase 1: Development Testing
**Week 1-4**: During implementation
- Run unit tests after each component
- Target: 80% code coverage

#### Phase 2: Integration Testing
**Week 5**: After all components complete
- Run integration tests
- Fix integration issues
- Target: All integration tests pass

#### Phase 3: E2E Testing
**Week 5**: After integration tests
- Run E2E tests
- Validate complete workflows
- Target: All E2E scenarios pass

#### Phase 4: Performance Testing
**Week 6**: After E2E tests
- Run performance tests
- Optimize bottlenecks
- Target: Meet performance criteria

#### Phase 5: Security Testing
**Week 6**: After performance tests
- Run security tests
- Fix vulnerabilities
- Target: No critical vulnerabilities

#### Phase 6: Acceptance Testing
**Week 7**: Final validation
- Run full test suite
- User acceptance testing
- Production readiness review

### Test Data Management

#### Sample Data Sets
1. **Valid Messages**: 100 valid message samples
2. **Invalid Messages**: 50 invalid message samples (various error types)
3. **Edge Cases**: 20 edge case samples (empty arrays, null values, max sizes)
4. **Performance Data**: 10,000 messages for load testing

#### Test Database
- Separate test database: `Historian_data_test`
- Reset before each test run
- Seed with sample topic configurations

### Test Metrics & Reporting

#### Key Metrics
- **Test Coverage**: >80% code coverage
- **Pass Rate**: 100% of tests must pass
- **Performance**: Meet latency/throughput targets
- **Security**: Zero critical vulnerabilities

#### Test Reports
- **Unit Test Report**: Coverage and results per module
- **Integration Test Report**: Component interaction results
- **E2E Test Report**: Workflow validation results
- **Performance Test Report**: Throughput, latency, resource usage
- **Security Test Report**: Vulnerability scan results

---

## Deployment Plan

### Pre-Deployment Checklist

#### Infrastructure
- [ ] PostgreSQL 14+ installed and running
- [ ] TimescaleDB extension installed
- [ ] MQTT broker (Mosquitto) installed and running
- [ ] Python 3.10+ installed
- [ ] Network connectivity verified (DB and MQTT)
- [ ] Firewall rules configured
- [ ] Sufficient disk space (50 GB minimum)

#### Database Setup
- [ ] Run `sql/create_subscriber_tables.sql`
- [ ] Insert sample topic configurations
- [ ] Create database user with appropriate privileges
- [ ] Verify table creation
- [ ] Test database connectivity

#### Configuration
- [ ] Update `config/service_config.yaml` with production values
- [ ] Configure MQTT broker connection
- [ ] Configure database connection
- [ ] Set thread pool size
- [ ] Configure logging
- [ ] Set security options
- [ ] Validate configuration file

### Deployment Steps

#### Step 1: Install Dependencies
```batch
cd c:\Shakil\Cerevate\OPC_REPOS\mqtt_subscriber_service
pip install -r requirements.txt
```

**Verify Installation**:
```batch
python -c "import paho.mqtt.client as mqtt; import psycopg2; import yaml; print('All dependencies installed')"
```

#### Step 2: Database Setup
```batch
psql -h localhost -U postgres -d Historian_data -f sql/create_subscriber_tables.sql
```

**Verify Tables**:
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'historian_raw' 
AND table_name LIKE 'mqtt_%';
```

#### Step 3: Configure Service
```batch
notepad config\service_config.yaml
```

**Critical Settings**:
- Database connection string
- MQTT broker address
- Log directory path
- Thread pool size

#### Step 4: Test Configuration
```batch
python main.py --validate-config
```

#### Step 5: Run Test Publisher (Verification)
```batch
cd tests
python mqtt_test_publisher.py --single --topic test/gateway/data
```

#### Step 6: Start Service
```batch
REM Console mode (for testing)
python main.py

REM OR Windows service mode
install.bat
start_service.bat
```

#### Step 7: Verify Operation
```batch
REM Check logs
type logs\mqtt_subscriber_YYYY-MM-DD.log

REM Check database
psql -h localhost -U postgres -d Historian_data
SELECT COUNT(*) FROM historian_raw.mqtt_audit_main;
```

### Post-Deployment Validation

#### Validation Checklist
- [ ] Service started successfully
- [ ] MQTT connection established
- [ ] Database connection established
- [ ] Topics subscribed
- [ ] Worker threads started
- [ ] Test message processed successfully
- [ ] Audit records created
- [ ] Timeseries data inserted
- [ ] Event data inserted
- [ ] Logs writing correctly
- [ ] Health check passing
- [ ] Metrics collecting

#### Smoke Test
```batch
REM Run smoke test
python tests\end_to_end_test.py --smoke-test
```

### Rollback Plan

#### If Deployment Fails
1. Stop service: `stop_service.bat`
2. Restore previous version
3. Revert database changes
4. Check logs for errors
5. Fix issues
6. Retry deployment

#### Database Rollback
```sql
-- Drop new tables if needed
DROP TABLE IF EXISTS historian_raw.mqtt_audit_history;
DROP TABLE IF EXISTS historian_raw.mqtt_audit_main;
DROP TABLE IF EXISTS historian_raw.mqtt_topic_config;
```

---

## Monitoring & Maintenance

### Health Monitoring

#### Health Check Endpoint
**Optional REST API**:
```
GET /health
Response:
{
  "status": "healthy",
  "mqtt_connected": true,
  "db_connected": true,
  "worker_threads": 8,
  "active_threads": 8,
  "messages_processed": 12345,
  "uptime_seconds": 86400
}
```

#### Log Monitoring
**Key Log Patterns**:
- `ERROR`: Processing failures
- `WARNING`: Validation failures
- `INFO`: Normal operations
- `SECURITY`: Security events

**Log Files**:
- `logs/mqtt_subscriber_YYYY-MM-DD.log`: Main service log
- `logs/mqtt_subscriber_error_YYYY-MM-DD.log`: Error log
- `logs/mqtt_subscriber_security_YYYY-MM-DD.log`: Security log

### Performance Monitoring

#### Key Metrics
```sql
-- Messages processed per hour
SELECT 
    DATE_TRUNC('hour', first_received_time) AS hour,
    COUNT(*) AS messages_processed,
    AVG(processing_duration_ms) AS avg_latency_ms,
    COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) AS successful,
    COUNT(CASE WHEN status != 'COMPLETED' THEN 1 END) AS failed
FROM historian_raw.mqtt_audit_main
WHERE first_received_time > NOW() - INTERVAL '24 hours'
GROUP BY DATE_TRUNC('hour', first_received_time)
ORDER BY hour DESC;

-- Processing status summary
SELECT 
    status,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS percentage
FROM historian_raw.mqtt_audit_main
WHERE first_received_time > NOW() - INTERVAL '1 hour'
GROUP BY status;

-- Slowest messages
SELECT 
    message_id,
    topic_name,
    processing_duration_ms,
    tags_processed,
    events_generated,
    first_received_time
FROM historian_raw.mqtt_audit_main
WHERE processing_duration_ms > 1000
ORDER BY processing_duration_ms DESC
LIMIT 10;
```

### Maintenance Tasks

#### Daily
- [ ] Check service is running
- [ ] Review error logs
- [ ] Check database disk space
- [ ] Monitor message processing rate

#### Weekly
- [ ] Review performance metrics
- [ ] Check log file sizes
- [ ] Verify backup completion
- [ ] Review security logs
- [ ] Update topic configurations if needed

#### Monthly
- [ ] Review and archive old logs
- [ ] Database maintenance (VACUUM, ANALYZE)
- [ ] Review and optimize indexes
- [ ] Update dependencies if needed
- [ ] Review system capacity

#### Quarterly
- [ ] Full system audit
- [ ] Security review
- [ ] Performance optimization
- [ ] Disaster recovery test
- [ ] Documentation update

### Troubleshooting Guide

#### Issue: Service Won't Start
**Symptoms**: Service fails to start or crashes immediately

**Checks**:
1. Verify Python installed: `python --version`
2. Verify dependencies: `pip list`
3. Check configuration: `python main.py --validate-config`
4. Check logs: `type logs\mqtt_subscriber_*.log`
5. Test database connection: `psql -h localhost -U postgres -d Historian_data`
6. Test MQTT broker: `mosquitto_sub -h localhost -t test/#`

#### Issue: No Messages Processing
**Symptoms**: Service running but no messages in database

**Checks**:
1. Verify MQTT connection in logs
2. Check topic subscriptions
3. Verify topics active in database: `SELECT * FROM mqtt_topic_config WHERE is_active=TRUE`
4. Test publish: `python tests/mqtt_test_publisher.py --single`
5. Check worker threads in logs
6. Check database connection

#### Issue: High Latency
**Symptoms**: Messages processing slowly

**Checks**:
1. Check CPU usage
2. Check database performance
3. Check network latency
4. Review slow queries
5. Increase worker threads
6. Check database connection pool size

#### Issue: Memory Leak
**Symptoms**: Memory usage increasing over time

**Checks**:
1. Check for unclosed database connections
2. Check for unclosed MQTT connections
3. Review thread creation
4. Check log rotation
5. Monitor with memory profiler

---

## Appendix

### A. Configuration Reference

**config/service_config.yaml** - Complete Reference:
```yaml
service:
  name: "MQTT_Subscriber_Service"
  version: "1.0.0"
  worker_threads: 8                    # 4-32 recommended
  graceful_shutdown_timeout: 30        # seconds
  topic_cache_refresh_interval: 300    # seconds (5 minutes)
  tag_master_cache_refresh_interval: 300  # seconds (5 minutes)

mqtt:
  broker_host: "localhost"
  broker_port: 1883
  client_id: "MqttSubscriber01"
  qos: 1                               # 0, 1, or 2
  keep_alive: 60                       # seconds
  reconnect_on_failure: true
  reconnect_delay_seconds: 5
  max_reconnect_attempts: 10
  clean_session: true

security:
  encryption_enabled: false            # Set true for production
  tls_enabled: false
  tls_cert_path: ""
  tls_key_path: ""
  ca_cert_path: ""
  mqtt_username: ""
  mqtt_password: ""
  verify_certificates: true

database:
  host: "localhost"
  port: 5432
  database: "Historian_data"
  username: "postgres"
  password: "Database@19c"
  schema: "historian_raw"
  pool_size: 20
  pool_timeout: 30
  command_timeout: 30
  auto_commit: false
  
processing:
  enable_retries: false                # NO RETRY - fail fast
  max_batch_size: 1000
  message_timeout_seconds: 10
  duplicate_check_enabled: true
  validate_schema: true
  sanitize_inputs: true
  validate_against_tag_master: true    # Validate tags against tag_master cache
  reject_unknown_tags: true            # Reject tags not in tag_master
  reject_disabled_tags: true           # Reject tags with enabled=false
  
logging:
  level: "INFO"                        # DEBUG, INFO, WARNING, ERROR
  format: "json"                       # json or text
  log_dir: "./logs"
  max_file_size_mb: 100
  backup_count: 10
  console_output: true
  file_output: true
  separate_error_log: true
  separate_security_log: true

monitoring:
  health_check_enabled: true
  metrics_enabled: true
  metrics_interval_seconds: 60
  expose_rest_api: false
  rest_api_port: 8080
```

### B. Sample MQTT Payload

See [sample_mqtt_payload.json](sample_mqtt_payload.json) for complete example.

### C. SQL Queries

**Check Service Status**:
```sql
-- Recent messages
SELECT * FROM historian_raw.mqtt_audit_main 
ORDER BY first_received_time DESC LIMIT 10;

-- Processing summary (last hour)
SELECT status, COUNT(*) 
FROM historian_raw.mqtt_audit_main 
WHERE first_received_time > NOW() - INTERVAL '1 hour'
GROUP BY status;

-- Failed messages
SELECT message_id, error_message, first_received_time
FROM historian_raw.mqtt_audit_main 
WHERE status != 'COMPLETED'
ORDER BY first_received_time DESC;
```

### D. Performance Tuning

**Database**:
- Increase `shared_buffers` in postgresql.conf
- Tune `work_mem` and `maintenance_work_mem`
- Enable TimescaleDB compression
- Add indexes on frequently queried columns

**Application**:
- Increase `worker_threads` (8-16 optimal)
- Increase `database.pool_size` (20-50)
- Enable batch processing
- Tune MQTT QoS (QoS 0 fastest, QoS 2 most reliable)

**System**:
- Use SSD for database
- Increase available RAM
- Tune network buffers
- Disable unnecessary services

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-01-06 | Development Team | Initial implementation and test plan |

---

## Contact & Support

For questions or issues, contact the development team or refer to the README.md file in the project root.

---
**END OF DOCUMENT**
