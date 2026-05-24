"""Create bi_model_versions table and verify schema."""
import psycopg2, sys
sys.path.insert(0, '.')
from container import container
cfg = container.config['database']
conn = psycopg2.connect(
    host=cfg['host'], port=cfg['port'], dbname=cfg['database'],
    user=cfg['user'], password=cfg['password']
)
cur = conn.cursor()

cur.execute("""
CREATE SCHEMA IF NOT EXISTS historian_analytics;
CREATE TABLE IF NOT EXISTS historian_analytics.bi_model_versions (
    id              SERIAL          PRIMARY KEY,
    tag_id          TEXT            NOT NULL,
    model_name      TEXT            NOT NULL,
    version         INTEGER         NOT NULL,
    params_json     JSONB           NOT NULL,
    n_train_points  INTEGER         NOT NULL DEFAULT 0,
    n_days_trained  NUMERIC(6,2)    NOT NULL DEFAULT 0,
    mae             NUMERIC(14,8),
    rmse            NUMERIC(14,8),
    aic             NUMERIC(14,4),
    is_active       BOOLEAN         NOT NULL DEFAULT FALSE,
    promoted_at     TIMESTAMPTZ,
    trained_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    retire_after    TIMESTAMPTZ,
    notes           TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS bi_model_versions_active_uidx
    ON historian_analytics.bi_model_versions(tag_id, model_name)
    WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS bi_model_versions_tag_idx
    ON historian_analytics.bi_model_versions(tag_id, model_name, trained_at DESC);
COMMENT ON TABLE historian_analytics.bi_model_versions IS
    'Versioned forecast model weights — only promoted when provably better (>=5% MAE gain)';
""")
conn.commit()
print("Table created / verified OK")

cur.execute("""
    SELECT table_name FROM information_schema.tables
    WHERE table_schema = 'historian_analytics' ORDER BY table_name
""")
print("Tables now:", [r[0] for r in cur.fetchall()])

cur.execute("""
    SELECT column_name, data_type FROM information_schema.columns
    WHERE table_schema='historian_analytics' AND table_name='bi_model_versions'
    ORDER BY ordinal_position
""")
print("Columns:", [(r[0], r[1]) for r in cur.fetchall()])

cur.execute("SELECT COUNT(*) FROM historian_analytics.bi_model_versions")
print("Row count:", cur.fetchone()[0])
conn.close()

