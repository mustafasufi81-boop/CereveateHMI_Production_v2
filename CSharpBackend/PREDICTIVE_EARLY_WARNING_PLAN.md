# Predictive Early Warning System — Full Implementation Plan
## Cereveate OPC DA / Analytics Platform

> **Last Updated:** May 21 2026  
> **Status:** Phase 1 COMPLETE — all backend + frontend files created, schema ready to run

---

## 1. Overview

This plan describes how to build an **AI-powered Predictive Early Warning System (PEWS)** on top of the existing historian data pipeline. The system will:

- Detect abnormal trends **before** they become alarms
- Predict future values using machine learning
- Send real-time notifications to the HMI dashboard
- Use the existing `historian_raw.historian_timeseries` data (149 tags, updated every 1 second)

---

## 2. DB-Centric Analytics Architecture (Core Design Principle)

The Predictive Early Warning System is designed as a **database-driven analytics platform**, not a direct live OPC/PLC inference engine.

### Core Principle

All prediction, anomaly detection, and AI analysis operate exclusively on:
- Historical historian data
- Time-windowed database reads
- Aggregated and processed TimescaleDB data

> **The analytics engine does NOT consume raw live PLC/OPC values directly.**

### Actual Data Flow

```
PLC / OPC Devices
        ↓
Historian Collector Service (existing — no changes)
        ↓
PostgreSQL + TimescaleDB  [historian_raw.historian_timeseries]
        ↓
Predictive Analytics Engine  (reads DB windows every 60s)
        ↓
Early Warnings / Predictions  (saved only when anomaly confirmed)
        ↓
MQTT + Flask API + React HMI  (notification delivery)
```

### Why This Architecture Was Chosen

| Advantage | Benefit |
|-----------|---------|
| Decoupled from live OPC stream | Analytics cannot disturb historian collection |
| Safer industrial architecture | No risk to real-time acquisition layer |
| Replay capability | Historical incidents can be reprocessed and re-analyzed |
| Easier debugging | Predictions always reproducible from stored data |
| Better scalability | Batch/time-window processing instead of per-tag live inference |
| Easier model retraining | ML models train directly from historian database |
| Higher reliability | Analytics continues even if OPC connection temporarily drops |

### Analytics Execution Model

The predictive engine periodically reads historian data windows:

| Window | Purpose |
|--------|---------|
| Last 1 minute | Real-time anomaly detection (Z-score, RoC) |
| Last 10 minutes | Rate-of-change trends |
| Last 1 hour | Rolling baseline comparison |
| Last 30 days | ML model training (ARIMA, Isolation Forest) |
| Last 90 days | LSTM deep learning training |

Processing is performed **entirely in memory**. Only the following are persisted back to the analytics schema:
- Confirmed anomalies
- Early warnings
- Important predictions
- Nightly baseline summaries

### Future Optimization Strategy

To reduce database load as the system scales, the following techniques will be applied:

- **Materialized views** — precomputed statistical windows
- **Aggregated feature tables** — hourly/daily summaries per tag
- **Incremental timestamp-based reads** — avoid re-scanning entire windows:

```sql
-- Efficient incremental read pattern
WHERE time > last_processed_timestamp
  AND tag_id = ANY(monitored_tags)
ORDER BY time ASC
```

### Industrial Design Philosophy

This platform is intentionally designed as a:
- **Historian analytics platform**
- **Condition monitoring system**
- **Predictive maintenance engine**

— rather than a direct real-time control or closed-loop AI system.

This ensures: **Stability · Auditability · Maintainability · Safe deployment in industrial environments**

---

## 3. What We Already Have (Advantage)

| Asset | How It Helps |
|-------|-------------|
| `historian_raw.historian_timeseries` | Historical values for ALL tags — training data |
| 149 tags @ 1-second resolution | High-frequency data = accurate trend detection |
| Flask HMI backend (port 6001) | Just add 2 new API endpoints — no restructure |
| React HMI frontend (port 8090) | Add 1 new route/page — no existing pages touched |
| MQTT broker (Mosquitto) | Already running — just subscribe to new topic |
| PostgreSQL + TimescaleDB | Just add new schema — existing tables untouched |

---

## 4. Integration Design — Minimal Touch Principle

> **Rule**: Zero changes to existing services. PEWS is a completely standalone module that only **reads** from the existing DB and **publishes** to existing MQTT + Flask.

### What Gets Changed vs What Stays Untouched

