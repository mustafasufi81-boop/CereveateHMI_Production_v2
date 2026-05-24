"""
Message Validator
Validates MQTT messages and data against tag_master
"""

from typing import Optional
from src.models.message_models import ParsedMessage, ValidationResult
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class MessageValidator:
    """Validates MQTT messages with OWASP security standards"""
    
    def __init__(self, config: dict):
        """
        Initialize Message Validator
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.validate_tags = config['processing'].get('validate_against_tag_master', True)
        self.max_payload_size = config['processing'].get('max_payload_size_bytes', 1048576)
        
        logger.info("MessageValidator initialized")
    
    def validate(self, parsed_msg: ParsedMessage, tag_master_cache) -> ValidationResult:
        """
        Validate parsed message
        
        Args:
            parsed_msg: ParsedMessage object
            tag_master_cache: TagMasterCache instance
            
        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(is_valid=True)
        
        # Check if this is a batch message with 'values' array
        is_batch_message = 'values' in parsed_msg.payload_data and isinstance(parsed_msg.payload_data.get('values'), list)
        
        if is_batch_message:
            # For batch messages, validate the structure but skip individual tag validation
            values = parsed_msg.payload_data.get('values', [])
            if not values:
                result.add_error("Batch message has empty 'values' array")
            else:
                # Validate each value entry has required fields
                for idx, value_entry in enumerate(values):
                    if 'tag' not in value_entry:
                        result.add_warning(f"Value entry {idx} missing 'tag' field")
                    if 'value' not in value_entry and 'samples' not in value_entry:
                        result.add_warning(f"Value entry {idx} missing 'value' or 'samples' field")
            return result
        
        # For single tag messages, validate required fields
        # 1. Validate required fields
        if not parsed_msg.tag_id:
            result.add_error("Missing required field: tag_id")
        
        if not parsed_msg.timestamp:
            result.add_error("Missing required field: timestamp")
        
        # 2. Validate at least one value field is present
        if (parsed_msg.value_num is None and 
            parsed_msg.value_text is None and 
            parsed_msg.value_bool is None):
            result.add_error("At least one value field (value_num, value_text, value_bool) must be present")
        
        # 3. Validate quality code
        if parsed_msg.quality not in ['G', 'B', 'U']:
            result.add_error(f"Invalid quality code: {parsed_msg.quality}. Must be G, B, or U")
        
        # 4. Validate against tag_master (if enabled)
        if self.validate_tags and parsed_msg.tag_id:
            tag_valid, tag_error = tag_master_cache.validate_tag(parsed_msg.tag_id)
            if not tag_valid:
                result.add_error(tag_error)
            else:
                # Validate data type consistency
                tag_data_type = tag_master_cache.get_data_type(parsed_msg.tag_id)
                if tag_data_type:
                    type_valid, type_warning = self._validate_data_type(parsed_msg, tag_data_type)
                    if not type_valid:
                        result.add_warning(type_warning)
                
                # Validate numeric range
                if parsed_msg.value_num is not None:
                    range_valid, range_warning = tag_master_cache.validate_value_range(
                        parsed_msg.tag_id, 
                        parsed_msg.value_num
                    )
                    if not range_valid:
                        result.add_warning(range_warning)
        
        # 5. Validate string lengths
        if parsed_msg.value_text and len(parsed_msg.value_text) > 1000:
            result.add_warning(f"value_text exceeds recommended length: {len(parsed_msg.value_text)} > 1000")
        
        if parsed_msg.tag_id and len(parsed_msg.tag_id) > 100:
            result.add_error(f"tag_id exceeds maximum length: {len(parsed_msg.tag_id)} > 100")
        
        return result
    
    def _validate_data_type(self, parsed_msg: ParsedMessage, expected_type: str) -> tuple[bool, Optional[str]]:
        """
        Validate data type consistency
        
        Args:
            parsed_msg: ParsedMessage object
            expected_type: Expected data type from tag_master
            
        Returns:
            Tuple of (is_valid, warning_message)
        """
        expected_type_lower = expected_type.lower()
        
        # Map expected types to value fields
        if expected_type_lower in ['int', 'float', 'double', 'real', 'numeric']:
            if parsed_msg.value_num is None:
                return False, f"Expected numeric value for tag '{parsed_msg.tag_id}' (type: {expected_type})"
        
        elif expected_type_lower in ['bool', 'boolean']:
            if parsed_msg.value_bool is None:
                return False, f"Expected boolean value for tag '{parsed_msg.tag_id}' (type: {expected_type})"
        
        elif expected_type_lower in ['string', 'text', 'varchar']:
            if parsed_msg.value_text is None:
                return False, f"Expected text value for tag '{parsed_msg.tag_id}' (type: {expected_type})"
        
        return True, None
    
    def validate_topic(self, topic: str) -> tuple[bool, Optional[str]]:
        """
        Validate MQTT topic format
        
        Args:
            topic: MQTT topic string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not topic:
            return False, "Topic cannot be empty"
        
        if len(topic) > 255:
            return False, f"Topic exceeds maximum length: {len(topic)} > 255"
        
        # Check for invalid characters
        invalid_chars = ['\0', '\r', '\n']
        for char in invalid_chars:
            if char in topic:
                return False, f"Topic contains invalid character: {repr(char)}"
        
        return True, None
    
    def validate_payload_size(self, payload_size: int) -> tuple[bool, Optional[str]]:
        """
        Validate payload size
        
        Args:
            payload_size: Size of payload in bytes
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if payload_size > self.max_payload_size:
            return False, f"Payload size {payload_size} exceeds maximum {self.max_payload_size}"
        
        return True, None
