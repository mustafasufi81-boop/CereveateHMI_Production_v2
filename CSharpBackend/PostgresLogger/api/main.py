"""
FastAPI Backend for PostgreSQL Logger
Provides REST APIs for tag mapping, trends, and configuration
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import asyncio
import os
import sys
import subprocess
import threading

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_manager import get_config_manager
from services.parquet_reader import SafeParquetReader

# Initialize app
app = FastAPI(title="Cereveate Database Trends API")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory="templates")

# Config manager
config_manager = get_config_manager()

# Background importer process
importer_process = None

def start_importer():
    """Start background importer service"""
    global importer_process
    try:
        python_exe = sys.executable
        # Use V2 importer (with all fixes applied)
        importer_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'services', 'background_importer_v2.py')
        
        if os.path.exists(importer_script):
            print(f"Starting background importer V2 (fixed): {importer_script}")
            importer_process = subprocess.Popen(
                [python_exe, importer_script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
            )
            print(f"Background importer V2 started with PID: {importer_process.pid}")
        else:
            print(f"Warning: Importer script not found at {importer_script}")
    except Exception as e:
        print(f"Failed to start background importer: {e}")

def stop_importer():
    """Stop background importer service"""
    global importer_process
    if importer_process:
        try:
            importer_process.terminate()
            importer_process.wait(timeout=5)
            print("Background importer stopped")
        except Exception as e:
            print(f"Error stopping importer: {e}")
            try:
                importer_process.kill()
            except:
                pass

@app.on_event("startup")
async def startup_event():
    """Start background services when API starts"""
    print("Starting Cereveate Database Trends API...")
    # Start importer in background thread to not block API startup
    threading.Thread(target=start_importer, daemon=True).start()

@app.on_event("shutdown")
async def shutdown_event():
    """Stop background services when API stops"""
    print("Shutting down...")
    stop_importer()

# Database connection pool
def get_db_connection():
    """Get database connection from config"""
    db_config = config_manager.get_db_config()
    return psycopg2.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 5432),
        database=db_config.get('database', 'Cereveate'),
        user=db_config.get('user', 'cereveate'),
        password=db_config.get('password', 'cereveate@222')
    )

# Pydantic models
class TagMapping(BaseModel):
    parquet_column: str
    tag_name: str
    plant: str
    asset: str
    subsystem: str = 'General'
    unit: str = ''
    sampling_frequency_seconds: int = 0
    enabled: bool = True

class TrendQuery(BaseModel):
    tag_names: List[str]
    start_time: str  # Accept as string, will parse in endpoint
    end_time: str    # Accept as string, will parse in endpoint
    max_points: Optional[int] = None

class RefreshConfig(BaseModel):
    interval_seconds: int

# ============================================================================
# CONFIGURATION ENDPOINTS
# ============================================================================

@app.get("/api/config/all")
async def get_all_config():
    """Get complete configuration"""
    return config_manager.config

@app.put("/api/config/all")
async def update_all_config(config: Dict):
    """Update complete configuration"""
    config_manager.config = config
    if config_manager.save_config():
        return {"status": "success", "message": "Configuration updated"}
    raise HTTPException(status_code=500, detail="Failed to save configuration")

@app.get("/api/config/database")
async def get_database_config():
    """Get database configuration (password masked)"""
    db_config = config_manager.get_db_config()
    # Mask password
    masked = db_config.copy()
    if 'password' in masked:
        masked['password'] = '***'
    return masked

@app.put("/api/config/database")
async def update_database_config(config: Dict):
    """Update database configuration"""
    config_manager.config['database'] = config
    if config_manager.save_config():
        return {"status": "success", "message": "Database configuration updated"}
    raise HTTPException(status_code=500, detail="Failed to save configuration")

@app.get("/api/config/parquet-source")
async def get_parquet_source_config():
    """Get parquet source configuration"""
    return config_manager.get_parquet_source_config()

@app.put("/api/config/parquet-source")
async def update_parquet_source_config(config: Dict):
    """Update parquet source configuration"""
    config_manager.config['parquet_source'] = config
    if config_manager.save_config():
        return {"status": "success", "message": "Parquet source configuration updated"}
    raise HTTPException(status_code=500, detail="Failed to save configuration")

@app.get("/api/config/web-ui")
async def get_web_ui_config():
    """Get web UI configuration"""
    return config_manager.get_web_ui_config()

@app.put("/api/config/web-ui")
async def update_web_ui_config(config: Dict):
    """Update web UI configuration"""
    config_manager.config['web_ui'] = config
    if config_manager.save_config():
        return {"status": "success", "message": "Web UI configuration updated"}
    raise HTTPException(status_code=500, detail="Failed to save configuration")

@app.get("/api/config/sampling-frequencies")
async def get_sampling_frequencies():
    """Get available sampling frequency options"""
    return config_manager.config.get('sampling_frequencies', {
        "available_options": [
            {"value": 1, "label": "1 second"},
            {"value": 5, "label": "5 seconds"},
            {"value": 60, "label": "1 minute"}
        ]
    })

@app.get("/api/config/refresh-intervals")
async def get_refresh_intervals():
    """Get available refresh intervals"""
    return {
        "intervals": [
            {"value": 1, "label": "1 second", "seconds": 1},
            {"value": 2, "label": "2 seconds", "seconds": 2},
            {"value": 3, "label": "3 seconds", "seconds": 3},
            {"value": 5, "label": "5 seconds", "seconds": 5},
            {"value": 10, "label": "10 seconds", "seconds": 10},
            {"value": 30, "label": "30 seconds", "seconds": 30},
            {"value": 60, "label": "1 minute", "seconds": 60}
        ],
        "default": config_manager.get_web_ui_config().get('refresh_interval_seconds', 5)
    }

# ============================================================================
# TAG MAPPING ENDPOINTS
# ============================================================================

@app.get("/api/tags/mappings")
async def get_tag_mappings():
    """Get all tag mappings"""
    return config_manager.get_tag_mappings()

@app.get("/api/tags/mappings/enabled")
async def get_enabled_tag_mappings():
    """Get only enabled tag mappings"""
    return config_manager.get_enabled_tag_mappings()

@app.get("/api/tags/mapping/{parquet_column}")
async def get_tag_mapping(parquet_column: str):
    """Get specific tag mapping"""
    mapping = config_manager.get_tag_mapping(parquet_column)
    if mapping:
        return mapping
    raise HTTPException(status_code=404, detail="Tag mapping not found")

@app.post("/api/tags/mapping")
async def create_tag_mapping(mapping: TagMapping):
    """Create new tag mapping"""
    print(f"[DEBUG] Received POST /api/tags/mapping")
    print(f"[DEBUG] Mapping data: {mapping.model_dump()}")
    result = config_manager.add_tag_mapping(mapping.model_dump())
    print(f"[DEBUG] add_tag_mapping result: {result}")
    if result:
        print(f"[OK] Tag mapping created successfully for {mapping.parquet_column}")
        return {"status": "success", "message": "Tag mapping created"}
    print(f"[WARN] Tag mapping already exists for {mapping.parquet_column}")
    raise HTTPException(status_code=400, detail="Tag mapping already exists")

@app.put("/api/tags/mapping/{parquet_column}")
async def update_tag_mapping(parquet_column: str, mapping: TagMapping):
    """Update existing tag mapping"""
    if config_manager.update_tag_mapping(parquet_column, mapping.model_dump()):
        return {"status": "success", "message": "Tag mapping updated"}
    raise HTTPException(status_code=404, detail="Tag mapping not found")

@app.delete("/api/tags/mapping/{parquet_column}")
async def delete_tag_mapping(parquet_column: str):
    """Delete tag mapping"""
    if config_manager.delete_tag_mapping(parquet_column):
        return {"status": "success", "message": "Tag mapping deleted"}
    raise HTTPException(status_code=404, detail="Tag mapping not found")

@app.get("/api/tags/discover")
async def discover_tags_from_parquet():
    """Discover TAG IDs from tag_catalog table (populated by importer).
    Returns mapping status per distinct TagId."""
    try:
        # Read from tag_catalog table instead of scanning parquet files
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT tag_id, first_seen, last_seen, last_file 
            FROM tag_catalog 
            ORDER BY last_seen DESC
        """)
        
        catalog_tags = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not catalog_tags:
            return {
                "format": "long",
                "source": "tag_catalog",
                "total_tags": 0,
                "mapped_count": 0,
                "unmapped_count": 0,
                "tags": []
            }
        
        # Get existing mappings
        existing_mappings = config_manager.get_tag_mappings()
        mapped_dict = {m['parquet_column']: m for m in existing_mappings}
        
        tags_info = []
        for row in catalog_tags:
            tag = row['tag_id']
            if tag in mapped_dict:
                tags_info.append({"tag_id": tag, "mapped": True, "mapping": mapped_dict[tag]})
            else:
                tags_info.append({"tag_id": tag, "mapped": False, "mapping": None})
        
        return {
            "format": "long",
            "source": "tag_catalog",
            "total_tags": len(tags_info),
            "mapped_count": sum(1 for t in tags_info if t['mapped']),
            "unmapped_count": sum(1 for t in tags_info if not t['mapped']),
            "tags": tags_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tags/discover/apply")
async def apply_discovered_tags():
    """This endpoint is deprecated - users must manually map tags via UI"""
    raise HTTPException(status_code=400, detail="Auto-apply disabled. Please map tags manually using 'Add New Tag' button.")

# ============================================================================
# DATA QUERY ENDPOINTS
# ============================================================================

@app.get("/api/data/tags/list")
async def get_available_tags():
    """Get list of tags available in database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT DISTINCT 
                tag_name, 
                MAX(plant) as plant,
                MAX(asset) as asset,
                MAX(subsystem) as subsystem,
                MAX(unit) as unit,
                COUNT(*) as record_count,
                MIN(timestamp) as first_timestamp,
                MAX(timestamp) as last_timestamp
            FROM sensor_data
            GROUP BY tag_name
            ORDER BY tag_name
        """)
        
        tags = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return list(tags)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data/tags/latest")