| Component | Change Required | Impact |
|-----------|----------------|--------|
| `historian_raw.historian_timeseries` | ❌ No change | Read-only by PEWS |
| C# OPC Backend (port 5001) | ❌ No change | Not touched |
| Flask `app.py` (port 6001) | ✅ Add **2 endpoints** only | `GET /api/pews/warnings` + `GET /api/pews/status` |
| React HMI (port 8090) | ✅ Add **1 new page** only | `/analytics` route — existing pages untouched |
| Mosquitto broker | ❌ No change | PEWS publishes to new topic `pews/#` |
| PostgreSQL | ✅ Add **1 new schema** only | `historian_analytics` — existing schemas untouched |
| PEWS Python service | ✅ **NEW standalone service** | Port 7001, completely independent |

### Full System Architecture

```
═══════════════════════════════════════════════════════════
  EXISTING SYSTEM (zero changes)
═══════════════════════════════════════════════════════════
  PLC/OPC → C# Backend (5001) → historian_timeseries
                                         │
                        READ ONLY ───────┘
                             │
═══════════════════════════════════════════════════════════
  PEWS MODULE (new, standalone)
═══════════════════════════════════════════════════════════
                             ↓
              ┌──────────────────────────┐
              │  predictive_engine/      │  Port 7001
              │  app.py (FastAPI)        │  Standalone Python service
              │                          │
              │  ┌─────────────────────┐ │
              │  │ statistical_engine  │ │  Layer 1 — runs immediately
              │  │ baseline_engine     │ │  Layer 2 — nightly compute
              │  │ ml_engine (ARIMA)   │ │  Layer 3 — after 7 days data
              │  └─────────────────────┘ │
              └────────┬─────────────────┘
                       │
          ┌────────────┼────────────────┐
          ↓            ↓                ↓
   historian_analytics  MQTT topic    Flask /api/pews/*
   (new schema, 3 tables) pews/alerts  (2 new endpoints)
                                            │
═══════════════════════════════════════════════════════════
  HMI INTEGRATION (1 new page added to React)
═══════════════════════════════════════════════════════════
                                            ↓
                              React /analytics page
                              ├── System Health Score widget
                              ├── Active Warnings list
                              ├── Tag trend + deviation chart
                              └── Deviation reason label
```

### PEWS Service — Standalone Python Module

```
WEB_HMI_MFA/
└── predictive_engine/          ← NEW folder, fully standalone
    ├── app.py                  ← FastAPI (port 7001)
    ├── scheduler.py            ← APScheduler: run detection every 60s
    ├── config.py               ← DB connection, thresholds
    ├── requirements.txt
    │
    ├── engines/
    │   ├── statistical_engine.py   ← Z-score, RoC, IQR
    │   ├── baseline_engine.py      ← Nightly mean/std per tag
    │   └── ml_engine.py            ← ARIMA (added in Phase 3)
    │
    ├── data/
    │   ├── db_reader.py            ← SELECT from historian_timeseries
    │   └── db_writer.py            ← INSERT into historian_analytics
    │
    └── notification/
        └── mqtt_publisher.py       ← Publish to pews/alerts
```

### Flask Changes — 2 Endpoints Only

```python
# In WEB_HMI_MFA/HMI/app.py — ADD these 2 routes, nothing else changes:

@app.route('/api/pews/warnings')
def get_pews_warnings():
    # SELECT from historian_analytics.early_warnings
    # Returns: list of active unacknowledged warnings

@app.route('/api/pews/status')
def get_pews_status():
    # SELECT from historian_analytics.tag_baselines
    # Returns: health score + tag deviation summary
```

### React HMI Changes — 1 New Page Only

```
apex-hmi/src/
├── pages/
│   ├── Dashboard.tsx       ← NO CHANGE
│   ├── Alarms.tsx          ← NO CHANGE
│   └── Analytics.tsx       ← NEW PAGE (add route /analytics)
│
└── components/
    └── pews/               ← NEW folder
        ├── WarningPanel.tsx     ← Active warnings list
        ├── TrendDeviation.tsx   ← Chart: actual vs average + reason
        └── HealthScore.tsx      ← System health score widget
```

### HMI Analytics Page Layout

