"""
Check where admin credentials come from
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='Automation_DB',
    user='cereveate',
    password='cereveate@222'
)

cur = conn.cursor(cursor_factory=RealDictCursor)

print("\n" + "="*80)
print("USER AUTHENTICATION - WHERE 'admin' COMES FROM")
print("="*80 + "\n")

# Check for auth-related tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'historian_raw' 
      AND (table_name LIKE '%user%' OR table_name LIKE '%auth%' OR table_name LIKE '%role%')
    ORDER BY table_name
""")

tables = cur.fetchall()

if tables:
    print("Found Auth Tables:")
    for t in tables:
        print(f"  - {t['table_name']}")
    print()
    
    # Try to find users table
    if any(t['table_name'] == 'users' for t in tables):
        print("Checking 'users' table...")
        cur.execute("SELECT username, role_id, is_active FROM historian_raw.users LIMIT 5")
        users = cur.fetchall()
        
        if users:
            print("\nFound Users in Database:")
            for user in users:
                print(f"  - Username: {user['username']}, Role: {user['role_id']}, Active: {user['is_active']}")
        else:
            print("  (No users found)")
            
else:
    print("❌ No auth tables found in database!")
    print("   Credentials might be hardcoded in Python code")

print("\n" + "="*80)
print("CHECKING PYTHON AUTH CODE")
print("="*80 + "\n")

# Check if there's a hardcoded user in the Python code
import os
os.chdir('d:/CereveateHMI_Production/HMI')

# Look for auth controller
auth_file = 'controllers/auth_controller.py'
if os.path.exists(auth_file):
    print(f"Found: {auth_file}")
    
    with open(auth_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Check if admin is hardcoded
    if '"admin"' in content or "'admin'" in content:
        print("⚠️  'admin' appears in auth_controller.py")
        
        # Find relevant lines
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if 'admin' in line.lower() and ('==' in line or 'password' in line.lower()):
                print(f"  Line {i}: {line.strip()[:100]}")
                
    if 'admin123' in content:
        print("⚠️  Password 'admin123' is HARDCODED in auth_controller.py")
else:
    print(f"Auth controller not found at: {auth_file}")

print("\n" + "="*80)

conn.close()
