# HistoricalTrends — Query Engine Proposal
**Date**: May 21, 2026  
**Author**: GitHub Copilot  
**Status**: AWAITING APPROVAL  

---

## 1. Problem Statement

| Issue | Current Behaviour | Impact |
|---|---|---|
| **Full table scan** | `read_parquet_data()` pulls ALL matching rows from DB into Python, then samples in pandas | 16M rows × N tags = OOM / 30s+ queries |
| **No concurrency protection** | 10 users × 1M rows each = 10M rows in RAM simultaneously | Server crash / OOM kill |
| **NaN → invalid JSON** | `df.replace({np.nan: None})` raises `ValueError` in pandas ≥ 2.0 | `"Failed to load data: invalid error value specified"` on every load |
| **SET LOCAL statement_timeout** (our previous fix) | Executes on a cursor inside `borrow_connection()`, then cursor is closed before `pd.read_sql` opens its own cursor | Dirty transaction state → psycopg2 error |
| **No sampling indicator to UI** | User doesn't know if they're seeing raw or aggregated data | Confusion / misleading charts |

---

## 2. DB Facts

```
Total rows   : 16,218,098
Time span    : 2025-12-21 → 2026-05-21  (~5 months)
Distinct tags: 413
Top density  : ~300,000 rows/tag  (~1 sample/minute continuous)
```

At 1-minute sampling, a **single tag over 1 week = 10,080 rows** (fine).  
A **single tag over 5 months = 216,000 rows** (heavy).  
**10 tags over 5 months = 2,160,000 rows** (must NOT be pulled to Python).

---

## 3. Proposed Solution — `query_engine.py`

A new single-responsibility module. `DBDataService.read_parquet_data()` delegates to it entirely.  
**No other file is aware of query routing logic.**

---

### 3.1 Query Mode Decision Tree

```
QueryEngine.fetch(tags, start, end, max_points=5000)
        │
        ▼
 STEP 1: Estimate row count WITHOUT a full scan
   est_rows = COUNT(*) WHERE tag_id IN (...) AND time BETWEEN ... AND ...
   (uses hypertable index — returns in <100ms even on 16M rows)
        │
        ├─ est_rows ≤ 50,000
        │   └── MODE: RAW
        │         Query:  SELECT time AS "Timestamp", tag_id, value_num AS "Value"
        │                 WHERE tag_id IN (...) AND time BETWEEN ... AND ...
        │                 ORDER BY time ASC
        │         Result: exact data, no aggregation
        │         Typical: short ranges (≤ 2 days for most tags)
        │
        ├─ 50,001 ≤ est_rows ≤ 2,000,000
        │   └── MODE: TIME-BUCKET (server-side aggregation)
        │         bucket_seconds = ceil(range_seconds / max_points)
        │         Query:  SELECT time_bucket('Xs', time) AS "Timestamp",
        │                        tag_id,
        │                        AVG(value_num)  AS "Value"
        │                 WHERE tag_id IN (...) AND time BETWEEN ... AND ...
        │                 GROUP BY 1, 2
        │                 ORDER BY 1 ASC
        │         Result: ≤ max_points rows, PostgreSQL aggregates in-place
        │         Typical: 2 days–2 months, any number of tags
        │
        └─ est_rows > 2,000,000
            └── MODE: TIME-BUCKET + LTTB (wide range, high fidelity)
                  Use wider bucket (min 5 minutes) to get ~10× max_points rows
                  Then apply LTTB (Largest Triangle Three Buckets) in Python
                  to reduce to max_points while preserving visual shape
                  Result: max_points rows, best visual fidelity for trend lines
                  Typical: full 5-month history, many tags
```

---

### 3.2 NaN / JSON Serialization Fix

**Current (broken in pandas ≥ 2.0):**
```python
df = df.replace({np.nan: None})   # raises ValueError
data = df.to_dict('records')      # NaN leaks through if above fails
```

**New (single helper, called everywhere):**
```python
def _safe_records(df: pd.DataFrame) -> list:
    """Pandas-2.0 safe. NaN/Inf/NaT → null via to_json C layer."""
    import json
    return json.loads(
        df.to_json(orient='records', date_format='iso', double_precision=6)
    )
```
- `to_json()` is implemented in C inside pandas — handles all edge cases  
- Works on pandas 1.x and 2.x  
- `json.loads()` gives us a clean Python list — no bare `NaN` ever reaches `jsonify()`

