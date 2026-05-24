# BI MODULE INTEGRATION TASK REFERENCE
**Created: May 21, 2026 — DO NOT DELETE — Agent Reference Document**

---

## ✅ WHAT WAS AGREED / INSTRUCTED

### THE CORE TASK (User's Exact Words):
> "SYSN THE bi MODULE MAKE SUE ITS HOULD READ ONLY THE TAGS FROM DB AND PARQUET FILE MUST BE REMOVED"
> "we no need to create new bi module just integrate existing bi module with code pointing to db and necessary correction"

### TRANSLATION:
- The **existing** `HistoricalTrends/` module (previously ran on port 6004) is the BI module
- It uses `ParquetDataService` to read `.parquet` files — **this must be replaced**
- Replace `ParquetDataService` with a **drop-in PostgreSQL data service** that returns the **same DataFrame format**
- The `HistoricalTrends/app.py` Flask app, UI templates, and all existing logic stays **UNTOUCHED**
- Only the data source changes: **Parquet files → PostgreSQL `historian_raw.historian_timeseries`**

---

## WHAT NOT TO DO ❌

1. **DO NOT** create a new BI module from scratch in React/TSX
2. **DO NOT** build a new dashboard page in the React HMI
3. **DO NOT** touch `HistoricalTrends/app.py` routes or templates
4. **DO NOT** remove or break the existing HistoricalTrends UI
5. **DO NOT** embed the BI module as an iframe in the HMI (already done and removed — don't re-add)
6. The `BIAnalytics.tsx` React page that was created — it is a **separate** thing, NOT a replacement for HistoricalTrends

---

## ARCHITECTURE — WHAT ALREADY EXISTS

### HistoricalTrends Module (existing, must be preserved)
```
HistoricalTrends/
├── app.py              ← Flask app, port 6004, ALL ROUTES STAY
├── parquet_service.py  ← THIS IS WHAT GETS REPLACED (interface must be kept)
├── templates/          ← HTML UI, stays untouched
├── static/             ← JS/CSS, stays untouched
├── bi_api.py           ← BI analytics API
├── bi_engines/         ← Analytics engine logic
└── trends-config.json  ← Config file
```

### PostgreSQL Database
- **Host**: localhost
- **Port**: 5432
- **Database**: Automation_DB
- **Username**: cereveate
- **Password**: cereveate@222
- **Table**: `historian_raw.historian_timeseries`
- **Tag catalog**: `public.tag_catalog`

### `historian_raw.historian_timeseries` Schema
Key columns used by HistoricalTrends:
- `timestamp` → maps to `Timestamp` in parquet
- `tag_id` → maps to `TagId` in parquet
- `value` → maps to `Value` in parquet

---

## THE SOLUTION — WHAT NEEDS TO BE DONE

### Step 1: Create `HistoricalTrends/db_data_service.py`
A **drop-in replacement** for `ParquetDataService` with the **exact same public interface**:

| Method | Parquet Behaviour | DB Implementation |
|--------|------------------|-------------------|
| `__init__(data_dir, backup_dir)` | Scans parquet files | Connects to PostgreSQL |
| `get_available_tags()` | Returns sorted tag list from parquet cache | `SELECT DISTINCT tag_id FROM historian_raw.historian_timeseries ORDER BY tag_id` |
| `get_available_files()` | Lists parquet files with metadata | Returns date-range "virtual files" from DB date ranges |
| `read_parquet_data(start, end, tags, max_points)` | Reads parquet, pivots to wide DataFrame | `SELECT timestamp, tag_id, value WHERE tag_id IN (...) AND timestamp BETWEEN ...`, pivot to wide format |
| `get_data_summary(start, end)` | Stats per tag | Same stats from DB |
| `export_to_csv(start, end, tags)` | CSV from parquet data | CSV from DB data |
| `export_to_excel(start, end, tags)` | Excel from parquet data | Excel from DB data |
| `get_files_for_date_range(start, end)` | Parquet file list | Return DB date-range markers |

### DataFrame Format Required (CRITICAL)
`read_parquet_data()` MUST return a DataFrame with this exact structure:
```
Timestamp          | TagId_1 | TagId_2 | TagId_3 | ...
2026-05-21 08:00   | 45.2    | 102.1   | NaN     | ...
2026-05-21 08:01   | 45.3    | 102.4   | 99.8    | ...
```
- `Timestamp` column (datetime)
- One column per tag (tag_id as column name)
- Values are float/numeric
- NaN where no value exists for that tag at that time

### Step 2: Swap in `app.py`
Change only 2 lines in `app.py`:
```python
# REMOVE:
from parquet_service import ParquetDataService
data_service = ParquetDataService(paths.get('DataLogDirectory', ...), paths.get('BackupDirectory', ...))

# ADD:
from db_data_service import DBDataService
data_service = DBDataService()
```

### Step 3: Run HistoricalTrends on port 6004
Start it with the existing `start.bat` or `python app.py`

### Step 4: HMI Tab links to port 6004
The `HmiAnalyticsTab.tsx` **BI ANALYTICS** button navigates to `/bi-analytics` route.  
The `/bi-analytics` React page can embed the HistoricalTrends UI (port 6004) or just link to it.

---

## CURRENT STATE (as of May 21, 2026)

### What is DONE ✅
- `WEB_HMI_MFA/HMI/controllers/bi_controller.py` — refactored, reads from PostgreSQL (4 endpoints: /tags, /trends, /baselines, /forecast)
- `HmiAnalyticsTab.tsx` — BI ANALYTICS tab navigates to `/bi-analytics` route (no more iframe to 6004)
- `BIAnalytics.tsx` — New React page showing a basic BI dashboard (tag list + trend chart + stats) reading from Flask `/api/bi/*`
- Port 6004 server is NOT running (HistoricalTrends not started)

### What is PENDING ❌
- `HistoricalTrends/db_data_service.py` — **NOT CREATED YET** (the main task)
- `HistoricalTrends/app.py` — still points to `ParquetDataService` (needs 2-line swap)
- HistoricalTrends service not running on port 6004

---

## WHAT THE USER WANTS RIGHT NOW

1. Create `HistoricalTrends/db_data_service.py` — drop-in PostgreSQL replacement for `ParquetDataService`
2. Edit `HistoricalTrends/app.py` — swap `ParquetDataService` → `DBDataService` (2 lines only)
3. Start `HistoricalTrends/app.py` on port 6004 — full existing UI works but reads from DB
4. The HMI BI Analytics tab opens the HistoricalTrends UI (port 6004) — either as iframe or direct link

---

## DB CONNECTION CONFIG
```python
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "Automation_DB",
    "user": "cereveate",
    "password": "cereveate@222"
}
TABLE = "historian_raw.historian_timeseries"
TAG_CATALOG = "public.tag_catalog"
```