```
┌──────────────────────────────────────────────────────────┐
│  🔴 EARLY WARNING SYSTEM                  [Live ● 60s]   │
├─────────────────────┬────────────────────────────────────┤
│  System Health      │  Active Warnings                   │
│  ┌───────────────┐  │  ┌──────────────────────────────┐  │
│  │   72 / 100    │  │  │ 🟠 CV1101  Rate of change    │  │
│  │  ████████░░   │  │  │   +18.3% above avg  [Ack]    │  │
│  │  CAUTION      │  │  ├──────────────────────────────┤  │
│  └───────────────┘  │  │ 🟡 AY1101  Drift detected    │  │
│                     │  │   +5.2% above 1hr avg  [Ack] │  │
│                     │  └──────────────────────────────┘  │
├─────────────────────┴────────────────────────────────────┤
│  Tag Trend — CV1101                        Last 30 min   │
│  95 ┤                         ╭───╮                       │
│  90 ┤           ─ ─ ─ ─ ─ ─ ─│   │⚠  ← deviation here   │
│  85 ┤───────────────────────╮╯   ╰──  ← actual           │
│  80 ┤░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   ← normal range     │
│     └─────────────────────────────────────────────────   │
│  Reason: Rate of change 2.8 units/sec (normal: <1.2)     │
│  Deviation: +18.3% above 1-hour average (avg=76.2)       │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Detection Methods (3-Layer Approach)

### Layer 1 — Statistical (Fast, No Training Required)
Runs immediately, no historical data needed.

| Method | What It Detects | Implementation |
|--------|----------------|----------------|
| **Z-Score** | Sudden spike/drop vs rolling mean | `(value - mean) / std > 3` |
| **Rate of Change (RoC)** | Too fast rise/fall | `Δvalue/Δtime > threshold` |
| **Rolling Average Deviation** | Drift from normal | Compare 1-min avg vs 1-hour avg |
| **IQR (Interquartile Range)** | Statistical outliers | Values outside Q1-1.5×IQR or Q3+1.5×IQR |

### Layer 2 — Machine Learning (Trained on Historical Data)
Trained on last 30 days of historian data.

| Model | What It Detects | Library |
|-------|----------------|---------|
| **ARIMA / SARIMA** | Future value prediction (time-series forecasting) | `statsmodels` |
| **Isolation Forest** | Anomaly detection (unsupervised) | `scikit-learn` |
| **LSTM Neural Network** | Complex pattern prediction | `tensorflow` / `keras` |
| **Prophet** | Trend + seasonality forecasting | `prophet` (Meta) |

### Layer 3 — Correlation (Multi-Tag Intelligence)
Detects when multiple tags behave unusually together.

| Method | What It Detects |
|--------|----------------|
| **Pearson Correlation Matrix** | When normally-correlated tags diverge |
| **PCA (Principal Component Analysis)** | System-wide anomaly from combined tag behavior |
| **Tag Pair Monitoring** | e.g., if `CV1101` rises but `AY1101` doesn't follow → abnormal |

---

## 5. Warning Severity Levels

```
Level 1 — INFO (Blue)      → Trend drifting slightly from baseline
Level 2 — CAUTION (Yellow) → Rate of change exceeding normal range
Level 3 — WARNING (Orange) → Predicted breach of setpoint in next 10 min
Level 4 — ALERT (Red)      → Anomaly confirmed, immediate attention required
```

---

## 6. Database Schema (New Tables)

```sql
-- Predictions table
CREATE TABLE historian_analytics.tag_predictions (
    id              BIGSERIAL PRIMARY KEY,
    time            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tag_id          TEXT NOT NULL,
    predicted_value DOUBLE PRECISION,
    prediction_horizon_min INT,      -- predicted this many minutes ahead
    confidence      DOUBLE PRECISION, -- 0.0 to 1.0
    model_used      TEXT,            -- 'arima', 'lstm', 'prophet'
    actual_value    DOUBLE PRECISION  -- filled in after the fact
);
SELECT create_hypertable('historian_analytics.tag_predictions', 'time');

-- Early warnings table
CREATE TABLE historian_analytics.early_warnings (
    id              BIGSERIAL PRIMARY KEY,
    time            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tag_id          TEXT NOT NULL,
    warning_level   INT NOT NULL,          -- 1=INFO, 2=CAUTION, 3=WARNING, 4=ALERT
    warning_type    TEXT NOT NULL,         -- 'spike', 'drift', 'rate_of_change', 'anomaly', 'prediction'
    current_value   DOUBLE PRECISION,
    predicted_value DOUBLE PRECISION,
    threshold_value DOUBLE PRECISION,
    message         TEXT,
    acknowledged    BOOLEAN DEFAULT FALSE,
    ack_by          TEXT,
    ack_time        TIMESTAMPTZ
);
SELECT create_hypertable('historian_analytics.early_warnings', 'time');