---

### 3.3 Statement Timeout (Safe Pattern)

**Previous broken approach** (ran SET LOCAL then cursor closed):
```python
with conn.cursor() as _cur:
    _cur.execute("SET LOCAL statement_timeout = '120s'")  # closes here
df_raw = pd.read_sql(sql, conn, params=params)            # new cursor, no timeout
```

**New approach** — pass timeout in the connection options at pool creation (already done in `db_pool.py`):
```python
options=f"-c statement_timeout={cfg['stmt_timeout_ms']} ..."
```
This is applied at connect time and persists for the lifetime of that connection.  
**No per-query SET needed.** Default `StatementTimeoutMs = 120000` (2 minutes).

---

### 3.4 Concurrency Model

```
Flask (threaded=True, 10 pool connections)
    │
    ├── User A: 7-day range, 3 tags  → RAW mode   → 30K rows, 0.3s
    ├── User B: 3-month range, 5 tags → BUCKET mode → 4.5K rows, 0.8s  
    ├── User C: full history, 10 tags → LTTB mode  → 5K rows, 1.2s
    └── User D: export request       → own connection, own timeout
```

Each request borrows ONE connection from the pool and returns it in `finally`.  
Broken connections are discarded (`putconn(conn, close=True)`).  
Pool exhaustion (>10 concurrent) raises `RuntimeError` with a friendly message — no hang.

---

### 3.5 API Response Shape (new fields added)

```json
{
  "success": true,
  "data": [...],
  "count": 4500,
  "query_mode": "time_bucket",
  "bucket_seconds": 60,
  "est_rows_db": 185000,
  "sampled": true,
  "elapsed_ms": 820
}
```

Frontend can show a subtle badge: **"Aggregated (1-min buckets)"** or **"Raw data"**.

---

## 4. Files Changed

| File | Type | What Changes |
|---|---|---|
| `HistoricalTrends/query_engine.py` | **NEW** | All query routing, mode selection, LTTB, NaN safety |
| `HistoricalTrends/db_data_service.py` | **MODIFY** | `read_parquet_data()` → delegates to `QueryEngine.fetch()` |
| `HistoricalTrends/app.py` | **MODIFY** | Add `_safe_records()` helper; remove all `df.replace({np.nan: None})` and `to_dict('records')` calls; expose `query_mode` in `/api/data` response |

---

## 5. Files NOT Changed

- `db_pool.py` — no changes  
- `trends.js` — no changes (response shape is additive, not breaking)  
- `trends.html` — no changes  
- `simple_bi.html` / `simple_bi_dashboard.js` — no changes  
- All other routes in `app.py` — existing logic untouched; only NaN serialization fixed  

---

## 6. Thresholds (tunable via `trends-config.json`)

```json
"QueryEngine": {
  "MaxPoints":          5000,
  "RawModeMaxRows":     50000,
  "BucketModeMaxRows":  2000000,
  "LTTBOversample":     10,
  "StatementTimeoutMs": 120000
}
```

---

## 7. LTTB Algorithm (brief)

Largest Triangle Three Buckets — standard downsampling for time-series charts:
1. Always keep first and last point
2. Divide data into `n` equal buckets
3. In each bucket, keep the point that forms the largest triangle with its neighbours
4. Result: `n` points that maximally preserve visual shape of the signal

Pure Python, no extra dependencies. O(n) time.

---

## 8. What This Fixes

| Issue | Fixed By |
|---|---|
| `ValueError: invalid error value specified` | `_safe_records()` replaces all `df.replace()` calls |
| Server crash on large queries | TIME-BUCKET mode: PostgreSQL aggregates, Python never sees >50K rows |
| Multiple users crash server | Pool properly returned in `finally`; each user gets own connection |
| SET LOCAL statement_timeout bug | Removed entirely; timeout set at pool/connection level |
| User unaware of sampling | `query_mode` + `sampled` fields in response |

---

## 9. Approval Checklist

- [ ] Strategy approved
- [ ] Thresholds accepted (RAW ≤ 50K / BUCKET ≤ 2M / LTTB above)
- [ ] `max_points = 5000` accepted
- [ ] New response fields (`query_mode`, `sampled`, `bucket_seconds`) accepted
- [ ] Ready to build

---
*Once all boxes are checked, implementation begins immediately.*
