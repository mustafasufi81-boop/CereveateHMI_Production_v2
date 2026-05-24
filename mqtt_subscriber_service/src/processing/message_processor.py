"""
Message Processor
Handles MQTT message parsing, validation, and storage
"""

import json
import time
import uuid
from datetime import datetime
from typing import Optional
from src.models.message_models import MQTTMessage, ParsedMessage, ValidationResult, ProcessingResult
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class MessageProcessor:
    """Processes MQTT messages with validation and storage"""
    
    def __init__(self, config: dict, topic_cache, tag_master_cache, 
                 audit_dao, historian_dao, validator):
        """
        Initialize Message Processor
        
        Args:
            config: Configuration dictionary
            topic_cache: TopicCache instance
            tag_master_cache: TagMasterCache instance
            audit_dao: AuditDAO instance
            historian_dao: HistorianDAO instance
            validator: MessageValidator instance
        """
        self.config = config
        self.topic_cache = topic_cache
        self.tag_master_cache = tag_master_cache
        self.audit_dao = audit_dao
        self.historian_dao = historian_dao
        self.validator = validator
        
        self.validate_tags = config['processing'].get('validate_against_tag_master', True)
        
        # Per-tag rate control state (tag_id -> last write time in seconds)
        self._last_write_times: dict = {}
        self._last_write_values: dict = {}
        
        logger.info("MessageProcessor initialized")
    
    def process_message(self, mqtt_msg: MQTTMessage) -> ProcessingResult:
        """
        Process MQTT message end-to-end
        
        Args:
            mqtt_msg: MQTTMessage object
            
        Returns:
            ProcessingResult with processing outcome
        """
        start_time = time.time()
        message_id = str(uuid.uuid4())
        audit_id = None
        
        try:
            # Step 1: Check if topic is enabled
            if not self.topic_cache.is_topic_enabled(mqtt_msg.topic):
                return ProcessingResult(
                    success=False,
                    message_id=message_id,
                    error_message=f"Topic '{mqtt_msg.topic}' not found or disabled"
                )
            
            # Step 2: Parse payload
            parsed_msg = self._parse_payload(mqtt_msg, message_id)
            if parsed_msg is None:
                return ProcessingResult(
                    success=False,
                    message_id=message_id,
                    error_message="Failed to parse message payload"
                )
            
            # Step 3: Create audit record
            try:
                audit_id = self.audit_dao.insert_audit_main(
                    message_id=message_id,
                    topic=mqtt_msg.topic,
                    payload_size=len(mqtt_msg.payload),
                    status='processing'
                )
                
                self.audit_dao.insert_audit_history(
                    audit_id=audit_id,
                    step='parse',
                    status='completed',
                    details='Message parsed successfully'
                )
            except Exception as e:
                logger.error(f"Failed to create audit record: {e}")
                # Continue processing even if audit fails
            
            # Step 4: Validate message
            validation = self.validator.validate(parsed_msg, self.tag_master_cache)
            
            if audit_id:
                self.audit_dao.insert_audit_history(
                    audit_id=audit_id,
                    step='validate',
                    status='completed' if validation.is_valid else 'failed',
                    details=json.dumps({
                        'errors': validation.errors,
                        'warnings': validation.warnings
                    })
                )
            
            if not validation.is_valid:
                if audit_id:
                    self.audit_dao.update_audit_main_status(
                        audit_id=audit_id,
                        status='failed',
                        error_message='; '.join(validation.errors)
                    )
                
                return ProcessingResult(
                    success=False,
                    message_id=message_id,
                    audit_id=audit_id,
                    error_message=f"Validation failed: {'; '.join(validation.errors)}",
                    processing_time_ms=(time.time() - start_time) * 1000
                )
            
            # Step 5: Insert into historian tables
            try:
                records_inserted = self._insert_historian_data(parsed_msg)
                
                if audit_id:
                    self.audit_dao.insert_audit_history(
                        audit_id=audit_id,
                        step='insert',
                        status='completed',
                        details=f'Inserted {records_inserted} records'
                    )
                    
                    self.audit_dao.update_audit_main_status(
                        audit_id=audit_id,
                        status='completed',
                        records_inserted=records_inserted
                    )
                
                processing_time = (time.time() - start_time) * 1000
                
                logger.info(f"Message processed successfully: {message_id} ({processing_time:.2f}ms)")
                
                return ProcessingResult(
                    success=True,
                    message_id=message_id,
                    audit_id=audit_id,
                    records_inserted=records_inserted,
                    processing_time_ms=processing_time
                )
                
            except Exception as e:
                logger.error(f"Failed to insert historian data: {e}")
                
                if audit_id:
                    self.audit_dao.insert_audit_history(
                        audit_id=audit_id,
                        step='insert',
                        status='failed',
                        details=str(e)
                    )
                    
                    self.audit_dao.update_audit_main_status(
                        audit_id=audit_id,
                        status='failed',
                        error_message=str(e)
                    )
                
                return ProcessingResult(
                    success=False,
                    message_id=message_id,
                    audit_id=audit_id,
                    error_message=f"Database insert failed: {e}",
                    processing_time_ms=(time.time() - start_time) * 1000
                )
        
        except Exception as e:
            logger.error(f"Unexpected error processing message: {e}")
            
            if audit_id:
                self.audit_dao.update_audit_main_status(
                    audit_id=audit_id,
                    status='failed',
                    error_message=str(e)
                )
            
            return ProcessingResult(
                success=False,
                message_id=message_id,
                audit_id=audit_id,
                error_message=f"Processing error: {e}",
                processing_time_ms=(time.time() - start_time) * 1000
            )
    
    def _parse_payload(self, mqtt_msg: MQTTMessage, message_id: str) -> Optional[ParsedMessage]:
        """
        Parse MQTT payload to structured data
        Supports both single-tag and batch message formats
        
        Args:
            mqtt_msg: MQTTMessage object
            message_id: Unique message identifier
            
        Returns:
            ParsedMessage or None if parsing fails
        """
        try:
            # Decode payload
            payload_str = mqtt_msg.payload.decode('utf-8')
            payload_data = json.loads(payload_str)
            
            # Check if this is a batch message with 'values' array
            if 'values' in payload_data and isinstance(payload_data['values'], list):
                # Batch format - store entire payload for batch processing
                parsed = ParsedMessage(
                    message_id=message_id,
                    topic=mqtt_msg.topic,
                    received_at=mqtt_msg.received_at,
                    payload_data=payload_data,
                    tag_id=None,  # Batch message, no single tag_id
                    timestamp=self._parse_timestamp(payload_data.get('timestamp')),
                    quality='G',
                    sample_source='MQTT',
                    mapping_version=1
                )
                return parsed
            
            # Single-tag format (legacy)
            parsed = ParsedMessage(
                message_id=message_id,
                topic=mqtt_msg.topic,
                received_at=mqtt_msg.received_at,
                payload_data=payload_data,
                tag_id=payload_data.get('tag_id'),
                timestamp=self._parse_timestamp(payload_data.get('timestamp')),
                quality=payload_data.get('quality', 'G'),
                sample_source=payload_data.get('source', 'MQTT'),
                mapping_version=payload_data.get('version', 1)
            )
            
            # Parse value based on type
            value = payload_data.get('value')
            if value is not None:
                if isinstance(value, bool):
                    parsed.value_bool = value
                elif isinstance(value, (int, float)):
                    parsed.value_num = float(value)
                else:
                    parsed.value_text = str(value)
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logger.error(f"Payload parsing error: {e}")
            return None
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> datetime:
        """Parse timestamp string to datetime"""
        if timestamp_str is None:
            return datetime.utcnow()
        
        if isinstance(timestamp_str, datetime):
            return timestamp_str
        
        try:
            if '+' in timestamp_str or timestamp_str.endswith('Z'):
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                return datetime.fromisoformat(timestamp_str)
        except Exception:
            return datetime.utcnow()
    
    def _should_write(self, tag_id: str, value_num) -> bool:
        """
        Rate control: check if enough time has elapsed since last write,
        and if value has changed beyond deadband. Respects db_logging_interval_ms
        and deadband_value from tag_master.
        """
        tag_cfg = self.tag_master_cache.get(tag_id)
        interval_ms = tag_cfg['db_logging_interval_ms'] if tag_cfg else 5000
        deadband = tag_cfg['deadband_value'] if tag_cfg else 0.0
        interval_s = interval_ms / 1000.0

        now = time.time()
        last_time = self._last_write_times.get(tag_id)

        # First sample for this tag — always write
        if last_time is None:
            self._last_write_times[tag_id] = now
            self._last_write_values[tag_id] = value_num
            return True

        elapsed = now - last_time

        if elapsed < interval_s:
            return False

        # Interval elapsed — check deadband/change
        last_val = self._last_write_values.get(tag_id)
        if value_num is not None and last_val is not None and deadband > 0:
            if abs(value_num - last_val) <= deadband:
                return False

        elif value_num is not None and last_val is not None and deadband == 0:
            if value_num == last_val:
                return False

        self._last_write_times[tag_id] = now
        self._last_write_values[tag_id] = value_num
        return True

    def _insert_historian_data(self, parsed_msg: ParsedMessage) -> int:
        """
        Insert data into historian tables
        Supports both single-tag and batch message formats
        
        Args:
            parsed_msg: ParsedMessage object
            
        Returns:
            Number of records inserted
        """
        total_records = 0
        payload_data = parsed_msg.payload_data
        
        # Check if this is a batch message with 'values' array
        if 'values' in payload_data and isinstance(payload_data['values'], list):
            # Process batch message
            timeseries_records = []
            
            for value_entry in payload_data['values']:
                tag_id = value_entry.get('tag')
                plc_id = value_entry.get('plcId')
                data_type = value_entry.get('dataType', 'float')
                
                # Process samples array if present
                samples = value_entry.get('samples', [])
                if samples:
                    for sample in samples:
                        raw_val = sample.get('value')
                        num_val = float(raw_val) if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool) else None
                        if not self._should_write(tag_id, num_val):
                            continue
                        record = self._create_timeseries_record(
                            tag_id=tag_id,
                            value=raw_val,
                            quality=sample.get('quality', 'Good'),
                            timestamp=self._parse_timestamp(sample.get('timestamp')),
                            data_type=data_type,
                            plc_id=plc_id
                        )
                        timeseries_records.append(record)
                else:
                    # No samples, use latest value
                    raw_val = value_entry.get('value')
                    num_val = float(raw_val) if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool) else None
                    if self._should_write(tag_id, num_val):
                        record = self._create_timeseries_record(
                            tag_id=tag_id,
                            value=raw_val,
                            quality=value_entry.get('quality', 'Good'),
                            timestamp=self._parse_timestamp(value_entry.get('timestamp')),
                            data_type=data_type,
                            plc_id=plc_id
                        )
                        timeseries_records.append(record)
            
            # Batch insert all timeseries records
            if timeseries_records:
                total_records += self.historian_dao.insert_timeseries_batch(timeseries_records)
                logger.info(f"Inserted {len(timeseries_records)} timeseries records from batch message")
        
        else:
            # Single-tag message (legacy format)
            if self._should_write(parsed_msg.tag_id, parsed_msg.value_num):
                tag_data = {
                    'time': parsed_msg.timestamp,
                    'tag_id': parsed_msg.tag_id,
                    'value_num': parsed_msg.value_num,
                    'value_text': parsed_msg.value_text,
                    'value_bool': parsed_msg.value_bool,
                    'quality': parsed_msg.quality,
                    'sample_source': parsed_msg.sample_source,
                    'mapping_version': parsed_msg.mapping_version
                }
                
                # Insert into historian_timeseries
                total_records += self.historian_dao.insert_timeseries_batch([tag_data])
        
        # NOTE: alarm_summary processing intentionally removed (May 2026).
        # Alarm evaluation and historian_events inserts are handled exclusively by
        # C# AlarmEvaluationService (Services/AlarmEvaluation/). This subscriber
        # processes tag VALUE data only. Do NOT add alarm INSERT logic here.

        return total_records
    
    def _create_timeseries_record(self, tag_id: str, value, quality: str, 
                                   timestamp: datetime, data_type: str, plc_id: str = None) -> dict:
        """
        Create a timeseries record from tag data
        
        Args:
            tag_id: Tag identifier
            value: Tag value
            quality: Quality code
            timestamp: Sample timestamp
            data_type: Data type (float, int, bool, string)
            plc_id: PLC identifier (optional)
            
        Returns:
            Dictionary formatted for historian_timeseries insert
        """
        # Normalize quality code to single character
        quality_code = 'G' if quality in ['Good', 'G'] else ('B' if quality in ['Bad', 'B'] else 'U')
        
        record = {
            'time': timestamp,
            'tag_id': tag_id,
            'value_num': None,
            'value_text': None,
            'value_bool': None,
            'quality': quality_code,
            'sample_source': 'MQTT',
            'mapping_version': 1,
            'opc_timestamp': timestamp  # Use same timestamp for OPC timestamp
        }
        
        # Parse value based on data type
        if value is not None:
            if data_type in ['float', 'double', 'real']:
                record['value_num'] = float(value)
            elif data_type in ['int', 'dint', 'uint', 'word', 'dword']:
                record['value_num'] = float(value)  # Store as numeric
            elif data_type in ['bool', 'boolean']:
                record['value_bool'] = bool(value)
            elif data_type in ['string', 'str']:
                record['value_text'] = str(value)
            else:
                # Default to numeric if type unknown
                if isinstance(value, bool):
                    record['value_bool'] = value
                elif isinstance(value, (int, float)):
                    record['value_num'] = float(value)
                else:
                    record['value_text'] = str(value)
        
        return record