-- Tag baselines (computed nightly)
CREATE TABLE historian_analytics.tag_baselines (
    tag_id          TEXT PRIMARY KEY,
    mean_value      DOUBLE PRECISION,
    std_value       DOUBLE PRECISION,
    min_value       DOUBLE PRECISION,
    max_value       DOUBLE PRECISION,
    q1_value        DOUBLE PRECISION,
    q3_value        DOUBLE PRECISION,
    normal_roc_max  DOUBLE PRECISION,   -- normal max rate of change per second
    last_computed   TIMESTAMPTZ,
    sample_count    INT
);
```

---

## 7. Python Service Structure

```
WEB_HMI_MFA/
└── predictive_engine/
    ├── app.py                    ← FastAPI service (port 7001)
    ├── config.py                 ← tag list, thresholds, model settings
    ├── requirements.txt
    │
    ├── engines/
    │   ├── statistical_engine.py   ← Z-score, RoC, IQR (Layer 1)
    │   ├── ml_engine.py            ← ARIMA, Isolation Forest (Layer 2)
    │   ├── lstm_engine.py          ← LSTM deep learning (Layer 2 advanced)
    │   ├── correlation_engine.py   ← Multi-tag correlation (Layer 3)
    │   └── baseline_engine.py      ← Nightly baseline computation
    │
    ├── data/
    │   ├── db_reader.py            ← Reads from historian_timeseries
    │   └── db_writer.py            ← Writes predictions + warnings
    │
    ├── notification/
    │   ├── mqtt_publisher.py       ← Publishes to pews/alerts topic
    │   └── alert_formatter.py      ← Formats warning messages
    │
    └── models/
        └── saved/                  ← Persisted trained ML models (.pkl, .h5)
```

---

## 8. Implementation Phases

### Phase 1 — Statistical Detection (Week 1-2)
**No ML training needed — works on Day 1**

- [ ] Create `historian_analytics` schema + tables
- [ ] Build `statistical_engine.py` (Z-score + RoC + IQR)
- [ ] Build `db_reader.py` — reads last 60 minutes of data per tag
- [ ] Build `db_writer.py` — writes warnings to `early_warnings` table
- [ ] Build `mqtt_publisher.py` — publishes to `pews/alerts`
- [ ] Add `/api/early-warnings` endpoint to Flask (port 6001)
- [ ] Add notification bell to React HMI
- [ ] **Test**: Inject a spike into a tag, verify notification appears

**Deliverable**: Live statistical alerts in HMI within 2 weeks

---

### Phase 2 — Baseline Learning (Week 2-3)
**System learns what "normal" looks like**

- [ ] Build `baseline_engine.py` — computes per-tag mean/std/IQR from last 30 days
- [ ] Schedule nightly baseline recomputation (2 AM cron)
- [ ] Store baselines in `tag_baselines` table
- [ ] Update statistical engine to use learned baselines instead of hardcoded thresholds
- [ ] Build HMI page: "Tag Baselines" — show normal range per tag

**Deliverable**: Adaptive thresholds based on real operating data

---

### Phase 3 — ARIMA Forecasting (Week 3-4)
**Predicts next 5-15 minutes**

- [ ] Build `ml_engine.py` with ARIMA per tag
- [ ] Train ARIMA on last 7 days of data per tag (run once daily)
- [ ] Store predictions in `tag_predictions` table (every 5 minutes)
- [ ] Add predicted value overlay to HMI trend charts (dashed line)
- [ ] Fire Level 3 WARNING if predicted value will breach setpoint in <10 min

**Deliverable**: "Tag X predicted to exceed limit in 8 minutes" warnings

---

### Phase 4 — Isolation Forest Anomaly Detection (Week 4-5)
**Detects complex anomalies that statistics miss**

- [ ] Train Isolation Forest on last 30 days per tag
- [ ] Save models to `models/saved/` as `.pkl` files
- [ ] Run inference every 60 seconds
- [ ] Combine score with statistical score for final severity level

**Deliverable**: Unsupervised anomaly detection running 24/7

---

### Phase 5 — LSTM Deep Learning (Week 5-7)
**Best accuracy for complex time-series patterns**

- [ ] Build `lstm_engine.py` using Keras/TensorFlow
- [ ] Architecture: 2 LSTM layers (64 units) + Dense output
- [ ] Input: 60-step sliding window (last 60 seconds of readings)
- [ ] Output: Next 10 predicted values
- [ ] Train on 90 days of data per tag group (group similar tags)
- [ ] Retrain weekly automatically

**Deliverable**: Highest accuracy predictions for critical tags

---

### Phase 6 — Correlation & Multi-Tag Intelligence (Week 7-8)
**System-level early warning**

- [ ] Build `correlation_engine.py`
- [ ] Compute correlation matrix for all 149 tags (updated daily)
- [ ] Monitor for correlation breakdown (e.g., tag A & B normally move together, now diverging)
- [ ] Build "System Health Score" — single 0-100 number from all tag anomaly scores
- [ ] Display system health score prominently in HMI header

**Deliverable**: "System-level anomaly detected" warning before individual tags breach limits

---

## 9. HMI Changes Required

### Notification Bell (Top Nav Bar)
```
🔔 [3]  ← badge count of active warnings
```
- Clicking opens warning panel
- Each warning shows: Tag, Level, Message, Time, Predicted value
- Acknowledge button per warning

### Trend Chart Enhancement
```
─────────────────────────────────────
  Current Value: 87.3 KPA
  Predicted (10 min): 94.1 KPA  ⚠️
  Normal Range: 70 - 90 KPA
