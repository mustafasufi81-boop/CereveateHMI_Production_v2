"""
REVERT: Change 'Welding Voltage V' back to 'Welding_Voltage_V' to match appsettings.json
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Revert back to underscores to match appsettings.json TagId
cur.execute("""
    UPDATE historian_meta.tag_master
    SET tag_id = 'Welding_Voltage_V',
        config_updated_at = NOW()
    WHERE tag_id = 'Welding Voltage V'
    RETURNING tag_id
""")

result = cur.fetchone()
if result:
    print(f"✅ Reverted: 'Welding Voltage V' → 'Welding_Voltage_V'")
    print("   (To match appsettings.json TagId)")
else:
    print("ℹ️  Already named 'Welding_Voltage_V' or not found")

conn.commit()

# Now check all welding tags
print("\nCurrent welding tag names in database:")
cur.execute("""
    SELECT tag_id, enabled  
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001'
    AND (tag_id LIKE '%Weld%' OR tag_id LIKE '%Pipe%' OR tag_id LIKE '%Joint%' 
         OR tag_id LIKE '%WPS%' OR tag_id LIKE '%Welder%' OR tag_id LIKE '%sim%'
         OR tag_id = 'Arc' OR tag_id = 'Power')
    ORDER BY tag_id
""")

for row in cur.fetchall():
    tag_id, enabled = row
    status = "✅" if enabled else "❌"
    print(f"  {status} {tag_id}")

cur.close()
conn.close()

print("\n✅ Database tag names now match appsettings.json TagId values (with underscores)")
print("   Restart C# backend and check if tags appear in API")
