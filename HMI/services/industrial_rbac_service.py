"""
Industrial RBAC Service
Implements Separation of Duties, Change Control, and Certification Management
Standards: ISA-18.2, ISA-61511, IEC 62443, NIST CSF

Author: Automation Team
Version: 1.0
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class OperationRequest:
    """Represents an operation requiring approval"""
    operation_type: str
    operation_id: str
    operation_description: str
    requested_by: int
    request_reason: str
    priority: str = 'NORMAL'
    execution_deadline: Optional[datetime] = None
    impact_assessment: str = ''
    rollback_procedure: str = ''
    additional_data: Dict[str, Any] = None


@dataclass
class OperationApprovalResult:
    """Result of approval request"""
    approval_id: int
    status: str  # REQUESTED, APPROVED, REJECTED, EXPIRED, CANCELLED
    approval_code: Optional[str] = None
    approval_expires_at: Optional[datetime] = None
    sod_violation: bool = False
    sod_violation_reason: Optional[str] = None
    message: str = ''


class IndustrialRBACService:
    """
    Enforces industrial-grade RBAC with SoD, change control, and certifications
    """
    
    def __init__(self, db_connection):
        """
        Initialize RBAC service
        
        Args:
            db_connection: Database connection service
        """
        self.db = db_connection
        logger.info("[INIT] Industrial RBAC Service initialized")
    
    # ========================== SEPARATION OF DUTIES ==========================
    
    def check_sod_violation(
        self,
        operation_type: str,
        requested_by: int,
        approved_by: Optional[int] = None,
        executed_by: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if operation violates Separation of Duties rules
        
        Args:
            operation_type: Type of operation
            requested_by: User ID of requester
            approved_by: User ID of approver (if applicable)
            executed_by: User ID of executor (if applicable)
            
        Returns:
            (violation_detected, violation_reason)
        """
        try:
            query = """
                SELECT * FROM historian_meta.check_sod_violation(%s, %s, %s, %s)
            """
            result = self.db.execute_query(
                query,
                (operation_type, requested_by, approved_by, executed_by),
                fetch=True
            )
            
            if result and len(result) > 0:
                violation = result[0][0]  # violation_detected
                reason = result[0][1]     # violation_reason
                
                if violation:
                    logger.warning(
                        f"⚠️ SoD violation detected for {operation_type}: {reason}"
                    )
                
                return violation, reason
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking SoD violation: {e}")
            raise
    
    # ========================== CERTIFICATION MANAGEMENT ==========================
    
    def check_user_certification(
        self,
        user_id: int,
        certification_type: str
    ) -> Dict[str, Any]:
        """
        Check if user has valid certification
        
        Args:
            user_id: User ID
            certification_type: Type of certification required
            
        Returns:
            {
                'is_certified': bool,
                'certification_id': int or None,
                'expires_at': timestamp or None,
                'days_until_expiry': int or None,
                'is_expiring_soon': bool or None
            }
        """
        try:
            query = """
                SELECT * FROM historian_meta.check_user_certification(%s, %s)
            """
            result = self.db.execute_query(
                query,
                (user_id, certification_type),
                fetch=True
            )
            
            if result and len(result) > 0:
                row = result[0]
                return {
                    'is_certified': row[0],
                    'certification_id': row[1],
                    'expires_at': row[2],
                    'days_until_expiry': row[3],
                    'is_expiring_soon': row[4]
                }
            
            return {
                'is_certified': False,
                'certification_id': None,
                'expires_at': None,
                'days_until_expiry': None,
                'is_expiring_soon': None
            }
            
        except Exception as e:
            logger.error(f"Error checking user certification: {e}")
            raise
    
    def grant_certification(
        self,
        user_id: int,
        certification_type: str,
        certified_by: int,
        validity_months: int = 12,
        training_record_url: Optional[str] = None,
        test_score: Optional[float] = None,
        notes: Optional[str] = None
    ) -> int:
        """
        Grant certification to user
        
        Args:
            user_id: User to certify
            certification_type: Type of certification
            certified_by: Admin/trainer ID
            validity_months: Months until expiry
            training_record_url: URL to training records
            test_score: Exam score (0-100)
            notes: Additional notes
            
        Returns:
            certification_id
        """
        try:
            expires_at = datetime.now() + timedelta(days=validity_months * 30)
            
            query = """
                INSERT INTO historian_meta.user_certifications (
                    user_id, certification_type, certified_at, expires_at,
                    certified_by, training_record_url, test_score, is_active, notes
                ) VALUES (%s, %s, NOW(), %s, %s, %s, %s, TRUE, %s)
                RETURNING id
            """
            
            result = self.db.execute_query(
                query,
                (user_id, certification_type, expires_at, certified_by,
                 training_record_url, test_score, notes),
                fetch=True
            )
            
            cert_id = result[0][0] if result else None
            logger.info(
                f"✅ Certification granted: user_id={user_id}, "
                f"type={certification_type}, expires={expires_at}"
            )
            return cert_id
            
        except Exception as e:
            logger.error(f"Error granting certification: {e}")
            raise
    
    def revoke_certification(
        self,
        certification_id: int,
        revoked_by: int,
        revoke_reason: str
    ) -> bool:
        """
        Revoke user certification
        
        Args:
            certification_id: Certification to revoke
            revoked_by: Admin ID
            revoke_reason: Reason for revocation
            
        Returns:
            success
        """
        try:
            query = """
                UPDATE historian_meta.user_certifications
                SET is_active = FALSE,
                    revoked_at = NOW(),
                    revoked_by = %s,
                    revocation_reason = %s
                WHERE id = %s
            """
            
            self.db.execute_query(
                query,
                (revoked_by, revoke_reason, certification_id),
                fetch=False
            )
            
            logger.info(
                f"⚠️ Certification revoked: cert_id={certification_id}, "
                f"reason={revoke_reason}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Error revoking certification: {e}")
            raise
    
    # ========================== OPERATION PERMISSION CHECKING ==========================
    
    def check_operation_allowed(
        self,
        user_id: int,
        operation_type: str
    ) -> Dict[str, Any]:
        """
        Check if user is allowed to perform operation
        
        Args:
            user_id: User ID
            operation_type: Operation type
            
        Returns:
            {
                'operation_allowed': bool,
                'reason': str,
                'requires_approval': bool,
                'requires_2fa': bool,
                'required_certification': str or None
            }
        """
        try:
            query = """
                SELECT * FROM historian_meta.check_operation_allowed(%s, %s)
            """
            result = self.db.execute_query(
                query,
                (user_id, operation_type),
                fetch=True
            )
            
            if result and len(result) > 0:
                row = result[0]
                return {
                    'operation_allowed': row[0],
                    'reason': row[1],
                    'requires_approval': row[2],
                    'requires_2fa': row[3],
                    'required_certification': row[4]
                }
            
            return {
                'operation_allowed': False,
                'reason': 'Operation check failed',
                'requires_approval': False,
                'requires_2fa': False,
                'required_certification': None
            }
            
        except Exception as e:
            logger.error(f"Error checking operation allowance: {e}")
            raise
    
    # ========================== APPROVAL WORKFLOW ==========================
    
    def request_operation_approval(
        self,
        request: OperationRequest,
        ip_address: str = '',
        session_id: Optional[str] = None
    ) -> OperationApprovalResult:
        """
        Create operation approval request (Change Control)
        
        Args:
            request: OperationRequest object
            ip_address: Requester IP
            session_id: Session ID
            
        Returns:
            OperationApprovalResult with approval ID and status
        """
        try:
            # Check SoD violation
            sod_violation, sod_reason = self.check_sod_violation(
                request.operation_type,
                request.requested_by
            )
            
            if sod_violation:
                logger.warning(f"SoD violation in approval request: {sod_reason}")
                return OperationApprovalResult(
                    approval_id=0,
                    status='REJECTED',
                    sod_violation=True,
                    sod_violation_reason=sod_reason,
                    message=f"Operation violates SoD rules: {sod_reason}"
                )
            
            # Create approval request
            query = """
                INSERT INTO historian_meta.operation_approvals (
                    operation_type, operation_id, operation_description,
                    requested_by, request_reason, status,
                    priority, execution_deadline, impact_assessment,
                    rollback_procedure, session_id, ip_address,
                    additional_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING id
            """
            
            result = self.db.execute_query(
                query,
                (
                    request.operation_type,
                    request.operation_id,
                    request.operation_description,
                    request.requested_by,
                    request.request_reason,
                    'REQUESTED',
                    request.priority,
                    request.execution_deadline,
                    request.impact_assessment,
                    request.rollback_procedure,
                    session_id,
                    ip_address,
                    json.dumps(request.additional_data) if request.additional_data else None
                ),
                fetch=True
            )
            
            approval_id = result[0][0] if result else None
            
            logger.info(
                f"✅ Approval request created: id={approval_id}, "
                f"operation={request.operation_type}, requested={request.requested_by}"
            )
            
            return OperationApprovalResult(
                approval_id=approval_id,
                status='REQUESTED',
                message='Approval request created successfully'
            )
            
        except Exception as e:
            logger.error(f"Error creating approval request: {e}")
            raise
    
    def approve_operation(
        self,
        approval_id: int,
        approved_by: int,
        approval_reason: str = '',
        requires_2fa: bool = False,
        ip_address: str = '',
        session_id: Optional[str] = None
    ) -> OperationApprovalResult:
        """
        Approve pending operation request
        
        Args:
            approval_id: Approval request ID
            approved_by: Approver user ID
            approval_reason: Reason for approval
            requires_2fa: Whether 2FA code needs to be verified
            ip_address: Approver IP
            session_id: Session ID
            
        Returns:
            OperationApprovalResult with approval code (if 2FA required)
        """
        try:
            # Get approval request
            query = """
                SELECT operation_type, requested_by, status
                FROM historian_meta.operation_approvals
                WHERE id = %s
            """
            result = self.db.execute_query(query, (approval_id,), fetch=True)
            
            if not result:
                return OperationApprovalResult(
                    approval_id=approval_id,
                    status='REJECTED',
                    message='Approval request not found'
                )
            
            operation_type = result[0][0]
            requested_by = result[0][1]
            
            # Check SoD: approver != requester
            if approved_by == requested_by:
                logger.warning(
                    f"SoD violation: Requester cannot approve own request "
                    f"(approval_id={approval_id})"
                )
                return OperationApprovalResult(
                    approval_id=approval_id,
                    status='REJECTED',
                    sod_violation=True,
                    sod_violation_reason='Requester cannot approve own request',
                    message='SoD violation: Requester cannot approve own request'
                )
            
            # Generate approval code if 2FA required
            approval_code = None
            approval_expires = None
            if requires_2fa:
                import secrets
                approval_code = secrets.token_urlsafe(16)
                approval_expires = datetime.now() + timedelta(minutes=10)
            
            # Update approval
            update_query = """
                UPDATE historian_meta.operation_approvals
                SET approved_by = %s,
                    approved_at = NOW(),
                    approval_reason = %s,
                    approval_code = %s,
                    approval_code_expires_at = %s,
                    status = %s
                WHERE id = %s
            """
            
            status = 'APPROVED' if not requires_2fa else 'APPROVED'
            
            self.db.execute_query(
                update_query,
                (approved_by, approval_reason, approval_code, 
                 approval_expires, status, approval_id),
                fetch=False
            )
            
            # Log approval action
            self._log_operation_audit(
                approval_id=approval_id,
                operation_type=operation_type,
                action='APPROVE',
                performed_by=approved_by,
                result='SUCCEEDED'
            )
            
            logger.info(
                f"✅ Operation approved: approval_id={approval_id}, "
                f"approved_by={approved_by}, requires_2fa={requires_2fa}"
            )
            
            return OperationApprovalResult(
                approval_id=approval_id,
                status='APPROVED',
                approval_code=approval_code,
                approval_expires_at=approval_expires,
                message='Operation approved successfully'
            )
            
        except Exception as e:
            logger.error(f"Error approving operation: {e}")
            raise
    
    def execute_approved_operation(
        self,
        approval_id: int,
        executed_by: int,
        approval_code: Optional[str] = None,
        ip_address: str = '',
        session_id: Optional[str] = None
    ) -> bool:
        """
        Execute an approved operation
        
        Args:
            approval_id: Approval request ID
            executed_by: Executor user ID
            approval_code: 2FA code if required
            ip_address: Executor IP
            session_id: Session ID
            
        Returns:
            success
        """
        try:
            # Get approval details
            query = """
                SELECT operation_type, operation_id, status, 
                       approval_code, approval_code_expires_at,
                       requested_by, approved_by
                FROM historian_meta.operation_approvals
                WHERE id = %s
            """
            result = self.db.execute_query(query, (approval_id,), fetch=True)
            
            if not result:
                logger.error(f"Approval request not found: {approval_id}")
                return False
            
            row = result[0]
            operation_type = row[0]
            operation_id = row[1]
            status = row[2]
            approval_code_stored = row[3]
            approval_expires = row[4]
            requested_by = row[5]
            approved_by = row[6]
            
            # Verify approval status
            if status != 'APPROVED':
                logger.warning(f"Approval not in approved status: {status}")
                return False
            
            # Verify 2FA code if required
            if approval_code_stored:
                if not approval_code or approval_code != approval_code_stored:
                    logger.warning(f"Invalid or missing 2FA code: approval_id={approval_id}")
                    return False
                
                if datetime.now() > approval_expires:
                    logger.warning(f"2FA code expired: approval_id={approval_id}")
                    return False
            
            # Execute operation
            update_query = """
                UPDATE historian_meta.operation_approvals
                SET executed_by = %s,
                    executed_at = NOW(),
                    status = %s
                WHERE id = %s
            """
            
            self.db.execute_query(
                update_query,
                (executed_by, 'EXECUTED', approval_id),
                fetch=False
            )
            
            # Log execution
            self._log_operation_audit(
                approval_id=approval_id,
                operation_type=operation_type,
                operation_id=operation_id,
                action='EXECUTE',
                performed_by=executed_by,
                approved_by=approved_by,
                result='SUCCEEDED'
            )
            
            logger.info(
                f"✅ Operation executed: approval_id={approval_id}, "
                f"operation={operation_type}, executed_by={executed_by}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error executing operation: {e}")
            self._log_operation_audit(
                approval_id=approval_id,
                operation_type=operation_type,
                action='EXECUTE',
                performed_by=executed_by,
                result='FAILED',
                reason_code='EXECUTION_ERROR'
            )
            raise
    
    # ========================== AUDIT LOGGING ==========================
    
    def _log_operation_audit(
        self,
        operation_type: str,
        action: str,
        performed_by: int,
        result: str = 'SUCCEEDED',
        approval_id: Optional[int] = None,
        operation_id: Optional[str] = None,
        approved_by: Optional[int] = None,
        reason_code: str = '',
        detailed_reason: str = '',
        metadata: Optional[Dict] = None,
        ip_address: str = '',
        session_id: Optional[str] = None
    ) -> bool:
        """
        Log operation to audit trail
        
        Args:
            operation_type: Type of operation
            action: ACTION type (REQUEST, APPROVE, EXECUTE, VERIFY)
            performed_by: User ID
            result: Result status
            approval_id: Approval request ID
            operation_id: Operation ID
            approved_by: Approver ID (if applicable)
            reason_code: Machine-readable reason
            detailed_reason: Human-readable reason
            metadata: Additional metadata
            ip_address: IP address
            session_id: Session ID
            
        Returns:
            success
        """
        try:
            query = """
                INSERT INTO historian_meta.operation_audit_trail (
                    operation_approval_id, operation_type, operation_id,
                    action, performed_by, approved_by, result,
                    reason_code, detailed_reason, ip_address, session_id,
                    metadata, timestamp
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
            """
            
            self.db.execute_query(
                query,
                (
                    approval_id,
                    operation_type,
                    operation_id,
                    action,
                    performed_by,
                    approved_by,
                    result,
                    reason_code,
                    detailed_reason,
                    ip_address,
                    session_id,
                    json.dumps(metadata) if metadata else None
                ),
                fetch=False
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error logging operation audit: {e}")
            return False
    
    def get_operation_audit_trail(
        self,
        operation_type: Optional[str] = None,
        operation_id: Optional[str] = None,
        user_id: Optional[int] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get operation audit trail records
        
        Args:
            operation_type: Filter by operation type
            operation_id: Filter by operation ID
            user_id: Filter by user ID
            days: Last N days
            limit: Max records
            
        Returns:
            List of audit trail records
        """
        try:
            query = """
                SELECT 
                    id, operation_type, operation_id, action,
                    performed_by, approved_by, timestamp, result,
                    reason_code, detailed_reason, ip_address, session_id
                FROM historian_meta.operation_audit_trail
                WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '%s days'
            """
            params = [days]
            
            if operation_type:
                query += " AND operation_type = %s"
                params.append(operation_type)
            
            if operation_id:
                query += " AND operation_id = %s"
                params.append(operation_id)
            
            if user_id:
                query += " AND (performed_by = %s OR approved_by = %s)"
                params.extend([user_id, user_id])
            
            query += f" ORDER BY timestamp DESC LIMIT {limit}"
            
            results = self.db.execute_query(query, tuple(params), fetch=True)
            
            records = []
            if results:
                for row in results:
                    records.append({
                        'id': row[0],
                        'operation_type': row[1],
                        'operation_id': row[2],
                        'action': row[3],
                        'performed_by': row[4],
                        'approved_by': row[5],
                        'timestamp': row[6],
                        'result': row[7],
                        'reason_code': row[8],
                        'detailed_reason': row[9],
                        'ip_address': row[10],
                        'session_id': row[11]
                    })
            
            return records
            
        except Exception as e:
            logger.error(f"Error retrieving audit trail: {e}")
            return []

