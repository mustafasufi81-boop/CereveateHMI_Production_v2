# BI Versioned Model Weights & Incremental Learning

**Implemented:** May 23, 2026  
**File:** `WEB_HMI_MFA/HMI/controllers/bi_controller.py`  
**DB Table:** `historian_analytics.bi_model_versions`

---

## What Was Changed

The flat single-row-per-model persistence (`bi_model_params`) has been replaced with a
**fully versioned, performance-gated** system.  Every training run creates a new version row.
A version is only promoted to `is_active = TRUE` when it is **provably better** than the
currently deployed version.  Old weights are never immediately deleted.

---

## Database Schema

```sql
CREATE TABLE historian_analytics.bi_model_versions (
    id              SERIAL          PRIMARY KEY,
    tag_id          TEXT            NOT NULL,
    model_name      TEXT            NOT NULL,   -- 'ARIMA', 'HW', 'LR', '_meta'
    version         INTEGER         NOT NULL,   -- auto-increments per tag+model
    params_json     JSONB           NOT NULL,   -- serialised model coefficients
    n_train_points  INTEGER         NOT NULL DEFAULT 0,
    n_days_trained  NUMERIC(6,2)    NOT NULL DEFAULT 0,
    mae             NUMERIC(14,8),              -- holdout MAE (20-point window)
    rmse            NUMERIC(14,8),              -- holdout RMSE
    aic             NUMERIC(14,4),              -- ARIMA/HW AIC (where available)
    is_active       BOOLEAN         NOT NULL DEFAULT FALSE,  -- currently deployed?
    promoted_at     TIMESTAMPTZ,               -- when this version became active
    trained_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    retire_after    TIMESTAMPTZ,               -- NULL = keep; set on de-activation
    notes           TEXT
);
-- Enforces at most ONE active version per tag+model
CREATE UNIQUE INDEX bi_model_versions_active_uidx
    ON historian_analytics.bi_model_versions(tag_id, model_name)
    WHERE is_active = TRUE;
```

---

## Promotion Rules

| Constant | Value | Meaning |
|---|---|---|
| `PROMOTION_THRESHOLD` | `0.05` | New model must have MAE **≥ 5% lower** than current active |
| `MAX_VERSIONS_KEPT` | `3` | Max non-active versions kept as safety backup |
| `VERSION_RETIRE_DAYS` | `14` | Non-active versions expire and are pruned after 14 days |

### Decision Logic (`_maybe_promote_model`)

```
Is there an active version?
  NO  → promote immediately (first-ever version for this tag+model)
  YES → compare MAE:
          new_mae < current_active_mae × 0.95  → PROMOTE
          new_mae ≥ current_active_mae × 0.95  → STAGE (store but do not activate)
          new_mae == inf (eval failed)          → NEVER PROMOTE
```

On promotion:
1. Old active version `is_active` set to `FALSE`, `retire_after = NOW() + 14 days`
2. New version inserted with `is_active = TRUE`, `promoted_at = NOW()`
3. Excess non-active versions pruned (keep newest `MAX_VERSIONS_KEPT`)

---

## Two-Speed Learning Scheduler

The background daemon thread runs forever with two operating modes:

### QUICK cycle — every 1 hour
- Fetches **only new data** since `last_trained_at` for each tag
- Appends to existing `y_long` in memory
- Refits all three models (ARIMA, HW, LR)
- **Skips holdout MAE evaluation** — fast, lightweight
- Does **NOT** call `_maybe_promote_model` — in-memory models updated only
- Purpose: keep predictions fresh with latest process data

### DEEP cycle — every 6 hours
- Rebuilds training series **incrementally day-by-day** (7 days total)
  ```
  Day 7 → fit
  Day 6 → append + fit
  ...
  Day 1 → append + final fit
  ```
  0.5 s pause between day-chunks (prevents DB hammering)
- Runs **holdout MAE** evaluation on 20-point window after each full fit
- Calls `_maybe_promote_model()` — version promoted only if MAE improves ≥ 5%
- Prunes expired non-active versions (`_prune_expired_versions`)

### Per-tag pause
```
TAG_TRAIN_PAUSE_S = 3 seconds
```
Tags are processed **one at a time** with a 3-second pause between each.  
With 100 tags this means one full DEEP cycle takes ~100 × (7 × 0.5s + fit time + 3s) 
≈ 10–15 minutes — Flask request handling is **never blocked**.

---

## Why Training Cannot Hang the System

| Risk | Mitigation |
|---|---|
| All tags trained simultaneously | ❌ Not possible — one tag at a time, `TAG_TRAIN_PAUSE_S = 3s` between each |
| Heavy ARIMA fit blocking requests | ❌ Not possible — all training runs in a **daemon thread** separate from Flask worker threads |
| DB flooded by many queries | ❌ Not possible — day-chunk loop has `0.5s` sleep + per-tag `3s` pause |
| Bad model silently replaces good one | ❌ Not possible — promotion gated by 5% MAE improvement; old weights kept 14 days |
| Crash deletes only good model | ❌ Not possible — multiple non-active versions kept as fallback |

---

## Key Functions

| Function | Purpose |
|---|---|
| `_ensure_model_versions_table()` | Creates `bi_model_versions` table on Flask startup |
| `_get_holdout_mae(y, forecast_fn, n)` | Evaluates model quality: fit on `y[:-n]`, forecast `n` steps, return MAE |
| `_maybe_promote_model(...)` | Insert new version; promote only if MAE improves ≥ 5% |
| `_prune_expired_versions()` | Delete non-active rows where `retire_after < NOW()` |
| `_get_active_params(tag_id, model_name)` | Fetch currently deployed version for a tag+model |
| `_load_all_active_params()` | Startup: load all promoted versions into `_model_cache` |
| `_fit_one_tag_incremental(...)` | Fit ARIMA/HW/LR for one tag; conditionally evaluate + promote |
| `_background_retrain_all()` | Main scheduler loop (daemon thread) |

---

## Status Endpoint

```http
GET /api/bi/learning/status?tag_id=<optional>
Authorization: Bearer <token>
```

Response includes:
- `quick_update_h` — quick cycle frequency (1h)
- `deep_retrain_h` — deep cycle frequency (6h)
- `promotion_threshold_pct` — 5%
- `max_versions_kept` — 3
- `version_retire_days` — 14
- `tags_with_active_model` — count of tags with a promoted active version
- `total_versions_in_db` — all version rows (active + staged + retired)
- `active_versions` — array of currently deployed versions with MAE/RMSE/AIC
- `all_versions` — full version history
- `memory_cache` — per-tag in-memory status (`n_train_points`, `n_days`, `last_trained_at`)

---

## Configuration (all in `bi_controller.py` constants — no hardcoding)

```python
PROMOTION_THRESHOLD  = 0.05   # 5% MAE improvement required to promote
MAX_VERSIONS_KEPT    = 3      # backup versions per tag+model
VERSION_RETIRE_DAYS  = 14     # days before non-active version is pruned
QUICK_UPDATE_HOURS   = 1      # quick append-only cycle frequency
RETRAIN_INTERVAL_HOURS = 6    # deep full-retrain cycle frequency
TAG_TRAIN_PAUSE_S    = 3      # sleep between tags (prevents CPU/DB hammering)
INCREMENTAL_CHUNK_DAYS = 1    # one day loaded at a time in deep cycle
HOLDOUT_N            = 20     # points held back for MAE evaluation
MAX_TRAIN_DAYS       = 7      # maximum historical window
MAX_TRAIN_POINTS     = 5000   # cap on resampled training points
```

All DB credentials come from `container.config['database']` — **zero hardcoded values**.
