# MQTT Subscriber Service - Test Plan

## Overview

Comprehensive test plan for validating the MQTT Subscriber Service implementation across all phases.

## Test Environment

### Hardware Requirements
- CPU: 4 cores minimum
- RAM: 8 GB minimum
- Disk: 20 GB available space

### Software Requirements
- Python 3.10+
- PostgreSQL 14+ with TimescaleDB
- MQTT Broker (Mosquitto or similar)
- MQTT Test Client (MQTT Explorer or mosquitto_pub)

## Test Phases

### Phase 1: Unit Tests

#### 1.1 Configuration Loader Tests
```python
def test_config_loader():
    """Test configuration loading"""
    config = ConfigLoader.load('config/service_config.yaml')
    assert 'database' in config
    assert 'mqtt' in config
    assert 'processing' in config

def test_config_env_override():
    """Test environment variable override"""
    os.environ['DB_HOST'] = 'test-host'
    config = ConfigLoader.load('config/service_config.yaml')
    assert config['database']['host'] == 'test-host'
```

**Expected Results:** All configuration sections loaded correctly

#### 1.2 Database Connection Tests
```python
def test_database_connection():
    """Test database connectivity"""
    db = DatabaseConnection.get_instance()
    db.initialize(config['database'])
    assert db.test_connection() == True

def test_connection_pool():
    """Test connection pooling"""
    db = DatabaseConnection.get_instance()
    with db.get_connection() as conn:
        assert conn is not None
```

**Expected Results:** Database connections established successfully

#### 1.3 DAO Tests
```python
def test_audit_dao_insert():
    """Test audit record insertion"""
    dao = AuditDAO(db)
    audit_id = dao.insert_audit_main(
        message_id='TEST-001',
        topic='test/topic',
        payload_size=100,
        status='processing'
    )
    assert audit_id > 0

def test_historian_dao_insert():
    """Test timeseries insertion"""
    dao = HistorianDAO(db)
    count = dao.insert_timeseries_batch([{
        'time': datetime.utcnow(),
        'tag_id': 'TEST-TAG',
        'value_num': 123.45,
        'quality': 'G'
    }])
    assert count == 1
```

**Expected Results:** Database operations succeed

#### 1.4 Validator Tests
```python
def test_validator_valid_message():
    """Test validation of valid message"""
    validator = MessageValidator(config)
    msg = ParsedMessage(...)
    result = validator.validate(msg, tag_cache)
    assert result.is_valid

def test_validator_invalid_tag():
    """Test validation with invalid tag"""
    validator = MessageValidator(config)
    msg = ParsedMessage(tag_id='INVALID')
    result = validator.validate(msg, tag_cache)
    assert not result.is_valid
    assert 'not found' in result.errors[0]
```

**Expected Results:** Validation logic works correctly

#### 1.5 Sanitizer Tests
```python
def test_sql_injection_detection():
    """Test SQL injection detection"""
    sanitizer = InputSanitizer(config)
    is_safe, error = sanitizer.check_sql_injection("'; DROP TABLE users;--")
    assert not is_safe

def test_sanitize_tag_id():
    """Test tag ID sanitization"""
    sanitizer = InputSanitizer(config)
    result = sanitizer.sanitize_tag_id("TAG-001<script>")
    assert '<script>' not in result
```

**Expected Results:** Injection attempts detected and sanitized

### Phase 2: Integration Tests

#### 2.1 End-to-End Message Flow
```
Test: Send MQTT message → Process → Store → Verify

Steps:
1. Publish MQTT message with valid payload
2. Wait for processing (5 seconds)
3. Query historian_timeseries for record
4. Query mqtt_audit_main for audit record
5. Verify data integrity

Expected Results:
- Message appears in historian_timeseries
- Audit record shows 'completed' status
- Values match original message
```

#### 2.2 Cache Refresh Test
```
Test: Cache auto-refresh functionality

Steps:
1. Start service
2. Insert new topic in mqtt_topic_config
3. Wait for cache refresh (5 minutes + 10 seconds)
4. Publish message to new topic
5. Verify message processed

Expected Results:
- New topic loaded into cache
- Message processed successfully
```

#### 2.3 Tag Validation Test
```
Test: Tag master validation

Steps:
1. Send message with valid tag_id
2. Verify processing succeeds
3. Send message with invalid tag_id
4. Verify processing fails with validation error
5. Check audit_history for validation step

Expected Results:
- Valid tag processed
- Invalid tag rejected with error
- Audit trail shows validation failure
```