async def get_latest_tag_values():
    """Get latest values for all tags"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT DISTINCT ON (tag_name)
                tag_name,
                timestamp,
                value,
                unit,
                quality_code,
                status_flag,
                plant,
                asset,
                subsystem
            FROM sensor_data
            ORDER BY tag_name, timestamp DESC
        """)
        
        latest_values = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert datetime to ISO format
        for row in latest_values:
            row['timestamp'] = row['timestamp'].isoformat()
        
        return list(latest_values)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/data/trends")
async def get_trend_data(query: TrendQuery):
    """Get trend data for specified tags and time range"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        max_points = query.max_points or config_manager.get_web_ui_config().get('default_chart_points', 1000)
        
        # Parse datetime strings (handle both ISO format and HTML datetime-local format)
        try:
            start_dt = datetime.fromisoformat(query.start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(query.end_time.replace('Z', '+00:00'))
        except ValueError:
            # Fallback: try parsing without timezone
            start_dt = datetime.strptime(query.start_time[:19], '%Y-%m-%dT%H:%M:%S')
            end_dt = datetime.strptime(query.end_time[:19], '%Y-%m-%dT%H:%M:%S')
        
        cursor.execute("""
            SELECT 
                timestamp,
                tag_name,
                value,
                unit,
                quality_code,
                status_flag
            FROM sensor_data
            WHERE tag_name = ANY(%s)
              AND timestamp BETWEEN %s AND %s
            ORDER BY timestamp ASC
            LIMIT %s
        """, (query.tag_names, start_dt, end_dt, max_points))
        
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert datetime to ISO format
        for row in data:
            row['timestamp'] = row['timestamp'].isoformat()
        
        return list(data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data/tag/{tag_name}/latest/{count}")
async def get_tag_latest_values(tag_name: str, count: int = 100):
    """Get latest N values for specific tag"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        max_points = config_manager.get_web_ui_config().get('max_chart_points', 50000)
        count = min(count, max_points)
        
        cursor.execute("""
            SELECT 
                timestamp,
                value,
                unit,
                quality_code,
                status_flag
            FROM sensor_data
            WHERE tag_name = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (tag_name, count))
        
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert datetime to ISO format and reverse (oldest first)
        result = []
        for row in reversed(data):
            row['timestamp'] = row['timestamp'].isoformat()
            result.append(row)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# STATISTICS ENDPOINTS
# ============================================================================

@app.get("/api/stats/database")
async def get_database_stats():
    """Get database statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total records
        cursor.execute("SELECT COUNT(*) as total_records FROM sensor_data")
        total_records = cursor.fetchone()['total_records']
        
        # Total tags
        cursor.execute("SELECT COUNT(DISTINCT tag_name) as total_tags FROM sensor_data")
        total_tags = cursor.fetchone()['total_tags']
        
        # Time range
        cursor.execute("SELECT MIN(timestamp) as first_record, MAX(timestamp) as last_record FROM sensor_data")
        time_range = cursor.fetchone()
        
        # Records by plant
        cursor.execute("""
            SELECT plant, COUNT(*) as count 
            FROM sensor_data 
            GROUP BY plant 
            ORDER BY count DESC
        """)
        by_plant = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "total_records": total_records,
            "total_tags": total_tags,
            "first_record": time_range['first_record'].isoformat() if time_range['first_record'] else None,
            "last_record": time_range['last_record'].isoformat() if time_range['last_record'] else None,
            "by_plant": list(by_plant)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# WEBSOCKET FOR REAL-TIME DATA
# ============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/live-data")
async def websocket_live_data(websocket: WebSocket):
    """WebSocket endpoint for live data streaming"""
    await manager.connect(websocket)
    try:
        while True:
            # Get latest values
            latest_values = await get_latest_tag_values()
            await websocket.send_json({
                "type": "live_data",
                "timestamp": datetime.now().isoformat(),
                "data": latest_values
            })
            
            # Wait before next update (configurable)
            refresh_interval = config_manager.get_web_ui_config().get('refresh_interval_seconds', 5)
            await asyncio.sleep(refresh_interval)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/imports/status")
async def get_import_status():
    """Get import status - which files processed, records imported"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all imports
        cursor.execute("""
            SELECT 
                file_path,
                file_hash,
                file_size,
                import_timestamp,
                records_imported,
                status,
                error_message
            FROM file_imports
            ORDER BY import_timestamp DESC
            LIMIT 100
        """)
        
        imports = cursor.fetchall()
        
        # Get summary stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_files,
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                SUM(records_imported) as total_records
            FROM file_imports
        """)
        
        summary = cursor.fetchone()
        cursor.close()
        conn.close()
        
        # Convert timestamps
        for imp in imports:
            imp['import_timestamp'] = imp['import_timestamp'].isoformat()
        
        return {
            "summary": summary,
            "imports": list(imports)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

@app.get("/")
async def root(request: Request):
    """Serve main UI"""
    ui_config = config_manager.get_web_ui_config()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": ui_config.get('title', 'Cereveate Database Trends')
    })

if __name__ == "__main__":
    import uvicorn
    ui_config = config_manager.get_web_ui_config()
    port = ui_config.get('port', 8001)
    host = ui_config.get('host', '0.0.0.0')
    
    print(f"Starting Cereveate Database Trends API on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
