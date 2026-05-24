#!/usr/bin/env python3
"""
Simple alarm checker that reads current PLC values and generates alarms
"""
import psycopg2
import json
from datetime import datetime

def check_current_alarms():
    try:
        # Connect to database
        conn = psycopg2.connect(
            host='localhost',
            user='cereveate', 
            password='cereveate@222',
            database='Cereveate'
        )
        cur = conn.cursor()
        
        print("🔍 Checking current PLC values for alarm conditions...")
        print("=" * 60)
        
        # Check what tables exist first
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'historian_meta'
        """)
        tables = cur.fetchall()
        print("Available tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Try to find data in any table that might have current values
        print("\nLooking for Pump_Trip data...")
        
        # Check tag_master for available tags
        cur.execute("""
            SELECT tag_id, enabled 
            FROM historian_meta.tag_master 
            WHERE tag_id ILIKE '%pump%' OR tag_id ILIKE '%trip%'
            LIMIT 10
        """)
        
        
        results = cur.fetchall()
        alarms_found = []
        
        for tag_id, value, timestamp in results:
            alarm_type = None
            
            # Check for trip conditions (should be 0 or False, alarm if 1 or True)
            if 'trip' in tag_id.lower():
                if value == 1 or value == True or str(value).lower() == 'true':
                    alarm_type = f"🚨 TRIP ALARM: {tag_id} = {value} (Equipment Trip Active!)"
                    alarms_found.append({
                        'tag': tag_id,
                        'value': value,
                        'type': 'TRIP',
                        'priority': 'CRITICAL',
                        'message': alarm_type
                    })
            
            # Check for healthy bits (should be 1 or True, alarm if 0 or False) 
            elif 'healthy' in tag_id.lower() or 'health' in tag_id.lower():
                if value == 0 or value == False or str(value).lower() == 'false':
                    alarm_type = f"⚠️ HEALTH ALARM: {tag_id} = {value} (Health Bit Low!)"
                    alarms_found.append({
                        'tag': tag_id,
                        'value': value,
                        'type': 'HEALTH',
                        'priority': 'WARNING',
                        'message': alarm_type
                    })
            
            # Print all relevant tags
            status = "✅ OK" if not alarm_type else alarm_type
            print(f"{tag_id}: {value} - {status}")
        
        print("\n" + "=" * 60)
        
        if alarms_found:
            print(f"🚨 FOUND {len(alarms_found)} ACTIVE ALARMS:")
            print("-" * 40)
            for alarm in alarms_found:
                print(f"  {alarm['priority']}: {alarm['message']}")
                
            # Store alarms in database
            store_alarms_in_db(cur, alarms_found)
            conn.commit()
            print(f"\n✅ Stored {len(alarms_found)} alarms in database")
        else:
            print("✅ No alarms detected - all systems normal")
        
        conn.close()
        return alarms_found
        
    except Exception as e:
        print(f"❌ Error checking alarms: {e}")
        return []

def store_alarms_in_db(cur, alarms):
    """Store alarms in the alarms table"""
    try:
        # Create alarms table if it doesn't exist
        cur.execute('''
            CREATE TABLE IF NOT EXISTS historian_meta.alarms (
                id SERIAL PRIMARY KEY,
                tag_id VARCHAR(255),
                alarm_type VARCHAR(100),
                message TEXT,
                priority INTEGER,
                value FLOAT,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                acknowledged BOOLEAN DEFAULT FALSE,
                ack_timestamp TIMESTAMPTZ,
                ack_user VARCHAR(100)
            )
        ''')
        
        # Insert new alarms
        for alarm in alarms:
            priority_num = 5 if alarm['priority'] == 'CRITICAL' else 4
            cur.execute('''
                INSERT INTO historian_meta.alarms 
                (tag_id, alarm_type, message, priority, value, timestamp, acknowledged)
                VALUES (%s, %s, %s, %s, %s, NOW(), FALSE)
            ''', (
                alarm['tag'],
                alarm['type'], 
                alarm['message'],
                priority_num,
                alarm['value']
            ))
            
    except Exception as e:
        print(f"Error storing alarms: {e}")

if __name__ == "__main__":
    alarms = check_current_alarms()
    
    if alarms:
        print(f"\n🎯 Quick Summary: {len(alarms)} alarms need attention!")
        print("   Run this script again or check the HMI dashboard")
    else:
        print("\n🎯 All systems running normally")