#### 2.4 Multi-Threading Test
```
Test: Concurrent message processing

Steps:
1. Configure worker_threads = 8
2. Publish 100 messages rapidly
3. Monitor processing
4. Verify all messages processed

Expected Results:
- All messages processed within 30 seconds
- No deadlocks or race conditions
- Audit records for all messages
```

### Phase 3: Performance Tests

#### 3.1 Throughput Test
```
Test: Maximum message throughput

Configuration:
- worker_threads: 16
- task_queue_size: 5000

Steps:
1. Publish 10,000 messages at 100 msg/s
2. Monitor processing rate
3. Check metrics

Success Criteria:
- Processing rate ≥ 80 msg/s
- Queue never full (no dropped messages)
- Average processing time < 50ms
- Success rate > 99%
```

#### 3.2 Load Test
```
Test: Sustained load handling

Steps:
1. Publish 100 msg/s for 1 hour
2. Monitor memory usage
3. Monitor CPU usage
4. Check for memory leaks

Success Criteria:
- Memory usage stable (< 500 MB)
- CPU usage < 80%
- No memory leaks
- All messages processed
```

#### 3.3 Stress Test
```
Test: Extreme load conditions

Steps:
1. Publish 1,000 msg/s for 5 minutes
2. Monitor queue size
3. Check dropped messages

Success Criteria:
- Service remains stable
- Graceful degradation (messages may be dropped)
- No crashes or deadlocks
```

### Phase 4: Security Tests

#### 4.1 SQL Injection Test
```
Test: SQL injection prevention

Payloads:
- "'; DROP TABLE historian_timeseries;--"
- "1' OR '1'='1"
- "UNION SELECT * FROM pg_tables"

Expected Results:
- All payloads sanitized or rejected
- No SQL executed from payload
- Audit log shows sanitization
```

#### 4.2 Command Injection Test
```
Test: Command injection prevention

Payloads:
- "; rm -rf /"
- "$(whoami)"
- "`cat /etc/passwd`"

Expected Results:
- All payloads sanitized
- No commands executed
```

#### 4.3 TLS/mTLS Test
```
Test: Secure MQTT connection

Steps:
1. Configure TLS with certificates
2. Connect to secure broker
3. Verify encrypted connection
4. Try connecting without certs (should fail)

Expected Results:
- TLS connection established
- Certificates validated
- Unencrypted connection rejected
```

#### 4.4 Authentication Test
```
Test: MQTT authentication

Steps:
1. Configure username/password
2. Connect with correct credentials
3. Try connecting with wrong credentials

Expected Results:
- Correct credentials accepted
- Wrong credentials rejected
- Audit log shows authentication
```

### Phase 5: Failure Tests

#### 5.1 Database Failure Test
```
Test: Database connectivity loss

Steps:
1. Start service
2. Stop PostgreSQL
3. Publish messages
4. Restart PostgreSQL
5. Check service recovery

Expected Results:
- Service logs database errors
- Messages queued (if queue not full)
- Service attempts reconnection
- Processing resumes after recovery
```

#### 5.2 MQTT Broker Failure Test
```
Test: MQTT broker connectivity loss

Steps:
1. Start service
2. Stop MQTT broker
3. Restart MQTT broker
4. Verify reconnection

Expected Results:
- Service logs disconnection
- Service attempts reconnection
- Subscriptions restored
- Processing resumes
```

#### 5.3 Queue Overflow Test
```
Test: Task queue full handling

Steps:
1. Configure task_queue_size: 10
2. Publish 100 messages rapidly
3. Monitor dropped messages

Expected Results:
- Queue fills up
- Additional messages dropped
- Metrics show queue_full_count > 0
- Service remains stable
```

### Phase 6: Data Integrity Tests

#### 6.1 Duplicate Message Test
```
Test: Duplicate message handling

Steps:
1. Send message with message_id: 'MSG-001'
2. Send same message again
3. Check audit_main for duplicates

Expected Results:
- Both messages processed (no deduplication by design)
- Two audit records created
- OR: If duplicate detection added, second rejected
```

#### 6.2 Data Type Validation Test
```
Test: Data type consistency

Test Cases:
1. Numeric tag with text value → Warning
2. Boolean tag with numeric value → Warning
3. Text tag with boolean value → Warning

Expected Results:
- Type mismatches generate warnings
- Messages still processed (warnings don't fail)
- Warnings logged in audit_history
```

