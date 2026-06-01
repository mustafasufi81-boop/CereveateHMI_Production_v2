import psycopg2

conn = psycopg2.connect(
    dbname="Automation_DB",
    user="cereveate",
    password="cereveate@222",
    host="localhost",
    port="5432"
)

cur = conn.cursor()

print("=" * 80)
print("CLEARING OLD ALARMS FROM alarm_active TABLE")
print("=" * 80)

# Count current alarms
cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
count_before = cur.fetchone()[0]
print(f"\nAlarms in alarm_active BEFORE cleanup: {count_before}")

# Delete all alarms - this will allow the system to create fresh event_ids
# when values next exceed setpoints
cur.execute("DELETE FROM historian_raw.alarm_active")
conn.commit()

cur.execute("SELECT COUNT(*) FROM historian_raw.alarm_active")
count_after = cur.fetchone()[0]
print(f"Alarms in alarm_active AFTER cleanup: {count_after}")

print(f"\n✅ Deleted {count_before - count_after} old alarm records")
print("\nThe system will now create NEW event_ids when alarms trigger.")
print("Old event_ids are preserved in historian_events for history.")

cur.close()
conn.close()

print("\n" * 80)
print("NEXT STEPS:")
print("1. Wait for alarm values to exceed setpoints again")
print("2. New event_ids will be created automatically")
print("3. Fresh lifecycle: RAISE → ACK → CLEAR → RAISE (new event_id)")
print("=" * 80)
