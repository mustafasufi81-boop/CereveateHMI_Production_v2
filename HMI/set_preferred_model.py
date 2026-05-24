"""One-off: set preferred_model = seasonal_fft for triangle wave tag."""
import psycopg2
from container import container

cfg = container.config['database']
conn = psycopg2.connect(
    host=cfg['host'], port=int(cfg['port']),
    dbname=cfg['database'], user=cfg['user'], password=cfg['password'],
)
conn.autocommit = True
cur = conn.cursor()

TAG = 'Triangle Waves.Int1'

# 1. Widen the check constraint to include new models
cur.execute("ALTER TABLE historian_analytics.tag_alarm_config DROP CONSTRAINT IF EXISTS tag_alarm_config_preferred_model_check")
cur.execute("""
    ALTER TABLE historian_analytics.tag_alarm_config
    ADD CONSTRAINT tag_alarm_config_preferred_model_check
    CHECK (preferred_model IN ('auto','lr','hw','fft','arima','kalman','seasonal_fft','lgbm'))
""")
print("Constraint updated.")

# 2. Update preferred model
cur.execute(
    "UPDATE historian_analytics.tag_alarm_config SET preferred_model = %s WHERE tag_id = %s",
    ('seasonal_fft', TAG),
)
print(f"Rows updated: {cur.rowcount}")

# 3. Verify
cur.execute(
    "SELECT tag_id, preferred_model, hi_hi_limit, lo_lo_limit FROM historian_analytics.tag_alarm_config WHERE tag_id = %s",
    (TAG,),
)
row = cur.fetchone()
print(f"Current row: {row}")

cur.close(); conn.close()
print("Done.")

cur = conn.cursor()

TAG = 'Triangle Waves.Int1'

# Update preferred model
cur.execute(
    "UPDATE historian_analytics.tag_alarm_config SET preferred_model = %s WHERE tag_id = %s",
    ('seasonal_fft', TAG),
)
print(f"Rows updated: {cur.rowcount}")

# Verify current row
cur.execute(
    "SELECT tag_id, preferred_model, hi_hi_limit, lo_lo_limit FROM historian_analytics.tag_alarm_config WHERE tag_id = %s",
    (TAG,),
)
row = cur.fetchone()
print(f"Current row: {row}")

conn.commit()
conn.close()
print("Done.")