#### 6.3 Range Validation Test
```
Test: Numeric range validation

Test Cases:
1. Value below min_value → Warning
2. Value above max_value → Warning
3. Value within range → Success

Expected Results:
- Out-of-range values generate warnings
- Messages still processed
- Warnings logged
```

### Phase 7: Monitoring Tests

#### 7.1 Health Check Test
```
Test: Health check endpoint

Steps:
1. Start service
2. Run health check
3. Stop database
4. Run health check again

Expected Results:
- First check: all components healthy
- Second check: database unhealthy, overall degraded
```

#### 7.2 Metrics Collection Test
```
Test: Metrics accuracy

Steps:
1. Reset metrics
2. Send 100 messages (95 valid, 5 invalid)
3. Check metrics

Expected Results:
- messages_received: 100
- messages_processed: 95
- messages_failed: 5
- success_rate: 95%
- Average processing time logged
```

#### 7.3 Logging Test
```
Test: Log rotation and formatting

Steps:
1. Generate logs exceeding 100 MB
2. Verify rotation occurs
3. Check log format (JSON)

Expected Results:
- Logs rotated at 100 MB
- 10 backup files maintained
- All logs in JSON format
- No log loss during rotation
```

## Test Data

### Valid MQTT Message
```json
{
  "tag_id": "TEST-TAG-001",
  "timestamp": "2024-01-15T10:30:00Z",
  "value": 123.45,
  "quality": "G",
  "source": "MQTT",
  "version": 1
}
```

### Invalid Messages

#### Missing Required Field
```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "value": 123.45
}
```

#### Invalid Tag
```json
{
  "tag_id": "INVALID-TAG",
  "timestamp": "2024-01-15T10:30:00Z",
  "value": 123.45,
  "quality": "G"
}
```

#### Invalid Quality Code
```json
{
  "tag_id": "TEST-TAG-001",
  "timestamp": "2024-01-15T10:30:00Z",
  "value": 123.45,
  "quality": "X"
}
```

## Test Execution

### Manual Testing
```batch
# 1. Setup test environment
python scripts/setup_test_env.py

# 2. Run unit tests
pytest tests/ -v

# 3. Start service
run_service.bat

# 4. Run integration tests
python tests/test_integration.py

# 5. Run performance tests
python tests/test_performance.py

# 6. Generate test report
pytest tests/ --html=report.html
```

### Automated Testing
```batch
# Run all tests
pytest tests/ -v --cov=src --cov-report=html

# Run specific test category
pytest tests/test_unit.py -v
pytest tests/test_integration.py -v
pytest tests/test_performance.py -v
```

## Test Results Template

### Test Execution Summary
```
Test Phase: Unit Tests
Date: 2024-01-15
Tester: [Name]

Total Tests: 50
Passed: 48
Failed: 2
Skipped: 0
Success Rate: 96%

Failed Tests:
1. test_database_connection_timeout - Timeout too short
2. test_mqtt_reconnection - Broker not available

Issues Found:
- Connection timeout needs adjustment
- MQTT broker configuration issue

Next Actions:
- Increase connection timeout to 30s
- Fix MQTT broker configuration
```

## Acceptance Criteria

### Functional Requirements
- [ ] All MQTT messages processed correctly
- [ ] Tag validation works against tag_master
- [ ] Audit trail captures all message lifecycle
- [ ] Database inserts successful
- [ ] Health checks return accurate status
- [ ] Metrics collection accurate

### Performance Requirements
- [ ] Processing rate ≥ 50 msg/s (8 workers)
- [ ] Average processing time < 50ms
- [ ] Memory usage < 500 MB (sustained)
- [ ] CPU usage < 80% (sustained)
- [ ] Success rate > 95%

### Security Requirements
- [ ] SQL injection prevented
- [ ] Command injection prevented
- [ ] Input sanitization effective
- [ ] TLS connection works
- [ ] Authentication enforced
- [ ] Credentials not logged

### Reliability Requirements
- [ ] Service runs for 24 hours without crash
- [ ] Graceful handling of connection failures
- [ ] Proper shutdown on SIGTERM
- [ ] No memory leaks
- [ ] No deadlocks

## Sign-Off

### Test Lead Approval
```
Name: _______________________
Date: _______________________
Signature: __________________
```

### Quality Assurance Approval
```
Name: _______________________
Date: _______________________
Signature: __________________
```

### Product Owner Approval
```
Name: _______________________
Date: _______________________
Signature: __________________
```

---

**Document Version:** 1.0  
**Last Updated:** 2024-01-15
