"""Check topic configuration in database"""
import sys
import os

# Add parent directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from src.database.db_client import DatabaseClient

def check_topics():
    db = DatabaseClient()
    
    print("\n" + "="*80)
    print("TOPIC CONFIGURATION IN DATABASE")
    print("="*80)
    
    # Check topic_master
    print("\n1. Topics in topic_master:")
    result = db.execute_query("""
        SELECT topic_id, topic, is_active, qos 
        FROM historian_raw.topic_master 
        ORDER BY topic
    """)
    
    if result:
        print(f"\n{'ID':<5} {'Topic':<50} {'Active':<8} {'QoS'}")
        print("-" * 80)
        for row in result:
            print(f"{row[0]:<5} {row[1]:<50} {str(row[2]):<8} {row[3]}")
    else:
        print("No topics configured!")
    
    # Check mqtt_audit_main for received data
    print("\n2. Topics with received data (mqtt_audit_main):")
    result = db.execute_query("""
        SELECT DISTINCT topic, COUNT(*) as message_count 
        FROM historian_raw.mqtt_audit_main 
        GROUP BY topic 
        ORDER BY topic
    """)
    
    if result:
        print(f"\n{'Topic':<50} {'Message Count'}")
        print("-" * 80)
        for row in result:
            print(f"{row[0]:<50} {row[1]}")
    else:
        print("No messages received yet!")
    
    # Check for production/plant_b specifically
    print("\n3. Checking for production/plant_b topics:")
    result = db.execute_query("""
        SELECT topic, COUNT(*) as count
        FROM historian_raw.mqtt_audit_main
        WHERE topic LIKE 'production/plant_b%'
        GROUP BY topic
    """)
    
    if result:
        for row in result:
            print(f"  {row[0]}: {row[1]} messages")
    else:
        print("  No messages from production/plant_b topics!")
    
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    check_topics()
