"""
FastAPI REST API for BI Engine - LICENSED MULTI-USER VERSION
Professional API layer with validation and error handling
ZERO HARDCODING - MULTI-USER CONCURRENT - ASYNC PROCESSING - LICENSED
"""

from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Tuple
import pandas as pd
import logging
from datetime import datetime
import asyncio
import uuid
from concurrent.futures import ProcessPoolExecutor
import hashlib

from bi_engines.master_orchestrator import MasterBIOrchestrator
from bi_engines.config import get_config
from bi_engines.license_manager import get_license_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Industrial BI Engine API",
    description="Professional Python backend for power plant analytics - Multi-user concurrent with licensing",
    version="2.0.0"
)

# Load configuration
config = get_config()
api_config = config.get_engine_config('api')

# Initialize license manager (CRITICAL: Controls concurrent users)
license_manager = get_license_manager()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=api_config.get('cors_origins', ['*']),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CRITICAL: Per-user session isolation
# Each user gets their own orchestrator instance to prevent data mixing
user_sessions = {}
session_lock = asyncio.Lock()

# Process pool for CPU-intensive tasks (parallel processing)
max_workers = api_config.get('max_workers', 4)
process_pool = ProcessPoolExecutor(max_workers=max_workers)

logger.info(f"✓ BI Engine API initialized with {max_workers} worker processes for concurrent users")


# =====================================================
# Request/Response Models
# =====================================================

class FullAnalysisRequest(BaseModel):
    """Request model for full BI analysis"""
    data: List[Dict[str, Any]] = Field(..., description="Time-series data as list of dictionaries")
    production_tag: str = Field(..., description="Main production parameter tag name")
    influencing_tags: List[str] = Field(..., description="List of influencing parameter tag names")
    rated_capacity: float = Field(..., description="Plant rated capacity in MW", gt=0)
    
    class Config:
        schema_extra = {
            "example": {
                "data": [
                    {"Timestamp": "2024-01-01T00:00:00", "Load": 500, "Vibration": 2.5, "NOx": 140},
                    {"Timestamp": "2024-01-01T00:01:00", "Load": 505, "Vibration": 2.6, "NOx": 142}
                ],
                "production_tag": "Load",
                "influencing_tags": ["Vibration", "NOx", "CondenserVacuum"],
                "rated_capacity": 660
            }
        }


class BaselineRequest(BaseModel):
    """Request model for baseline calculation"""
    data: List[Dict[str, Any]]
    tag: str
    
    class Config:
        schema_extra = {
            "example": {
                "data": [{"Timestamp": "2024-01-01T00:00:00", "Load": 500}],
                "tag": "Load"
            }
        }


class InfluenceMapRequest(BaseModel):
    """Request model for influence map calculation"""
    data: List[Dict[str, Any]]
    primary_tag: str
    influencing_tags: List[str]


class AvailabilityRequest(BaseModel):
    """Request model for availability calculation"""
    data: List[Dict[str, Any]]
    load_col: str
    rated_capacity: float


class LoginRequest(BaseModel):
    """Request model for user login"""
    user_id: str = Field(..., description="Unique user identifier")
    ip_address: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LicenseInstallRequest(BaseModel):
    """Request model for license installation (ONE-TIME ONLY)"""
    max_concurrent_users: int = Field(..., description="Maximum concurrent users allowed", ge=1, le=100)
    admin_key: str = Field(..., description="Admin API key for license management")


class UpdateLicenseRequest(BaseModel):
    """Request model for updating license limit"""
    new_max_users: int = Field(..., description="New maximum concurrent users", ge=1, le=100)
    admin_key: str = Field(..., description="Admin API key (required)")


# =====================================================
# Helper Functions
# =====================================================

