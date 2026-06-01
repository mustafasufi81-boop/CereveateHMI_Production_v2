from app import create_app
app = create_app()
with app.app_context():
    from extensions import container
    with container.historical_service.connection.cursor() as cur:
        cur.execute("""
            SELECT t.tag_id, t.tag_name, lv.last_quality
            FROM historian_meta.tag_master t
            LEFT JOIN historian_raw.historian_latest_value lv ON lv.tag_id = t.tag_id
            WHERE t.enabled=true
            LIMIT 30
        """)
        for r in cur.fetchall():
            print(r['tag_id'], r['tag_name'], repr(r['last_quality']))