─────────────────────────────────────
  [Actual ───]  [Predicted - - -]  [Normal Range ░░░]
```

### New Dashboard Widget: "System Health Score"
```
┌─────────────────────────┐
│  System Health Score    │
│         78/100          │
│  ████████░░  GOOD       │
│  2 tags need attention  │
└─────────────────────────┘
```

---

## 10. MQTT Topics for Predictions

```
pews/alerts/{tag_id}          ← Individual tag warning
pews/predictions/{tag_id}     ← Predicted values
pews/system/health            ← Overall system health score
pews/system/summary           ← Count of active warnings per level
```

---

## 11. Technology Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Statistical engine | Python + NumPy/Pandas | Fast, no GPU needed |
| ARIMA forecasting | `statsmodels` | Proven time-series library |
| Anomaly detection | `scikit-learn` (Isolation Forest) | No labels needed |
| Deep learning | `tensorflow` + `keras` (LSTM) | Best accuracy |
| Trend forecasting | `prophet` (Meta) | Handles seasonality automatically |
| API service | FastAPI (port 7001) | Async, fast |
| Notifications | MQTT + SocketIO | Real-time push |
| Model storage | `.pkl` (sklearn) + `.h5` (keras) | Lightweight, reloadable |

---

## 12. Requirements to Install

```bash
pip install pandas numpy scipy statsmodels scikit-learn
pip install tensorflow prophet
pip install fastapi uvicorn paho-mqtt psycopg2-binary
pip install joblib    # model persistence
```

---

## 13. Quick Start — Phase 1 Only (Fastest Path to Working Alerts)

To get working alerts in 1 week without ML:

1. Create DB schema (1 hour)
2. Build statistical engine — Z-score + RoC (1 day)
3. Wire MQTT notifications (half day)
4. Add bell icon to HMI (half day)
5. **Done** — live early warnings running

ML phases can be added incrementally without disrupting Phase 1.

---

## 14. Key Configuration Per Tag

Each tag will have:
```json
{
  "tag_id": "CV1101",
  "detection_enabled": true,
  "zscore_threshold": 3.0,
  "roc_threshold_per_sec": 2.5,
  "prediction_horizon_min": 10,
  "warning_cooldown_sec": 300,
  "models": ["statistical", "arima", "isolation_forest"]
}
```

---

## 15. Summary Timeline

| Week | Deliverable |
|------|------------|
| Week 1-2 | Statistical alerts live in HMI (Z-score, RoC) |
| Week 2-3 | Adaptive baselines from real data |
| Week 3-4 | ARIMA 10-minute ahead predictions |
| Week 4-5 | Isolation Forest anomaly detection |
| Week 5-7 | LSTM deep learning predictions |
| Week 7-8 | Multi-tag correlation + System Health Score |

**End result**: A fully AI-powered early warning system that predicts problems 5-15 minutes before they happen, using your own historical data as the training source.

---

## 16. Storage Strategy — "Save Only Anomalies"

### Core Principle
Detection runs **entirely in memory**. Nothing is written to the database unless an anomaly is confirmed. On a normal healthy day, the predictive engine writes almost **zero new rows**.

### What We Save vs What We Don't

#### ✅ SAVE (Small, High Value)
| Data | When Saved | Est. Size/Day |
|------|-----------|---------------|
| **Early Warnings fired** | Only when anomaly detected (rare) | ~5 KB |
| **Tag Baselines** (mean/std/min/max per tag) | Recomputed once nightly, 149 rows overwritten | ~50 KB total |
| **Trained ML models** | Retrained weekly, saved as `.pkl` / `.h5` files on disk | ~50 MB total |
| **Predictions** | Only saved when a warning is triggered, not every cycle | ~10 KB/day |

#### ❌ DO NOT SAVE (Avoids Storage Bloat)
| Data | Why Skip |
|------|----------|
| Every prediction every 60 sec for all 149 tags | = 149 × 1440 = **215,000 rows/day** — too much |
| Raw Z-score / RoC scores per tag | Computed in memory, discarded if normal |
| LSTM inference output every cycle | Only persisted if score crosses threshold |

---

### Detection Loop — In-Memory Flow

```
Every 60 seconds:
  ┌─────────────────────────────────────────┐
  │  Read last 10 min from historian_timeseries  │  ← Already in DB
  │  (149 tags × 600 rows = 89,400 rows)    │
  └────────────────┬────────────────────────┘
                   ↓  (all processing IN MEMORY)
  ┌─────────────────────────────────────────┐
  │  Run Z-Score + RoC + IQR + ML models   │
  └────────────────┬────────────────────────┘
                   ↓
         Score < threshold?
         ┌────────┴────────┐
        YES               NO
         ↓                 ↓
      DISCARD          SAVE 1 row
   (nothing written)  to early_warnings
                       + MQTT publish
                       + HMI notification
