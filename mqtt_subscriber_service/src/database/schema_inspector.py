"""
Schema Inspector Module
Auto-detects database table structures and builds column mappings
"""

import psycopg2.extras
from typing import Dict, List, Optional, Any
from src.monitoring.logger import get_logger

logger = get_logger(__name__)


class SchemaInspector:
    """Inspects and caches database schema information"""
    
    def __init__(self, db_connection):
        """
        Initialize schema inspector
        
        Args:
            db_connection: DatabaseConnection instance
        """
        self.db = db_connection
        self._schemas: Dict[str, Dict[str, Any]] = {}
        
    def inspect_table(self, schema: str, table_name: str) -> Dict[str, Any]:
        """
        Inspect table structure
        
        Args:
            schema: Schema name
            table_name: Table name
            
        Returns:
            Dictionary with table metadata
        """
        cache_key = f"{schema}.{table_name}"
        
        if cache_key in self._schemas:
            return self._schemas[cache_key]
        
        query = """
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = %s 
            AND table_name = %s
            ORDER BY ordinal_position
        """
        
        with self.db.get_cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (schema, table_name))
            columns = cur.fetchall()
        
        table_info = {
            'schema': schema,
            'table': table_name,
            'full_name': f"{schema}.{table_name}",
            'columns': {},
            'column_names': []
        }
        
        for col in columns:
            col_name = col['column_name']
            table_info['columns'][col_name] = {
                'data_type': col['data_type'],
                'nullable': col['is_nullable'] == 'YES',
                'default': col['column_default'],
                'max_length': col['character_maximum_length']
            }
            table_info['column_names'].append(col_name)
        
        self._schemas[cache_key] = table_info
        logger.info(f"Inspected table {cache_key}: {len(table_info['columns'])} columns")
        
        return table_info
    
    def get_historian_timeseries_schema(self) -> Dict[str, Any]:
        """Get historian_timeseries table schema"""
        return self.inspect_table('historian_raw', 'historian_timeseries')
    
    def get_historian_events_schema(self) -> Dict[str, Any]:
        """Get historian_events table schema"""
        return self.inspect_table('historian_raw', 'historian_events')
    
    def get_tag_master_schema(self) -> Dict[str, Any]:
        """Get tag_master table schema"""
        return self.inspect_table('historian_meta', 'tag_master')
    
    def build_insert_query(self, schema: str, table_name: str, columns: List[str]) -> str:
        """
        Build parameterized INSERT query
        
        Args:
            schema: Schema name
            table_name: Table name
            columns: List of column names
            
        Returns:
            Parameterized INSERT query string
        """
        placeholders = ', '.join(['%s'] * len(columns))
        cols = ', '.join(columns)
        
        query = f"""
            INSERT INTO {schema}.{table_name} ({cols})
            VALUES ({placeholders})
        """
        
        return query
    
    def validate_columns(self, schema: str, table_name: str, columns: List[str]) -> bool:
        """
        Validate that columns exist in table
        
        Args:
            schema: Schema name
            table_name: Table name
            columns: List of column names to validate
            
        Returns:
            True if all columns exist, False otherwise
        """
        table_info = self.inspect_table(schema, table_name)
        
        for col in columns:
            if col not in table_info['columns']:
                logger.error(f"Column '{col}' not found in {schema}.{table_name}")
                return False
        
        return True
    
    def clear_cache(self):
        """Clear schema cache"""
        self._schemas.clear()
        logger.info("Schema cache cleared")