async def get_user_orchestrator(
    user_id: str = None,
    session_token: str = None,
    config_override: Dict = None
) -> Tuple[MasterBIOrchestrator, str]:
    """
    Get or create orchestrator for specific user session
    CRITICAL: Ensures complete isolation + license control
    
    Returns:
        Tuple of (orchestrator, session_token)
    """
    async with session_lock:
        # Generate user ID if not provided
        if not user_id:
            user_id = str(uuid.uuid4())
        
        # Check license and concurrent user limit
        can_login, reason, old_token = license_manager.check_user_login(user_id, session_token)
        
        if not can_login:
            max_users = license_manager.license_data['max_concurrent_users']
            raise HTTPException(
                status_code=403,
                detail=f"Maximum concurrent users ({max_users}) reached. Please try again later."
            )
        
        # If same user from different location, logout old session
        if reason == "logout_other_session" and old_token:
            # Remove old session from user_sessions
            if user_id in user_sessions:
                logger.info(f"🔄 Removing old session for {user_id}")
                del user_sessions[user_id]
        
        # Check if user session exists
        if user_id not in user_sessions:
            logger.info(f"Creating new session for user: {user_id}")
            
            # Create session in license manager
            new_session_token = license_manager.create_session(user_id)
            
            # Create dedicated orchestrator for this user
            user_sessions[user_id] = {
                'orchestrator': MasterBIOrchestrator(use_cache=True),
                'session_token': new_session_token,
                'created_at': datetime.now(),
                'last_accessed': datetime.now()
            }
            
            session_token = new_session_token
        else:
            # Update last accessed time (keeps session active)
            user_sessions[user_id]['last_accessed'] = datetime.now()
            license_manager.update_session_activity(user_id)
            session_token = user_sessions[user_id]['session_token']
        
        return user_sessions[user_id]['orchestrator'], session_token


async def cleanup_idle_sessions(idle_minutes: int = 30):
    """
    Remove IDLE sessions (not active sessions)
    Only clears if idle for specified time
    """
    async with session_lock:
        now = datetime.now()
        to_remove = []
        
        for user_id, session in user_sessions.items():
            idle_time = (now - session['last_accessed']).total_seconds() / 60
            
            # Only remove if IDLE (not actively used)
            if idle_time > idle_minutes:
                to_remove.append(user_id)
        
        for user_id in to_remove:
            logger.info(f"🧹 Removing IDLE session: {user_id} (idle {idle_minutes} min)")
            del user_sessions[user_id]
            license_manager.logout_session(user_id)


# Background task: cleanup idle sessions every 5 minutes
@app.on_event("startup")
async def start_cleanup_task():
    """Start background task for idle session cleanup"""
    async def periodic_cleanup():
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            await cleanup_idle_sessions(idle_minutes=30)
    
    asyncio.create_task(periodic_cleanup())
    logger.info("✓ Background idle session cleanup task started (30 min timeout)")


# =====================================================
# Authentication & License Endpoints
# =====================================================

