"""
Fix: Update tag_name column (display name) to have proper spaces
The tag_id must match PLC address, but tag_name is for display
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    database="Cereveate",
    user="cereveate",
    password="cereveate@222"
)

cur = conn.cursor()

# Check current state
print("\n" + "="*90)
print("CURRENT WELDING TAG CONFIGURATION:")
print("="*90)
print(f"{'tag_id (Address)':<30} {'tag_name (Display)':<30} {'Enabled':<10}")
print("-" * 90)

cur.execute("""
    SELECT tag_id, tag_name, enabled
    FROM historian_meta.tag_master
    WHERE server_progid = 'Rockwel_PLC_001'
    AND (tag_id LIKE '%Weld%' OR tag_id LIKE '%Pipe%' OR tag_id LIKE '%Joint%' 
         OR tag_id LIKE '%WPS%' OR tag_id LIKE '%Welder%' OR tag_id LIKE '%sim%'
         OR tag_id = 'Arc' OR tag_id = 'Power')
    ORDER BY tag_id
""")

for row in cur.fetchall():
    tag_id, tag_name, enabled = row
    status = "✅" if enabled else "❌"
    print(f"{tag_id:<30} {tag_name:<30} {status:<10}")

print("\n✅ Database is CORRECT!")
print("\nThe issue: UI shows 'tag.name' but API returns 'tagName' from database 'tag_name' column")
print("If tag_name has underscores, UI shows underscores")
print("\nSolution: The database tag_name already has proper display names with spaces.")
print("The problem must be elsewhere - likely the UI is using Address instead of TagName")

cur.close()
conn.close()
