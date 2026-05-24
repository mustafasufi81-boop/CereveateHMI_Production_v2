"""
test_db_calculations.py — Direct DB verification tests (no HTTP)
Connects to Automation_DB and verifies:
  1. Data is flowing (recent rows exist)
  2. No duplicates
  3. No future timestamps
  4. v_daily_hourly_agg avg matches raw table AVG
  5. ts_hourly_agg matches v_daily_hourly_agg
  6. report_gen_log is being written
  7. No null tag_id rows
  8. Quality values are valid
"""
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

DB_DSN   = "host=localhost port=5432 dbname=Automation_DB user=cereveate password=cereveate@222"
TEST_TAG = "Random.Real4"


# ─── session fixture ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def db():
    try:
        conn = psycopg2.connect(DB_DSN, cursor_factory=RealDictCursor)
    except Exception as e:
        pytest.skip(f"Cannot connect to DB: {e}")
    conn.set_session(autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'Asia/Kolkata'")
    yield conn
    conn.close()


# ─── TC-DB01 : recent data is flowing ────────────────────────────────────────
def test_data_flowing_last_5_minutes(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT count(*) AS cnt
            FROM historian_raw.historian_timeseries
            WHERE time > now() - interval '5 minutes'
        """)
        row = cur.fetchone()
    assert row["cnt"] > 0, \
        "No data in last 5 minutes — OPC ingest may be stopped"


# ─── TC-DB02 : no null tag_id rows ───────────────────────────────────────────
def test_no_null_tag_ids(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT count(*) AS cnt
            FROM historian_raw.historian_timeseries
            WHERE tag_id IS NULL
        """)
        row = cur.fetchone()
    assert row["cnt"] == 0, \
        f"Found {row['cnt']} rows with NULL tag_id — data integrity issue"


# ─── TC-DB03 : no future timestamps ──────────────────────────────────────────
def test_no_future_timestamps(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT count(*) AS cnt
            FROM historian_raw.historian_timeseries
            WHERE time > now() + interval '1 minute'
        """)
        row = cur.fetchone()
    assert row["cnt"] == 0, \
        f"Found {row['cnt']} future-dated rows — clock or timezone issue"


# ─── TC-DB04 : no duplicate (tag_id, time) pairs ─────────────────────────────
def test_no_duplicate_timestamps(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT count(*) AS dup_count
            FROM (
                SELECT tag_id, time, count(*) AS c
                FROM historian_raw.historian_timeseries
                WHERE time > now() - interval '1 hour'
                GROUP BY tag_id, time
                HAVING count(*) > 1
            ) t
        """)
        row = cur.fetchone()
    assert row["dup_count"] == 0, \
        f"Found {row['dup_count']} duplicate (tag_id, time) pairs in last hour"


# ─── TC-DB05 : valid quality values only ─────────────────────────────────────
def test_valid_quality_values(db):
    VALID = {"G", "B", "U", "C", "Good", "Bad", "Uncertain", "CommError",
             "good", "bad", "uncertain", "commerror"}
    with db.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT quality
            FROM historian_raw.historian_timeseries
            WHERE time > now() - interval '1 hour'
        """)
        rows = cur.fetchall()
    invalid = [r["quality"] for r in rows if r["quality"] not in VALID]
    assert not invalid, \
        f"Unexpected quality values found: {invalid}"


# ─── TC-DB06 : hourly agg AVG matches raw table ──────────────────────────────
def test_hourly_agg_avg_matches_raw(db):
    """
    v_daily_hourly_agg.avg_val must equal AVG(value_num) from raw table
    for the same tag/hour. Tolerance ±0.01.
    """
    test_date = date.today() - timedelta(days=1)

    # Get a sample hour from the view
    with db.cursor() as cur:
        cur.execute("""
            SELECT local_hour, avg_val, min_val, max_val
            FROM historian_raw.v_daily_hourly_agg
            WHERE tag_id = %s AND local_date = %s
            ORDER BY local_hour
            LIMIT 3
        """, (TEST_TAG, test_date))
        agg_rows = cur.fetchall()

    if not agg_rows:
        pytest.skip(f"No agg data for {TEST_TAG} on {test_date}")

    failures = []
    for agg in agg_rows:
        hour = agg["local_hour"]
        with db.cursor() as cur:
            cur.execute("""
                SELECT
                    AVG(value_num) AS raw_avg,
                    MAX(value_num) AS raw_max,
                    MIN(value_num) AS raw_min
                FROM historian_raw.historian_timeseries
                WHERE tag_id = %s
                  AND time AT TIME ZONE 'Asia/Kolkata' >= %s::date + (%s || ' hours')::interval
                  AND time AT TIME ZONE 'Asia/Kolkata' <  %s::date + (%s || ' hours')::interval + interval '1 hour'
            """, (TEST_TAG,
                  str(test_date), str(hour),
                  str(test_date), str(hour)))
            raw = cur.fetchone()

        if raw["raw_avg"] is None:
            continue

        avg_diff = abs(float(raw["raw_avg"]) - float(agg["avg_val"]))
        if avg_diff > 0.01:
            failures.append(
                f"Hour {hour:02d}:  raw_avg={float(raw['raw_avg']):.4f}  "
                f"view_avg_val={float(agg['avg_val']):.4f}  diff={avg_diff:.4f}"
            )

    assert not failures, \
        f"v_daily_hourly_agg does not match raw table:\n" + "\n".join(failures)


# ─── TC-DB07 : ts_hourly_agg matches v_daily_hourly_agg ──────────────────────
def test_ts_hourly_agg_matches_view(db):
    test_date = date.today() - timedelta(days=1)

    with db.cursor() as cur:
        cur.execute("""
            SELECT
                a.avg_value   AS ts_avg,
                b.avg_val     AS view_avg,
                EXTRACT(HOUR FROM a.bucket AT TIME ZONE 'Asia/Kolkata') AS hour
            FROM historian_raw.ts_hourly_agg a
            JOIN historian_raw.v_daily_hourly_agg b
              ON a.tag_id = b.tag_id
             AND DATE(a.bucket AT TIME ZONE 'Asia/Kolkata') = b.local_date
             AND EXTRACT(HOUR FROM a.bucket AT TIME ZONE 'Asia/Kolkata') = b.local_hour
            WHERE a.tag_id = %s
              AND DATE(a.bucket AT TIME ZONE 'Asia/Kolkata') = %s
            LIMIT 5
        """, (TEST_TAG, test_date))
        rows = cur.fetchall()

    if not rows:
        pytest.skip("No ts_hourly_agg data to compare (may not have refreshed yet)")

    failures = []
    for row in rows:
        diff = abs(float(row["ts_avg"]) - float(row["view_avg"]))
        if diff > 0.01:
            failures.append(
                f"Hour {int(row['hour'])}:  ts_avg={float(row['ts_avg']):.4f}  "
                f"view_avg={float(row['view_avg']):.4f}  diff={diff:.4f}"
            )
    assert not failures, \
        "ts_hourly_agg does not match v_daily_hourly_agg:\n" + "\n".join(failures)


# ─── TC-DB08 : report_gen_log is being written ────────────────────────────────
def test_report_gen_log_exists(db):
    with db.cursor() as cur:
        cur.execute("""
            SELECT count(*) AS cnt
            FROM historian_meta.report_gen_log
        """)
        row = cur.fetchone()
    assert row["cnt"] > 0, \
        "historian_meta.report_gen_log is empty — reports may not be logging correctly"


# ─── TC-DB09 : all enabled tags have recent data ─────────────────────────────
def test_enabled_tags_have_data(db):
    """Tags marked enabled=TRUE in tag_master must have data in last 10 minutes."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT tm.tag_id
            FROM historian_meta.tag_master tm
            WHERE tm.enabled = TRUE
            AND NOT EXISTS (
                SELECT 1 FROM historian_raw.historian_timeseries ht
                WHERE ht.tag_id = tm.tag_id
                  AND ht.time > now() - interval '10 minutes'
            )
        """)
        missing = [r["tag_id"] for r in cur.fetchall()]
    assert not missing, \
        f"Enabled tags with NO data in last 10 min: {missing[:10]}"


# ─── TC-DB10 : hourly agg has all 24 hours for a full day ────────────────────
def test_all_24_hours_in_agg(db):
    test_date = date.today() - timedelta(days=1)
    with db.cursor() as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT local_hour) AS hour_count
            FROM historian_raw.v_daily_hourly_agg
            WHERE tag_id = %s AND local_date = %s
        """, (TEST_TAG, test_date))
        row = cur.fetchone()
    if row["hour_count"] == 0:
        pytest.skip(f"No agg data for {TEST_TAG} on {test_date}")
    assert row["hour_count"] == 24, \
        f"Expected 24 distinct hours, got {row['hour_count']} for {test_date}"