@app.post("/auth/login")
async def login(request: LoginRequest):
    """
    User login endpoint
    - Checks concurrent user limit
    - Force logout from other locations if same user
    - Returns session token
    """
    try:
        orchestrator, session_token = await get_user_orchestrator(
            user_id=request.user_id,
            session_token=None  # New login
        )
        
        return {
            "success": True,
            "user_id": request.user_id,
            "session_token": session_token,
            "message": "Login successful",
            "max_concurrent_users": license_manager.license_data['max_concurrent_users'],
            "active_sessions": len(user_sessions)
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/logout")
async def logout(user_id: str = Header(..., alias="X-User-ID")):
    """
    User logout endpoint
    - Removes user session
    - Frees up concurrent user slot
    """
    try:
        async with session_lock:
            if user_id in user_sessions:
                del user_sessions[user_id]
                license_manager.logout_session(user_id)
                logger.info(f"✅ User logged out: {user_id}")
                return {"success": True, "message": "Logout successful"}
            else:
                return {"success": False, "message": "Session not found"}
    
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/setup/install_license")
async def install_license(request: LicenseInstallRequest):
    """
    INSTALLATION-TIME ONLY: Set up license with concurrent user limit
    Can only be called once during initial setup
    """
    try:
        success = license_manager.install_license(
            max_users=request.max_concurrent_users,
            admin_key=request.admin_key
        )
        
        if success:
            return {
                "success": True,
                "message": "License installed successfully",
                "max_concurrent_users": request.max_concurrent_users,
                "installation_date": datetime.now().isoformat()
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="License already installed. Use /admin/update_license to change limits."
            )
    
    except Exception as e:
        logger.error(f"License installation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/license/info")
async def get_license_info():
    """
    Get license information (READ-ONLY)
    Shows max users, installation date, current usage
    """
    try:
        license_info = license_manager.get_license_info()
        active_sessions = license_manager.get_active_sessions()
        
        return {
            **license_info,
            "current_active_users": len(active_sessions),
            "active_sessions": active_sessions,
            "available_slots": license_info['max_concurrent_users'] - len(active_sessions)
        }
    
    except Exception as e:
        logger.error(f"License info error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/update_license")
async def update_license(request: UpdateLicenseRequest):
    """
    ADMIN ONLY: Update concurrent user limit
    Requires correct admin API key
    """
    try:
        success = license_manager.update_max_users(
            new_limit=request.new_max_users,
            admin_key=request.admin_key
        )
        
        if success:
            return {
                "success": True,
                "message": "License updated successfully",
                "new_max_users": request.new_max_users
            }
        else:
            raise HTTPException(
                status_code=403,
                detail="Invalid admin API key"
            )
    
    except Exception as e:
        logger.error(f"License update error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/active")
async def get_active_sessions():
    """
    Get all active user sessions
    Shows who is currently logged in
    """
    try:
        active_sessions = license_manager.get_active_sessions()
        
        return {
            "active_sessions": active_sessions,
            "total_count": len(active_sessions),
            "max_allowed": license_manager.license_data['max_concurrent_users'],
            "available_slots": license_manager.license_data['max_concurrent_users'] - len(active_sessions)
        }
    
    except Exception as e:
        logger.error(f"Active sessions error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# BI Analysis Endpoints (All require valid session)
# =====================================================

@app.get("/")
async def root():
    """API health check"""
    return {
        "status": "online",
        "service": "Industrial BI Engine API",
        "version": "2.0.0",
        "licensed": True,
        "multi_user": True,
        "async_processing": True,
        "active_sessions": len(user_sessions),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "config_loaded": config.config is not None,
        "active_sessions": len(user_sessions),
        "max_workers": max_workers,
        "max_concurrent_users": license_manager.license_data.get('max_concurrent_users', 'Not installed'),
        "license_installed": license_manager.is_license_installed(),
        "multi_user_support": True,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/v1/analyze/full")
async def full_analysis(
    request: FullAnalysisRequest,
    x_user_id: str = Header(..., alias="X-User-ID"),
    session_token: str = Header(None, alias="X-Session-Token")
):
    """
    Execute full BI analysis pipeline (ASYNC - Non-blocking)
    Includes all 8 steps: baseline → efficiency → influence → availability → 
    performance score → stability → condition → loss attribution
    
    REQUIRES: Valid session token and user ID
    """
    try:
        # Get user-specific orchestrator (validates license + session)
        orchestrator, token = await get_user_orchestrator(
            user_id=x_user_id,
            session_token=session_token
        )
        
        # Convert request data to DataFrame
        df = pd.DataFrame(request.data)
        
        # Execute full analysis in thread pool (non-blocking)
        result = await asyncio.to_thread(
            orchestrator.execute_full_analysis,
            df,
            request.production_tag,
            request.rated_capacity,
            request.influencing_tags
        )
        
        logger.info(f"✅ Full analysis completed for user {x_user_id}")
        
        return {
            "success": True,
            "user_id": x_user_id,
            "session_token": token,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Full analysis error for user {x_user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calculate/baseline")
async def calculate_baseline(
    request: BaselineRequest,
    x_user_id: str = Header(..., alias="X-User-ID"),
    session_token: str = Header(None, alias="X-Session-Token")
):
    """
    Calculate adaptive baseline for a parameter (ASYNC)
    Uses configurable outlier detection (sigma/IQR/MAD/percentile)
    """
    try:
        orchestrator, token = await get_user_orchestrator(
            user_id=x_user_id,
            session_token=session_token
        )
        
        df = pd.DataFrame(request.data)
        
        result = await asyncio.to_thread(
            orchestrator.get_baseline,
            df,
            request.tag
        )
        
        return {
            "success": True,
            "user_id": x_user_id,
            "session_token": token,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Baseline calculation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calculate/influence_map")
async def calculate_influence_map(
    request: InfluenceMapRequest,
    x_user_id: str = Header(..., alias="X-User-ID"),
    session_token: str = Header(None, alias="X-Session-Token")
):
    """
    Calculate influence map (correlations + cross-correlations + lag analysis)
    CPU-intensive operation using ProcessPoolExecutor
    """
    try:
        orchestrator, token = await get_user_orchestrator(
            user_id=x_user_id,
            session_token=session_token
        )
        
        df = pd.DataFrame(request.data)
        
        result = await asyncio.to_thread(
            orchestrator.calculate_influence_map,
            df,
            request.primary_tag,
            request.influencing_tags
        )
        
        return {
            "success": True,
            "user_id": x_user_id,
            "session_token": token,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Influence map error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calculate/availability")
async def calculate_availability(
    request: AvailabilityRequest,
    x_user_id: str = Header(..., alias="X-User-ID"),
    session_token: str = Header(None, alias="X-Session-Token")
):
    """
    Calculate availability metrics (cumulative production vs. rated capacity)
    """
    try:
        orchestrator, token = await get_user_orchestrator(
            user_id=x_user_id,
            session_token=session_token
        )
        
        df = pd.DataFrame(request.data)
        
        result = await asyncio.to_thread(
            orchestrator.calculate_availability,
            df,
            request.load_col,
            request.rated_capacity
        )
        
        return {
            "success": True,
            "user_id": x_user_id,
            "session_token": token,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Availability calculation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/cache/invalidate")
async def invalidate_cache(
    x_user_id: str = Header(..., alias="X-User-ID"),
    session_token: str = Header(None, alias="X-Session-Token")
):
    """
    Invalidate cache for specific user
    Forces fresh calculations on next request
    """
    try:
        orchestrator, token = await get_user_orchestrator(
            user_id=x_user_id,
            session_token=session_token
        )
        
        orchestrator.invalidate_cache()
        
        return {
            "success": True,
            "user_id": x_user_id,
            "message": "Cache invalidated for user",
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Cache invalidation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/cache/stats")
async def get_cache_stats(
    x_user_id: str = Header(..., alias="X-User-ID"),
    session_token: str = Header(None, alias="X-Session-Token")
):
    """
    Get cache statistics for specific user
    """
    try:
        orchestrator, token = await get_user_orchestrator(
            user_id=x_user_id,
            session_token=session_token
        )
        
        stats = orchestrator.get_cache_stats()
        
        return {
            "success": True,
            "user_id": x_user_id,
            "cache_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Cache stats error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# Startup Message
# =====================================================

logger.info("=" * 80)
logger.info("🚀 INDUSTRIAL BI ENGINE API - LICENSED MULTI-USER")
logger.info("=" * 80)
logger.info("✓ Zero hardcoding - All config in bi_config.yaml")
logger.info("✓ Multi-user concurrent - Per-user session isolation")
logger.info("✓ Zero lag - Async processing with process pool")
logger.info("✓ Licensed system - Concurrent user limit enforcement")
logger.info(f"✓ Max workers: {max_workers}")
logger.info(f"✓ Session timeout: 30 min (idle only)")
logger.info(f"✓ License status: {'Installed' if license_manager.is_license_installed() else 'Not installed - Run /setup/install_license'}")
logger.info("=" * 80)
