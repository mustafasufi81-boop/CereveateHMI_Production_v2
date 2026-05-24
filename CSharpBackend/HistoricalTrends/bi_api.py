"""
FastAPI REST API for BI Engine
Professional API layer with validation and error handling
ZERO HARDCODING - MULTI-USER CONCURRENT - ASYNC PROCESSING
"""

from fastapi import FastAPI, HTTPException, Body, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
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
    description="Professional Python backend for power plant analytics - Multi-user concurrent",
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


# =====================================================
# API Endpoints
# =====================================================

async def get_user_orchestrator(user_id: str = None, config_override: Dict = None) -> MasterBIOrchestrator:
    """
    Get or create orchestrator for specific user session
    CRITICAL: Ensures complete isolation between concurrent users
    """
    async with session_lock:
        # Generate user ID if not provided
        if not user_id:
            user_id = str(uuid.uuid4())
        
        # Check if user session exists
@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "config_loaded": config.config is not None,
        "active_sessions": len(user_sessions),
        "max_workers": max_workers,
        "multi_user_support": True,
        "timestamp": datetime.now().isoformat()
    }
    
    # Update last accessed time
    user_sessions[user_id]['last_accessed'] = datetime.now()
    
    return user_sessions[user_id]['orchestrator']


async def cleanup_old_sessions(idle_minutes: int = 30):
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


