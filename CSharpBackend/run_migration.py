import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='Automation_DB',
                        user='cereveate', password='cereveate@222')
conn.autocommit = False
cur = conn.cursor()

steps = [
    ("STEP 1 — Clear blocking test rows", """
        UPDATE historian_raw.historian_events
        SET    alarm_state = 'CLEARED'
        WHERE  event_id IN (32654, 32655, 32656)
    """),
    ("STEP 2a — Add alarm_level to historian_events", """
        ALTER TABLE historian_raw.historian_events
            ADD COLUMN IF NOT EXISTS alarm_level TEXT
    """),
    ("STEP 2b — Add occurrence_id to historian_events", """
        ALTER TABLE historian_raw.historian_events
            ADD COLUMN IF NOT EXISTS occurrence_id UUID DEFAULT gen_random_uuid()
    """),
    ("STEP 2c — Add instance_seq to historian_events", """
        ALTER TABLE historian_raw.historian_events
            ADD COLUMN IF NOT EXISTS instance_seq INTEGER
    """),
    ("STEP 3 — Create alarm_active table", """
        CREATE TABLE IF NOT EXISTS historian_raw.alarm_active (
            alarm_key        TEXT        PRIMARY KEY,
            tag_id           TEXT        NOT NULL,
            level            TEXT        NOT NULL,
            alarm_state      TEXT        NOT NULL CHECK (alarm_state IN ('ACTIVE_UNACK','ACTIVE_ACK','RTN_UNACK')),
            current_event_id BIGINT,
            occurrence_id    UUID        NOT NULL,
            instance_seq     INTEGER     NOT NULL DEFAULT 1,
            raised_at        TIMESTAMPTZ NOT NULL,
            raised_value     DOUBLE PRECISION,
            setpoint_value   DOUBLE PRECISION,
            ack_at           TIMESTAMPTZ,
            ack_by           TEXT,
            rtn_at           TIMESTAMPTZ,
            priority         INTEGER,
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """),
    ("STEP 3b — Create index on alarm_active", """
        CREATE INDEX IF NOT EXISTS idx_alarm_active_tag ON historian_raw.alarm_active(tag_id)
    """),
    ("STEP 4 — Add alarm_onset_delay_s to tag_master", """
        ALTER TABLE historian_meta.tag_master
            ADD COLUMN IF NOT EXISTS alarm_onset_delay_s INTEGER DEFAULT 0
    """),
]

try:
    for name, sql in steps:
        cur.execute(sql)
        print(f"  OK  {name} (rowcount={cur.rowcount})")
    conn.commit()
    print("\nAll steps committed.")
except Exception as e:
    conn.rollback()
    print(f"\nERROR — rolled back: {e}")
    raise

# Verify
print("\n=== VERIFICATION ===")
checks = [
    ("alarm_active exists",
     "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='historian_raw' AND table_name='alarm_active')"),
    ("occurrence_id on historian_events",
     "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='historian_events' AND column_name='occurrence_id')"),
    ("alarm_onset_delay_s on tag_master",
     "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='historian_meta' AND table_name='tag_master' AND column_name='alarm_onset_delay_s')"),
    ("blocking rows cleared",
     "SELECT COUNT(*)=0 FROM historian_raw.historian_events WHERE event_id IN (32654,32655,32656) AND alarm_state != 'CLEARED'"),
]
for label, sql in checks:
    cur.execute(sql)
    result = cur.fetchone()[0]
    status = "PASS" if result else "FAIL"
    print(f"  {status}  {label}")

conn.close()
