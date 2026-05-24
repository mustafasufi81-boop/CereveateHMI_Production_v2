"""
Quick fix: Update just Welding_Voltage_V to match PLC name "Welding Voltage V"
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

old_name = 'Welding_Voltage_V'
new_name = 'Welding Voltage V'

print(f"\nUpdating: {old_name} → {new_name}")

# Update tag_master
cur.execute("""
    UPDATE historian_meta.tag_master
    SET tag_id = %s,
        config_updated_at = NOW()
    WHERE tag_id = %s
    RETURNING tag_id, tag_name, enabled
""", (new_name, old_name))

result = cur.fetchone()
if result:
    print(f"✅ Updated tag_master: {result[0]} | {result[1]} | Enabled: {result[2]}")
else:
    print(f"❌ Tag not found: {old_name}")

conn.commit()
cur.close()
conn.close()

print("\n✅ Done! Now restart C# backend and check if 'Welding Voltage V' appears in database")