```

---

### Storage Estimate — Full Year

| Table | Rows/Year | Size/Year |
|-------|-----------|-----------|
| `historian_analytics.early_warnings` | ~10,000 (avg 27/day) | **~5 MB** |
| `historian_analytics.tag_predictions` | ~3,650 (1 per warning event) | **~2 MB** |
| `historian_analytics.tag_baselines` | 149 rows (overwritten nightly) | **< 1 MB** |
| ML model files on disk | 149 models | **~50 MB** |
| **Total new storage added** | | **~58 MB/year** |

> Compare: existing `historian_timeseries` grows **~500 MB/month**.  
> The entire predictive engine adds less than **1 day of historian data per year**.

---

### Retention Policy for Warnings

```sql
-- Auto-delete acknowledged warnings older than 90 days
-- (run as a nightly scheduled job)
DELETE FROM historian_analytics.early_warnings
WHERE acknowledged = TRUE
  AND time < NOW() - INTERVAL '90 days';

-- Keep unacknowledged warnings forever (operator must review)
-- Keep ALL warnings from last 30 days regardless of ack status
```

---

### Why This Approach Is Best for This System

| Concern | Solution |
|---------|----------|
| **Storage constraint** | Detection in memory, only anomalies persisted |
| **DB performance** | Reads are time-bounded (last 10 min), use existing hypertable index |
| **Historical review** | All warnings saved with timestamp, tag, value, type |
| **Auditability** | Acknowledged warnings tracked with who and when |
| **Model retraining** | Uses existing `historian_timeseries` — no duplicate data |
| **Scaling to 500 tags** | Same approach works, still minimal storage |

---

*Document created: May 21, 2026*

---

## IMPLEMENTATION STATUS (Phase 1 Complete)

### Complete File Inventory

| File | Status | Notes |
|------|--------|-------|
| `WEB_HMI_MFA/HMI/pews_schema.sql` | ✅ Created | Run once to create `historian_analytics` schema |
| `WEB_HMI_MFA/predictive_engine/config.py` | ✅ Created | DB/MQTT settings, detection thresholds, level constants |
| `WEB_HMI_MFA/predictive_engine/data/__init__.py` | ✅ Created | Empty init |
| `WEB_HMI_MFA/predictive_engine/data/db_pool.py` | ✅ Created | `SimpleConnectionPool(1,5)`, `PooledConn` context manager |
| `WEB_HMI_MFA/predictive_engine/data/db_reader.py` | ✅ Created | `get_tag_window`, `get_all_active_tag_ids`, `get_all_baselines` |
| `WEB_HMI_MFA/predictive_engine/data/db_writer.py` | ✅ Created | `save_warning`, `upsert_baseline`, `acknowledge_warning` |
| `WEB_HMI_MFA/predictive_engine/data/db_timeseries_reader.py` | ✅ Fixed | Path bug fixed; pivots `historian_timeseries` to wide DataFrame |
| `WEB_HMI_MFA/predictive_engine/engines/__init__.py` | ✅ Created | Empty init |
| `WEB_HMI_MFA/predictive_engine/engines/statistical_engine.py` | ✅ Created | Z-score, IQR, ROC anomaly detection |
| `WEB_HMI_MFA/predictive_engine/engines/baseline_engine.py` | ✅ Created | Nightly baseline compute per tag |
| `WEB_HMI_MFA/predictive_engine/notification/__init__.py` | ✅ Created | Empty init |
| `WEB_HMI_MFA/predictive_engine/notification/mqtt_publisher.py` | ✅ Pre-existed | Isolated `pews/alerts/` + `pews/system/health` topics |
| `WEB_HMI_MFA/predictive_engine/scheduler.py` | ✅ Created | APScheduler 60s detection + 02:00 nightly baselines |
| `WEB_HMI_MFA/predictive_engine/app.py` | ✅ Created | FastAPI port 7001, lifespan start/stop |
| `WEB_HMI_MFA/HMI/controllers/pews_controller.py` | ✅ Created | `Blueprint("pews")` — warnings CRUD + ack |
| `WEB_HMI_MFA/HMI/controllers/bi_controller.py` | ✅ Pre-existed | `Blueprint("bi")` — BI orchestrator via PostgreSQL |
| `WEB_HMI_MFA/HMI/app.py` | ✅ Modified | `pews_bp` + `bi_bp` registered |
| `apex-hmi/src/pages/Analytics.tsx` | ✅ Created | Two-tab page: PEWS + BI Analytics |
| `apex-hmi/src/components/pews/HealthScore.tsx` | ✅ Created | SVG circular gauge, colour-coded |
| `apex-hmi/src/components/pews/WarningPanel.tsx` | ✅ Created | Scrollable warning list with ACK button |
| `apex-hmi/src/components/pews/StatusSummary.tsx` | ✅ Created | Baseline coverage + per-level warning cards |
| `apex-hmi/src/components/pews/BiPanel.tsx` | ✅ Created | BI engine UI: tag picker, date range, results |
| `apex-hmi/src/App.tsx` | ✅ Modified | `/analytics` route added inside `<ProtectedRoute>` |

---

## Connection Pool Design

### Why `SimpleConnectionPool` (Not Raw Connect)

| Concern | Raw `psycopg2.connect()` | Pool (`SimpleConnectionPool`) |
|---------|--------------------------|-------------------------------|
| Connection overhead | New TCP handshake every call | Reuses existing connections |
| Concurrency | Potential exhaustion under load | Bounded (max=5), wait or error |
| Error resilience | Leaked connections on exceptions | `PooledConn.__exit__` always returns |
| Commit safety | Manual `conn.commit()` risk | Auto-commit on clean exit, rollback on exception |

### `PooledConn` Contract

```python
with PooledConn() as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    # __exit__ on success → conn.commit(), putconn()
    # __exit__ on exception → conn.rollback(), putconn()
