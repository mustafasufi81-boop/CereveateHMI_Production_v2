"""
Data Models for MQTT Subscriber Service
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Dict


@dataclass
class MQTTMessage:
    """MQTT Message model"""
    topic: str
    payload: bytes
    qos: int
    received_at: datetime = field(default_factory=datetime.utcnow)
    
    def __str__(self):
        return f"MQTTMessage(topic={self.topic}, size={len(self.payload)}, qos={self.qos})"


@dataclass
class ParsedMessage:
    """Parsed MQTT message with extracted data"""
    message_id: str
    topic: str
    received_at: datetime
    payload_data: Dict[str, Any]
    
    # Extracted fields
    tag_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    value_num: Optional[float] = None
    value_text: Optional[str] = None
    value_bool: Optional[bool] = None
    quality: str = 'G'
    
    # Metadata
    sample_source: str = 'MQTT'
    mapping_version: int = 1
    
    def __str__(self):
        return f"ParsedMessage(id={self.message_id}, tag={self.tag_id}, value={self.value_num or self.value_text or self.value_bool})"


@dataclass
class ValidationResult:
    """Validation result model"""
    is_valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    
    def add_error(self, error: str):
        """Add validation error"""
        self.is_valid = False
        self.errors.append(error)
    
    def add_warning(self, warning: str):
        """Add validation warning"""
        self.warnings.append(warning)
    
    def has_errors(self) -> bool:
        """Check if validation has errors"""
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        """Check if validation has warnings"""
        return len(self.warnings) > 0
    
    def __str__(self):
        status = "VALID" if self.is_valid else "INVALID"
        return f"ValidationResult({status}, errors={len(self.errors)}, warnings={len(self.warnings)})"


@dataclass
class ProcessingResult:
    """Message processing result"""
    success: bool
    message_id: str
    audit_id: Optional[int] = None
    records_inserted: int = 0
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0
    
    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return f"ProcessingResult({status}, id={self.message_id}, records={self.records_inserted}, time={self.processing_time_ms:.2f}ms)"
