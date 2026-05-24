#!/usr/bin/env python3
"""
Simple schema and data check
"""
import psycopg2
import json
from datetime import datetime, timedelta

# Load config  
with open('config.json') as f:
    config = json.load(f)

try:
    conn = psycopg2.connect(**config['database'])
    
    with conn.cursor() as cursor:
        # Get table structure
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'historian_raw' 
            AND table_name = 'historian_timeseries'
            ORDER BY ordinal_position
        """)
        
        print('📋 historian_timeseries columns:')
        for row in cursor.fetchall():
            print(f'  {row[0]}: {row[1]}')
            
        # Check recent data with actual column names
        cursor.execute("""
            SELECT tag_id, time, value_num, quality
            FROM historian_raw.historian_timeseries 
            WHERE time >= NOW() - INTERVAL '1 hour'
            ORDER BY time DESC LIMIT 5
        """)
        
        print(f'\n📊 Recent data (last hour):')
        for row in cursor.fetchall():
            print(f'  {row[0]}: {row[2]} at {row[1]}')
            
        # Count data by tag in last hour
        cursor.execute("""
            SELECT tag_id, COUNT(*) as count
            FROM historian_raw.historian_timeseries 
            WHERE time >= NOW() - INTERVAL '1 hour'
            GROUP BY tag_id
            ORDER BY count DESC
            LIMIT 5
        """)
        
        print(f'\n📈 Data counts (last hour):')
        for row in cursor.fetchall():
            print(f'  {row[0]}: {row[1]} points')
    
    conn.close()
    print('\n✅ Schema check complete')
    
except Exception as e:
    print(f'❌ Error: {e}')