@app.get("/")
async def root():
    """API health check"""
    return {
        "status": "online",
        "service": "Industrial BI Engine API",
        "version": "2.0.0",
        "multi_user": True,
        "async_processing": True,
        "active_sessions": len(user_sessions),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    cache_stats = orchestrator.get_cache_stats()
    
    return {
        "status": "healthy",
        "cache": cache_stats,
        "config_loaded": config.config is not None,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/v1/analyze/full")
async def full_analysis(
    request: FullAnalysisRequest,
    background_tasks: BackgroundTasks,
    user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """
    Execute complete BI analysis with per-user isolation
    
    ZERO HARDCODING - MULTI-USER CONCURRENT - ASYNC PROCESSING
    Each user gets isolated session preventing data mixing
    """
    try:
        # Get or create user-specific orchestrator
        user_orchestrator = await get_user_orchestrator(user_id)
        
        logger.info(f"📊 Full analysis request [User: {user_id or 'anonymous'}]: {len(request.data)} points, tag={request.production_tag}")
        
        # Add cleanup task
        background_tasks.add_task(cleanup_old_sessions)
        
        # Convert data to DataFrame (async to not block)
        df = await asyncio.to_thread(pd.DataFrame, request.data)
        
        # Ensure Timestamp is datetime
        if 'Timestamp' in df.columns:
            df['Timestamp'] = await asyncio.to_thread(pd.to_datetime, df['Timestamp'])
        else:
            raise HTTPException(status_code=400, detail="Data must include 'Timestamp' column")
        
        # Validate columns
        if request.production_tag not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Production tag '{request.production_tag}' not found in data"
            )
        
        missing_tags = [tag for tag in request.influencing_tags if tag not in df.columns]
        if missing_tags:
            logger.warning(f"⚠️ Missing tags: {missing_tags}")
        
        # Execute analysis ASYNCHRONOUSLY (non-blocking)
        results = await asyncio.to_thread(
            user_orchestrator.execute_full_analysis,
            df=df,
            production_tag=request.production_tag,
            influencing_tags=request.influencing_tags,
            rated_capacity=request.rated_capacity
        )
        
        # Remove DataFrame from results (not JSON serializable)
        if 'processed_data' in results:
            del results['processed_data']
        
        logger.info(f"✅ Full analysis complete [User: {user_id or 'anonymous'}]")
        
        return {
            "status": "success",
            "results": results,
            "metadata": {
                "user_id": user_id or "anonymous",
                "data_points": len(request.data),
                "production_tag": request.production_tag
            }
        }
    
    except Exception as e:
        logger.error(f"❌ Full analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calculate/baseline")
async def calculate_baseline(
    request: BaselineRequest,
    user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """Calculate adaptive baseline for a tag (per-user session)"""
    try:
        user_orchestrator = await get_user_orchestrator(user_id)
        
        logger.info(f"📊 Baseline calculation request [User: {user_id or 'anonymous'}]: tag={request.tag}")
        
        # Async data processing
        df = await asyncio.to_thread(pd.DataFrame, request.data)
        df['Timestamp'] = await asyncio.to_thread(pd.to_datetime, df['Timestamp'])
        
        # Async baseline calculation
        baseline = await asyncio.to_thread(
            user_orchestrator.baseline_engine.calculate_adaptive_baseline,
            df,
            request.tag
        )
        
        if baseline is None:
            raise HTTPException(status_code=400, detail="Insufficient data for baseline calculation")
        
        return {
            "status": "success",
            "baseline": baseline,
            "tag": request.tag,
            "user_id": user_id or "anonymous"
        }
    
    except Exception as e:
        logger.error(f"❌ Baseline calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calculate/influence_map")
async def calculate_influence_map(
    request: InfluenceMapRequest,
    user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """Compute influence map showing parameter correlations (per-user session)"""
    try:
        user_orchestrator = await get_user_orchestrator(user_id)
        
        logger.info(f"🔗 Influence map request [User: {user_id or 'anonymous'}]: {request.primary_tag} vs {len(request.influencing_tags)} tags")
        
        # Async data processing
        df = await asyncio.to_thread(pd.DataFrame, request.data)
        df['Timestamp'] = await asyncio.to_thread(pd.to_datetime, df['Timestamp'])
        
        # Async correlation calculation
        influence_map = await asyncio.to_thread(
            user_orchestrator.influence_engine.compute_influence_map,
            df,
            request.primary_tag,
            request.influencing_tags
        )
        
        # Get top influencers
        top_influencers = user_orchestrator.influence_engine.find_top_influencers(
            influence_map,
            top_n=5
        )
        
        return {
            "status": "success",
            "influence_map": influence_map,
            "top_influencers": [
                {"tag": tag, **metrics} for tag, metrics in top_influencers
            ]
        }
    
    except Exception as e:
        logger.error(f"❌ Influence map error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calculate/availability")
async def calculate_availability(
    request: AvailabilityRequest,
    user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """Calculate availability and production metrics (per-user session)"""
    try:
        user_orchestrator = await get_user_orchestrator(user_id)
        
        logger.info(f"📈 Availability calculation request [User: {user_id or 'anonymous'}]")
        
        # Async data processing
        df = await asyncio.to_thread(pd.DataFrame, request.data)
        df['Timestamp'] = await asyncio.to_thread(pd.to_datetime, df['Timestamp'])
        
        # Async availability calculation
        availability = await asyncio.to_thread(
            user_orchestrator.availability_engine.calculate_availability_production,
            df,
            request.load_col,
            request.rated_capacity
        )
        
        return {
            "status": "success",
            "availability": availability,
            "user_id": user_id or "anonymous"
        }
    
    except Exception as e:
        logger.error(f"❌ Availability calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/cache/invalidate")
async def invalidate_cache(
    operation: Optional[str] = None,
    user_id: Optional[str] = Header(None, alias="X-User-ID")
):
    """Invalidate cache entries for specific user"""
    try:
        user_orchestrator = await get_user_orchestrator(user_id)
        user_orchestrator.invalidate_cache(operation)
        
        return {
            "status": "success",
            "message": f"Cache invalidated for {operation or 'all operations'}",
            "user_id": user_id or "anonymous"
        }
    
    except Exception as e:
        logger.error(f"❌ Cache invalidation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/cache/stats")
async def get_cache_stats(user_id: Optional[str] = Header(None, alias="X-User-ID")):
    """Get cache statistics for specific user"""
    try:
        user_orchestrator = await get_user_orchestrator(user_id)
        stats = user_orchestrator.get_cache_stats()
        
        return {
            "status": "success",
            "cache_stats": stats,
            "user_id": user_id or "anonymous"
        }
    
    except Exception as e:
        logger.error(f"❌ Cache stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/sessions/active")
async def get_active_sessions():
    """Get count of active user sessions"""
    return {
        "status": "success",
        "active_sessions": len(user_sessions),
        "sessions": [
            {
                "user_id": user_id,
                "created_at": session['created_at'].isoformat(),
                "last_accessed": session['last_accessed'].isoformat()
            }
            for user_id, session in user_sessions.items()
        ]
    }


@app.post("/api/v1/sessions/cleanup")
async def cleanup_sessions(max_age_minutes: int = 60):
    """Manually trigger session cleanup"""
    await cleanup_old_sessions(max_age_minutes)
    return {
        "status": "success",
        "active_sessions": len(user_sessions),
        "message": f"Cleaned up sessions older than {max_age_minutes} minutes"
    }


@app.get("/api/v1/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    try:
        stats = orchestrator.get_cache_stats()
        
        return {
            "status": "success",
            "cache_stats": stats
        }
    
    except Exception as e:
        logger.error(f"❌ Cache stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/config")
async def get_configuration():
    """Get current configuration"""
    try:
        return {
            "status": "success",
            "config": config.config
        }
    
    except Exception as e:
        logger.error(f"❌ Config retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# Run Server
# =====================================================

if __name__ == "__main__":
    import uvicorn
    
    host = api_config.get('host', '0.0.0.0')
    port = api_config.get('port', 8000)
    debug = api_config.get('debug', False)
    
    logger.info(f"🚀 Starting BI Engine API on {host}:{port}")
    
    uvicorn.run(
        "bi_api:app",
        host=host,
        port=port,
        reload=debug,
        log_level="info"
    )