```

**Rules enforced:**
- `autocommit=False` always set on borrow (pool may have leftover state)
- No manual `conn.commit()` anywhere in `db_writer.py` — pool handles it
- `db_writer.py`, `db_reader.py`, `db_timeseries_reader.py` all use `PooledConn`
- Flask controllers use `container.get_db_connection()` (Flask-side pool, same principle)
- One-off diagnostic scripts (`check_*.py`) may use raw connect — **acceptable for scripts only**

---

## MQTT Isolation Decision

The `mqtt_publisher.py` uses **`paho.mqtt.publish.single()`** — a fire-and-forget function that:
- Opens a new MQTT connection per call
- Publishes one message, then disconnects
- Never holds a persistent MQTT session
- Never interferes with the industrial OPC→MQTT bridge

Topics are completely separate:
- Industrial layer: `opc/data/…` (managed by C# OPC backend)
- PEWS layer: `pews/alerts/{tag_id}`, `pews/system/health`

**Decision: Do not change mqtt_publisher.py.** The current design is correct and safe.

---

## BI Module Integration

The BI module (`HistoricalTrends/bi_engines/`) contains 8 production-grade engines:

| Engine | Purpose |
|--------|---------|
| `baseline_engine` | Statistical baselines per tag |
| `efficiency_engine` | Performance vs rated capacity |
| `delta_engine` | Rate-of-change trend analysis |
| `availability_engine` | Uptime/downtime detection |
| `influence_engine` | Cross-tag correlation |
| `stability_engine` | Variance and oscillation |
| `condition_engine` | Equipment health scoring |
| `loss_engine` | Production loss quantification |

**Integration approach:**
1. `bi_controller.py` (Flask Blueprint) adds `HistoricalTrends/` to `sys.path`
2. `MasterBIOrchestrator` instantiated lazily per Flask worker
3. Data sourced from **PostgreSQL** via `db_timeseries_reader.get_timeseries_df()` — wide pivoted DataFrame
4. Engines never modified — they accept any wide DataFrame
5. `BiPanel.tsx` in React sends `POST /api/bi/analysis` with tag list + date range

**Replacing Parquet with PostgreSQL:**
- Old path: BI engines read `.parquet` files from `D:\OpcLogs\Data\`
- New path: `db_timeseries_reader.py` queries `historian_raw.historian_timeseries`, resamples, pivots to wide DataFrame
- Result: same DataFrame shape the engines expect, zero engine code changes

---

## Startup Sequence

### Prerequisites (run once)

```sql
-- 1. Create PEWS schema (run as cereveate user)
psql -U cereveate -d Automation_DB -f WEB_HMI_MFA/HMI/pews_schema.sql
```

```bash
# 2. Install Python deps in project venv
.venv\Scripts\pip install apscheduler fastapi uvicorn[standard] paho-mqtt
```

### Service Start Order

```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"

