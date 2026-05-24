"""
Input Sanitizer
Sanitizes and validates input data against injection attacks
"""

import re
import html
from typing import Any, Optional
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class InputSanitizer:
    """Sanitizes input data to prevent injection attacks (OWASP A03:2021)"""
    
    # SQL injection patterns
    SQL_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)",
        r"(--|\;|\/\*|\*\/)",
        r"(\bOR\b.*=.*)",
        r"(\bAND\b.*=.*)",
        r"('.*--)",
        r"(UNION.*SELECT)"
    ]
    
    # Command injection patterns
    CMD_PATTERNS = [
        r"[;&|`$()]",
        r"(\.\./)",
        r"(\\x[0-9a-fA-F]{2})"
    ]
    
    def __init__(self, config: dict):
        """
        Initialize Input Sanitizer
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.enable_sanitization = config['security'].get('enable_input_sanitization', True)
        
        logger.info(f"InputSanitizer initialized (enabled={self.enable_sanitization})")
    
    def sanitize_string(self, value: str, max_length: int = 1000) -> str:
        """
        Sanitize string input
        
        Args:
            value: Input string
            max_length: Maximum allowed length
            
        Returns:
            Sanitized string
        """
        if not self.enable_sanitization:
            return value
        
        if value is None:
            return ""
        
        # Convert to string
        value = str(value)
        
        # Truncate to max length
        if len(value) > max_length:
            logger.warning(f"String truncated from {len(value)} to {max_length} characters")
            value = value[:max_length]
        
        # Remove null bytes
        value = value.replace('\0', '')
        
        # HTML encode special characters
        value = html.escape(value)
        
        return value
    
    def check_sql_injection(self, value: str) -> tuple[bool, Optional[str]]:
        """
        Check for SQL injection patterns
        
        Args:
            value: Input string to check
            
        Returns:
            Tuple of (is_safe, detected_pattern)
        """
        if not self.enable_sanitization:
            return True, None
        
        value_upper = value.upper()
        
        for pattern in self.SQL_PATTERNS:
            if re.search(pattern, value_upper, re.IGNORECASE):
                logger.warning(f"Potential SQL injection detected: {pattern}")
                return False, f"Potential SQL injection pattern: {pattern}"
        
        return True, None
    
    def check_command_injection(self, value: str) -> tuple[bool, Optional[str]]:
        """
        Check for command injection patterns
        
        Args:
            value: Input string to check
            
        Returns:
            Tuple of (is_safe, detected_pattern)
        """
        if not self.enable_sanitization:
            return True, None
        
        for pattern in self.CMD_PATTERNS:
            if re.search(pattern, value):
                logger.warning(f"Potential command injection detected: {pattern}")
                return False, f"Potential command injection pattern: {pattern}"
        
        return True, None
    
    def sanitize_tag_id(self, tag_id: str) -> str:
        """
        Sanitize tag ID
        
        Args:
            tag_id: Tag identifier
            
        Returns:
            Sanitized tag ID
        """
        if not tag_id:
            return ""
        
        # Allow only alphanumeric, underscore, hyphen, dot
        sanitized = re.sub(r'[^a-zA-Z0-9_\-\.]', '', tag_id)
        
        # Truncate to 100 characters
        return sanitized[:100]
    
    def sanitize_topic(self, topic: str) -> str:
        """
        Sanitize MQTT topic
        
        Args:
            topic: MQTT topic string
            
        Returns:
            Sanitized topic
        """
        if not topic:
            return ""
        
        # Remove control characters
        sanitized = ''.join(c for c in topic if ord(c) >= 32)
        
        # Truncate to 255 characters
        return sanitized[:255]
    
    def sanitize_numeric(self, value: Any) -> Optional[float]:
        """
        Sanitize numeric value
        
        Args:
            value: Input value
            
        Returns:
            Float value or None if invalid
        """
        try:
            return float(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid numeric value: {value}")
            return None
    
    def sanitize_boolean(self, value: Any) -> Optional[bool]:
        """
        Sanitize boolean value
        
        Args:
            value: Input value
            
        Returns:
            Boolean value or None if invalid
        """
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            value_lower = value.lower()
            if value_lower in ['true', '1', 'yes', 'on']:
                return True
            elif value_lower in ['false', '0', 'no', 'off']:
                return False
        
        if isinstance(value, (int, float)):
            return bool(value)
        
        logger.warning(f"Invalid boolean value: {value}")
        return None
