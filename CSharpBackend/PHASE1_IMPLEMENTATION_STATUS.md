# Phase 1 Alarm System — Implementation Status

**Date**: 2026-05-08  
**Branch**: main  
**DB**: Automation_DB @ localhost:5432

---

## What We Are Doing

Implementing Phase 1 of the ISA-18.2 alarm system redesign (v5.1).  
The existing `AlarmEvaluationService` blindly restores all `ACTIVE` DB rows on startup,  
permanently blocking new alarms from being raised. This rewrites the whole alarm engine.

---

## Files Created / Modified

### SQL
| File | Purpose | Status |
|------|---------|--------|
| `phase1_migration.sql` | DB migration script (read-only reference) | ✅ Written |
| `run_migration.py` | Executes migration against Automation_DB | ⏳ Ready to run |
| `check_alarm_tables.py` | Verified existing DB schema before migration | ✅ Used |
| `check_full_schema.py` | Full schema dump — confirmed what exists | ✅ Used |

### C# — Services
| File | Purpose | Status |
|------|---------|--------|
| `Services\AlarmEvaluation\Services\AlarmEvaluationService.cs` | REWRITE — event-driven orchestrator, calls AlarmStateManager | ⏳ Pending |
| `Services\AlarmEvaluation\Services\AlarmStateManager.cs` | NEW — 4-state machine, per-tag SemaphoreSlim lock, sole DB writer | ⏳ Pending |
| `Services\AlarmEvaluation\Services\AlarmReconciliationService.cs` | NEW — startup live-value reconciliation (batched, MQTT suppressed) | ⏳ Pending |
| `Services\AlarmEvaluation\Services\AlarmSuppressionEngine.cs` | NEW — HH suppresses H, LL suppresses L | ⏳ Pending |
| `Services\AlarmEvaluation\Services\AlarmDelayTracker.cs` | NEW — per-tag onset delay timers (anti-spike) | ⏳ Pending |
| `Services\AlarmEvaluation\Services\AlarmSetpointCacheService.cs` | UPDATE — add `alarm_onset_delay_s` field | ⏳ Pending |

### C# — Models
| File | Purpose | Status |
|------|---------|--------|
| `Services\AlarmEvaluation\Models\AlarmRuntimeState.cs` | REWRITE — 4-state enum, occurrence_id, per alarm_key | ⏳ Pending |
| `Services\AlarmEvaluation\Models\AlarmSetpoint.cs` | UPDATE — add `OnsetDelaySeconds` property | ⏳ Pending |
| `Services\AlarmEvaluation\Models\AlarmTransitionEvent.cs` | NEW — typed transition event record | ⏳ Pending |

### C# — Config
| File | Purpose | Status |
|------|---------|--------|
| `Services\AlarmEvaluation\Config\AlarmEvaluationConfig.cs` | UPDATE — clean up unused fields | ⏳ Pending |

### C# — API
| File | Purpose | Status |
|------|---------|--------|
| `Controllers\AlarmsController.cs` | NEW — GET /api/alarms/active, GET /api/alarms/history, POST /api/alarms/{key}/ack | ⏳ Pending |
| `Controllers\AlarmDiagnosticsController.cs` | EXISTS — keep as-is | ✅ No change |

### Design
| File | Purpose | Status |
|------|---------|--------|
| `ALARM_SYSTEM_REDESIGN_PROPOSAL.md` | v5.1 final design document | ✅ Complete |

---

## DB Changes (phase1_migration.sql / run_migration.py)

| Action | Object | Status |
|--------|--------|--------|
| UPDATE alarm_state='CLEARED' | `historian_events` rows 32654, 32655, 32656 | ⏳ Not run |
| ADD COLUMN alarm_level, occurrence_id, instance_seq | `historian_raw.historian_events` | ⏳ Not run |
| CREATE TABLE | `historian_raw.alarm_active` | ⏳ Not run |
| ADD COLUMN alarm_onset_delay_s | `historian_meta.tag_master` | ⏳ Not run |

**NOT touched (confirmed from check_full_schema.py)**:
- `historian_events` CHECK constraint (`ACTIVE/ACKNOWLEDGED/CLEARED/SUPPRESSED`) — untouched
- `alarm_audit_trail` — untouched
- `interlock_state_tracking` — untouched
- `trip_event_tracking` — untouched
- All existing views — untouched

---

## Next Step

Run `run_migration.py` first, then implement C# files in order:
1. `AlarmRuntimeState.cs`
2. `AlarmTransitionEvent.cs`
3. `AlarmStateManager.cs`
4. `AlarmReconciliationService.cs`
5. `AlarmSuppressionEngine.cs`
6. `AlarmDelayTracker.cs`
7. `AlarmEvaluationService.cs` (rewrite)
8. `AlarmsController.cs`
9. Register new services in `Program.cs`
10. Build and test via `GET /api/alarm-diagnostics`