# 1. PEWS FastAPI engine (port 7001)
Start-Process python -ArgumentList "-m uvicorn app:app --host 0.0.0.0 --port 7001" `
    -WorkingDirectory "$ROOT\WEB_HMI_MFA\predictive_engine" -WindowStyle Minimized

# 2. Flask HMI backend (port 6001) — restart to pick up new blueprints
$p = (netstat -ano | Select-String ":6001.*LISTENING") -replace '.*\s+(\d+)$','$1'
Stop-Process -Id ([int]$p.Trim()) -Force -ErrorAction SilentlyContinue
Start-Sleep 2
Start-Process python -ArgumentList "app.py" `
    -WorkingDirectory "$ROOT\WEB_HMI_MFA\HMI" -WindowStyle Minimized

# 3. React Vite HMI (port 8090) — already running, HMR picks up changes
# If not running:
Start-Process cmd -ArgumentList "/c npm run dev" `
    -WorkingDirectory "$ROOT\WEB_HMI_MFA\HMI\apex-hmi" -WindowStyle Minimized
```

### Verification

```powershell
# PEWS engine health
Invoke-RestMethod "http://localhost:7001/health"
# Expected: {"status":"ok","scheduler":"running"}

# PEWS status via Flask
Invoke-RestMethod "http://localhost:6001/api/pews/status" `
    -Headers @{"Authorization"="Bearer <token>"}
# Expected: {baseline_count, oldest_baseline, newest_baseline, warning_summary}

# BI tags available
Invoke-RestMethod "http://localhost:6001/api/bi/tags" `
    -Headers @{"Authorization"="Bearer <token>"}
# Expected: [{tag_id, first_seen, last_seen, record_count}, ...]
```

### Login
- URL: `http://localhost:8090`
- Navigate to `/analytics`
- Tab 1: **⚠ Early Warnings** — live health score, warning list, ack buttons
- Tab 2: **📊 BI Analytics** — tag picker, date range, run analysis

---

## Architecture Summary

```
historian_raw.historian_timeseries (TimescaleDB)
        │
        ├──► HistorianIngestHostedService (C# — UNCHANGED)
        │
        ├──► PEWS FastAPI (port 7001)
        │     • APScheduler: detection every 60s, baselines nightly 02:00
        │     • db_reader.py → get_tag_window() (10-min window per tag)
        │     • statistical_engine.py → z-score / IQR / ROC
        │     • baseline_engine.py → nightly upsert to tag_baselines
        │     • db_writer.py → save_warning() to early_warnings
        │     • mqtt_publisher.py → pews/alerts/{tag_id} (isolated)
        │
        └──► Flask HMI (port 6001)
              • pews_controller.py → /api/pews/* (warnings, ack, status)
              • bi_controller.py → /api/bi/* (tags, trends, analysis, baselines)
              • db_timeseries_reader.py → pivot wide DataFrame
              • MasterBIOrchestrator → 8 BI engines (UNCHANGED)

React Vite (port 8090) → /analytics
  Tab 1: HealthScore + WarningPanel + StatusSummary (polls /api/pews/*)
  Tab 2: BiPanel (posts to /api/bi/analysis)
```

---

*Last updated: May 21, 2026 — Phase 1 implementation complete*

*Platform: Cereveate OPC DA Analytics Platform*  
*Tags in service: 149 (128 PLC + 21 OPC)*
