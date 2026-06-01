import urllib.request, json

# Step 1: get OPC tag
with urllib.request.urlopen('http://127.0.0.1:5001/api/opc/values', timeout=5) as r:
    data = json.loads(r.read())
tags = data.get('tags') or data.get('values') or []
opc_tag = next((t for t in tags if 'Triangle Waves.Real4' in str(t.get('tagId',''))), None)
print('OPC tag:', opc_tag)

# Step 2: check what tag_id this maps to in historian
import sys
sys.path.insert(0, r'd:\CereveateHMI_Production\HMI')
from app import create_app
app = create_app()
with app.app_context():
    from extensions import container
    with container.historical_service.connection.cursor() as cur:
        cur.execute("""
            SELECT t.tag_id, t.tag_name, lv.last_quality
            FROM historian_meta.tag_master t
            LEFT JOIN historian_raw.historian_latest_value lv ON lv.tag_id = t.tag_id
            WHERE t.tag_name ILIKE '%Triangle%' OR t.tag_name ILIKE '%Real4%'
        """)
        rows = cur.fetchall()
        if rows:
            for r in rows:
                print(f"DB: tag_id={r['tag_id']}  tag_name={r['tag_name']}  last_quality={r['last_quality']}")
        else:
            print('No matching tag in historian DB')
