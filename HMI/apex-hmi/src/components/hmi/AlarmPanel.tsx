import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { AlertTriangle, Bell, Clock, XCircle, AlertCircle, CheckCircle, FileText, History, HelpCircle, Search, X, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/auth-context";
import { usePermission } from "@/hooks/usePermission";
import { mqttWebSocketService } from "@/services/mqtt-websocket";
import AlarmHistoryModal from "./AlarmHistoryModal";

interface Alarm {
  id: number;
  alarm_key?: string;   // stable card identity: tag_id + level (never changes across oscillations)
  tag_name: string;
  tag_id: string;
  event_type: string;
  alarm_state: "ACTIVE_UNACK" | "ACTIVE_ACK" | "RTN_UNACK" | "CLEARED" | "SUPPRESSED" | null;
  alarm_priority: number; // 1=Low, 2=Med, 3=High, 4=Urgent, 5=Critical
  alarm_level?: string;   // H / HH / L / LL — which limit was crossed (NOT priority)
  severity: "CRITICAL" | "HIGH" | "URGENT" | "WARNING" | "LOW";
  occurrence_count?: number; // How many times this limit has fired since card was raised
  instance_seq?: number;
  message: string;
  alarm_setpoint?: number;
  alarm_actual_value?: number;
  acknowledged_by?: string;
  acknowledged_at?: string;
  cleared_at?: string;
  cleared_by?: string;
  clear_reason?: string;
  clear_notes?: string;
  last_cleared_at?: string;   // last time this alarm key was ever cleared (from audit trail)
  last_cleared_by?: string;   // operator who last cleared it
  recent_raise_times?: string[]; // last ≤3 ALARM_RAISED timestamps, newest first
  raised_at: string;
  duration_minutes: number;
  status: "ONGOING" | "CLEARED";
}

interface SuppressedAlarm {
  audit_id: number;
  event_id: number;
  tag_id: string;
  tag_name: string;
  alarm_key: string;
  alarm_level: string;
  suppressed_by: string;
  suppressed_at: string;
  suppress_until: string | null; // always set — indefinite not permitted
  duration_hours: number | null;
  reason: string;
  notes: string;
}

interface AuditRecord {
  audit_id: number;
  event_id: number;
  tag_id: string;
  tag_name: string;
  tag_description?: string;
  plant?: string;
  area?: string;
  equipment?: string;
  event_type: string;
  action_type: string;
  action_timestamp: string;
  performed_by: string;
  previous_state: string | null;
  new_state: string;
  alarm_priority: number;
  priority_label: string;
  alarm_actual_value?: number;
  alarm_setpoint?: number;
  action_reason?: string;
  action_notes?: string;
  minutes_since_previous_action?: number;
  response_time_seconds?: number;
}

interface AlarmPanelProps {
  className?: string;
}

const AUDIT_ACTION_ORDER: Record<string, number> = {
  RAISED: 1,
  ACKNOWLEDGED: 2,
  CLEARED: 3,
  SUPPRESSED: 4,
};

const sortAuditRecordsByTimeAndAction = (records: AuditRecord[]): AuditRecord[] => {
  return [...records].sort((a, b) => {
    const ao = AUDIT_ACTION_ORDER[a.action_type] ?? 99;
    const bo = AUDIT_ACTION_ORDER[b.action_type] ?? 99;
    if (ao !== bo) return ao - bo;

    const ta = a.action_timestamp ? new Date(a.action_timestamp).getTime() : 0;
    const tb = b.action_timestamp ? new Date(b.action_timestamp).getTime() : 0;
    if (ta !== tb) return ta - tb;

    return 0;
  });
};

export const AlarmPanel = ({ className }: AlarmPanelProps) => {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [isExpanded, setIsExpanded] = useState(true);
  const [loading, setLoading] = useState(true);
  // Per-alarm in-flight tracking — replaces single `acknowledging` id.
  // Multiple alarms can now show spinners simultaneously (e.g. ACK ALL).
  const [pendingOps, setPendingOps] = useState<Set<number>>(new Set());
  const addPending    = useCallback((id: number) => setPendingOps(prev => { const s = new Set(prev); s.add(id);    return s; }), []);
  const removePending = useCallback((id: number) => setPendingOps(prev => { const s = new Set(prev); s.delete(id); return s; }), []);
  const isPending     = (id: number) => pendingOps.has(id);

  // Polling overlap guard — skip poll cycle if previous fetch still running
  const pollingInProgress = useRef(false);
  // Starvation fix: track when polling lock was acquired; force-reset if stuck >15s
  const pollingStartedAt = useRef<number | null>(null);
  // Debounce ref — coalesce multiple post-ACK refreshes into one
  const refreshDebounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Circuit breaker: track consecutive fetch failures
  const consecutiveFailures = useRef(0);
  const [isDegraded, setIsDegraded] = useState(false);
  // Timer refs for opMessages — cleaned up on unmount (fix: no leaking setTimeouts)
  const opMessageTimers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  // ACK ALL: selected alarm ids (max 10 at a time)
  const [selectedForAck, setSelectedForAck] = useState<Set<number>>(new Set());
  const ACK_SELECTION_LIMIT = 10;
  // ACK ALL confirmation modal
  const [showAckAllConfirm, setShowAckAllConfirm] = useState(false);
  // Inline per-alarm op messages (replaces alert())
  const [opMessages, setOpMessages] = useState<Map<number, { text: string; type: 'info' | 'warn' | 'err' }>>(new Map());
  const showOpMessage = useCallback((id: number, text: string, type: 'info' | 'warn' | 'err' = 'info') => {
    // Cancel any existing timer for this alarm id (prevents duplicate messages)
    const existing = opMessageTimers.current.get(id);
    if (existing) clearTimeout(existing);
    setOpMessages(prev => { const m = new Map(prev); m.set(id, { text, type }); return m; });
    const t = setTimeout(() => {
      setOpMessages(prev => { const m = new Map(prev); m.delete(id); return m; });
      opMessageTimers.current.delete(id);
    }, 4_000);
    opMessageTimers.current.set(id, t);
  }, []);

  const [clearingAlarmId, setClearingAlarmId] = useState<number | null>(null);
  const [clearReason, setClearReason] = useState("");
  const [clearNotes, setClearNotes] = useState("");
  const [auditTrailAlarmId, setAuditTrailAlarmId] = useState<number | null>(null);
  const [auditRecords, setAuditRecords] = useState<AuditRecord[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [showClearedAlarms, setShowClearedAlarms] = useState(false);
  const [searchTag, setSearchTag] = useState("");
  const [showHelp, setShowHelp] = useState<number | null>(null);
  const [, setTick] = useState(0); // 1-min tick to refresh live elapsed times
  // Suppression state
  const [suppressModalAlarm, setSuppressModalAlarm] = useState<Alarm | null>(null);
  const [suppressReason, setSuppressReason] = useState('');
  const [suppressDuration, setSuppressDuration] = useState<number>(1);
  const [suppressNotes, setSuppressNotes] = useState('');
  const [suppressing, setSuppressing] = useState<number | null>(null);
  const [suppressedAlarms, setSuppressedAlarms] = useState<SuppressedAlarm[]>([]);
  const [showSuppressed, setShowSuppressed] = useState(false);

  // ── Metrics ─────────────────────────────────────────────────────────────
  // lastSyncAt: epoch ms of last successful fetchSnapshot completion
  const lastSyncAt = useRef<number | null>(null);
  // syncLatencyMs: how long the last fetchSnapshot took (ms)
  const [syncLatencyMs, setSyncLatencyMs] = useState<number | null>(null);
  // syncTick: drives the 'X s ago' counter — stored as a ref so the 1-second
  // tick does NOT re-render the full component (only the metrics bar needs it).
  // We piggyback on a lightweight state only used in the metrics IIFE.
  const [metricsSeq, setMetricsSeq] = useState(0); // increments 1/s for metrics bar only
  const { user } = useAuth();
  const canOperateAlarms = usePermission('alarms', 'canOperate');

  // 60-second tick: refreshes live elapsed durations on alarm cards (e.g. "+4m")
  // 1-second tick: updates metrics bar 'X s ago' — only triggers a metrics re-render
  useEffect(() => {
    const timer     = setInterval(() => setTick(t => t + 1), 60_000);
    const metricsTmr = setInterval(() => setMetricsSeq(s => s + 1), 1_000);
    return () => { clearInterval(timer); clearInterval(metricsTmr); };
  }, []);

  // Cleanup: clear all pending opMessage timers on unmount (prevents setState after unmount)
  useEffect(() => {
    return () => {
      opMessageTimers.current.forEach(t => clearTimeout(t));
      opMessageTimers.current.clear();
      if (refreshDebounceTimer.current) clearTimeout(refreshDebounceTimer.current);
    };
  }, []);

  // Stable ref always pointing to the latest fetchSnapshot implementation.
  // Consumers (scheduleRefresh, setInterval) call this ref so they are NEVER
  // stale-closed over an old isDegraded / consecutiveFailures value.
  const fetchSnapshotRef = useRef<(force?: boolean) => Promise<void>>(async () => {});

  const isTemporaryMqttAlarm = (alarm: Alarm) => alarm.id >= 1000000000000;

  const sortByPriorityAndTime = (alarmList: Alarm[]) => {
    return [...alarmList].sort((a, b) => {
      const priorityDiff = (b.alarm_priority || 0) - (a.alarm_priority || 0);
      if (priorityDiff !== 0) return priorityDiff;
      return new Date(b.raised_at).getTime() - new Date(a.raised_at).getTime();
    });
  };

  const mergeDbWithTemporaryMqtt = (existing: Alarm[], dbAlarms: Alarm[]) => {
    const temporaryLiveAlarms = existing.filter(isTemporaryMqttAlarm);

    // Key on alarm_key (tag_id + level) — this is the stable card identity.
    // current_event_id (alarm.id) changes on every oscillation hit, so it
    // cannot be used as the freeze key.
    const existingDbByKey = new Map(
      existing
        .filter(a => !isTemporaryMqttAlarm(a))
        .map(a => [(a as any).alarm_key ?? `${a.tag_id}_${a.alarm_level ?? ''}`, a])
    );

    const merged = dbAlarms.map(dbAlarm => {
      const stableKey = (dbAlarm as any).alarm_key ?? `${dbAlarm.tag_id}_${dbAlarm.alarm_level ?? ''}`;
      const prev = existingDbByKey.get(stableKey);
      if (prev) {
        // Freeze the first-hit timestamp and PV@Trip value — never overwrite once set
        return {
          ...dbAlarm,
          raised_at:          prev.raised_at,
          alarm_actual_value: prev.alarm_actual_value ?? dbAlarm.alarm_actual_value,
        };
      }
      return dbAlarm;
    });

    for (const tempAlarm of temporaryLiveAlarms) {
      const hasDbEquivalent = dbAlarms.some(
        dbAlarm =>
          dbAlarm.tag_id === tempAlarm.tag_id &&
          dbAlarm.event_type === tempAlarm.event_type &&
          (dbAlarm.alarm_state === 'ACTIVE_UNACK' || dbAlarm.alarm_state === 'RTN_UNACK' || dbAlarm.alarm_state === null)
      );

      if (!hasDbEquivalent) {
        merged.push(tempAlarm);
      }
    }

    return sortByPriorityAndTime(merged);
  };

  // ── Issue 2 fix: REST snapshot on mount + on reconnect ──────────────────
  // Socket.IO / MQTT handles live *deltas* only (new transitions).
  // REST provides the authoritative snapshot so reconnects never miss state.
  const fetchSnapshot = async (forceHardReload = false) => {
    // Starvation fix: if polling lock has been held >15s, force-reset it
    const MAX_POLL_TIME = 15_000;
    if (pollingInProgress.current) {
      const heldMs = pollingStartedAt.current ? Date.now() - pollingStartedAt.current : 0;
      if (!forceHardReload && heldMs < MAX_POLL_TIME) return; // still within allowed window
      console.warn(`[AlarmPanel] Polling lock stale for ${heldMs}ms — force-resetting`);
      pollingInProgress.current = false; // force-release stale lock
    }
    // Circuit breaker: if backend is repeatedly failing, back off
    if (!forceHardReload && isDegraded && consecutiveFailures.current >= 5) {
      // In degraded mode, only retry every ~30s (every 6th poll cycle at 5s interval)
      // Use syncTick to avoid adding extra state; just check via lastSyncAt
      const msSinceLastAttempt = lastSyncAt.current ? Date.now() - lastSyncAt.current : Infinity;
      if (msSinceLastAttempt < 30_000) return;
    }
    pollingInProgress.current = true;
    pollingStartedAt.current = Date.now();
    const fetchStart = Date.now();
    try {
      const [activeRes, suppRes] = await Promise.all([
        fetch('/api/alarms/active'),
        fetch('/api/alarms/suppressed'),
      ]);
      const data = await activeRes.json();
      if (data.success && Array.isArray(data.alarms)) {
        setAlarms(prev => mergeDbWithTemporaryMqtt(prev, data.alarms));
      }
      const suppData = await suppRes.json();
      if (suppData.success) setSuppressedAlarms(suppData.suppressed || []);
      // Record successful sync metrics + reset circuit breaker
      lastSyncAt.current = Date.now();
      setSyncLatencyMs(Date.now() - fetchStart);
      consecutiveFailures.current = 0;
      if (isDegraded) setIsDegraded(false);
    } catch (err) {
      consecutiveFailures.current += 1;
      console.warn(`Alarm snapshot fetch failed (attempt ${consecutiveFailures.current}):`, err);
      if (consecutiveFailures.current >= 5 && !isDegraded) {
        console.error('[AlarmPanel] Circuit breaker OPEN — 5 consecutive failures. Switching to degraded mode.');
        setIsDegraded(true);
      }
    } finally {
      setLoading(false);
      pollingInProgress.current = false;
      pollingStartedAt.current = null;
    }
  };

  // Always point the ref at the freshest fetchSnapshot (runs every render,
  // which is fine — assignment is O(1) and has no side effects).
  fetchSnapshotRef.current = fetchSnapshot;

  // Debounced refresh — collapses many post-ACK refresh calls (e.g. ACK ALL)
  // into a single fetch 600 ms after the last call.
  const scheduleRefresh = useCallback(() => {
    if (refreshDebounceTimer.current) clearTimeout(refreshDebounceTimer.current);
    refreshDebounceTimer.current = setTimeout(() => {
      refreshDebounceTimer.current = null;
      fetchSnapshotRef.current(); // always calls the latest fetchSnapshot — no stale closure
    }, 600);
  }, []); // stable: no deps needed because we go through the ref

  useEffect(() => {
    fetchSnapshotRef.current(); // initial load
    // Re-fetch every 5 s — always uses latest fetchSnapshot via the ref
    const guard = setInterval(() => fetchSnapshotRef.current(), 5_000);
    return () => clearInterval(guard);
  }, []); // intentionally empty — ref keeps this fresh

  // Real-time alarm updates via WebSocket/SocketIO
  // NOTE: This is for INSTANT display of NEW alarms (<1 second latency)
  // Database polling (above) handles historical/persistent alarms
  // BOTH sources work together for complete ISA-18.2 compliance
  useEffect(() => {
    const handleActiveAlarmsSnapshot = (data: any) => {
      if (data.alarms && data.alarms.length > 0) {
        setAlarms(prevAlarms => mergeDbWithTemporaryMqtt(prevAlarms, data.alarms));
      }
    };
    
    // Issue 2: live MQTT events are *deltas* — apply against current state, never full overwrite.
    // Use transition_seq to discard stale / out-of-order messages.
    const handleRealtimeAlarm = (alarmData: any) => {

      const incomingSeq: number = alarmData.transition_seq ?? 0;
      const incomingState = alarmData.new_state ?? (alarmData.state === 'ACTIVE' ? 'ACTIVE_UNACK' : null);
      const eventType: string  = alarmData.event_type ?? '';

      // CLEARED transition: remove from panel (alarm lifecycle done)
      if (incomingState === 'CLEARED' || eventType === 'ALARM_CLEARED') {
        setAlarms(prev => prev.filter(a => {
          if (!a.tag_id || a.tag_id !== alarmData.tag_id) return true;
          // Keep if our local seq is already higher (we have a newer REST snapshot)
          if (a.alarm_state === 'CLEARED') return false; // already marked
          return false; // remove
        }));
        return;
      }

      const newAlarm: Alarm = {
        id: Date.now(),
        tag_name: alarmData.tagId ?? alarmData.tag_id,
        tag_id: alarmData.tagId ?? alarmData.tag_id,
        event_type: alarmData.event_type || 'ALARM',
        alarm_state: incomingState as Alarm['alarm_state'],
        alarm_priority: alarmData.priority || 3,
        severity: alarmData.priority === 5 ? 'CRITICAL' :
                 alarmData.priority === 4 ? 'URGENT' :
                 alarmData.priority === 3 ? 'HIGH' :
                 alarmData.priority === 2 ? 'WARNING' : 'LOW',
        message: alarmData.message ?? `${alarmData.tagId ?? alarmData.tag_id} alarm`,
        alarm_setpoint: alarmData.setpoint,
        alarm_actual_value: alarmData.value,
        raised_at: alarmData.timestamp,
        duration_minutes: 0,
        status: "ONGOING"
      };

      setAlarms(prevAlarms => {
        const tagId     = newAlarm.tag_id;
        const existing  = prevAlarms.findIndex(a => a.tag_id === tagId && !isTemporaryMqttAlarm(a));

        if (existing >= 0) {
          // DB-backed alarm already present — apply delta only if newer
          const cur = prevAlarms[existing];
          // Stale check: if we have a real DB id and a higher-or-equal seq, keep current
          const curSeq = (cur as any)._transitionSeq ?? 0;
          if (incomingSeq > 0 && incomingSeq <= curSeq) {
            return prevAlarms; // stale
          }
          const updated = [...prevAlarms];
          updated[existing] = { ...cur, alarm_state: newAlarm.alarm_state } as Alarm;
          (updated[existing] as any)._transitionSeq = incomingSeq;
          return sortByPriorityAndTime(updated);
        }

        // No DB alarm yet — add temporary entry
        const tmpIdx = prevAlarms.findIndex(a => a.tag_id === tagId && isTemporaryMqttAlarm(a));
        if (tmpIdx >= 0) {
          const updated = [...prevAlarms];
          updated[tmpIdx] = { ...updated[tmpIdx], alarm_state: newAlarm.alarm_state };
          return sortByPriorityAndTime(updated);
        }
        return sortByPriorityAndTime([newAlarm, ...prevAlarms]);
      });
    };
    
    mqttWebSocketService.on('active_alarms_snapshot', handleActiveAlarmsSnapshot);
    mqttWebSocketService.on('mqtt_alarm', handleRealtimeAlarm);
    return () => {
      mqttWebSocketService.off('active_alarms_snapshot', handleActiveAlarmsSnapshot);
      mqttWebSocketService.off('mqtt_alarm', handleRealtimeAlarm);
    };
  }, []);

  // ISA-18.2: Context-sensitive operator guidance for alarms
  const getAlarmHelp = (alarm: Alarm): { title: string; steps: string[]; safety: string } => {
    const tagType = alarm.tag_name.substring(0, 2); // Extract tag prefix (TT, PT, FT, etc.)
    const priority = alarm.alarm_priority || 1;
    
    // High/Low detection from message
    const isHigh = alarm.message.toLowerCase().includes('high') || alarm.message.toLowerCase().includes('exceeded');
    const isLow = alarm.message.toLowerCase().includes('low');
    
    // Tag-specific guidance (ISA-5.1 standard tag prefixes)
    switch(tagType) {
      case 'TT': // Temperature Transmitter
        return {
          title: isHigh ? "High Temperature Alarm" : "Low Temperature Alarm",
          steps: isHigh ? [
            "1. Check cooling system operation (pumps, fans, coolers)",
            "2. Verify cooling water/air flow rates are normal",
            "3. Check for process upsets or increased load",
            "4. Inspect for insulation damage or steam traps malfunction",
            "5. If critical: Initiate emergency shutdown procedures"
          ] : [
            "1. Check heating system operation (steam, electric heaters)",
            "2. Verify steam/heating supply pressure and flow",
            "3. Check for heat exchanger fouling or valve issues",
            "4. Inspect control valve position and operation",
            "5. Monitor for freeze protection if applicable"
          ],
          safety: priority >= 4 ? "⚠️ CRITICAL: May lead to equipment damage or process upset. Take immediate action." : "Monitor closely. Document actions taken."
        };
      
      case 'PT': // Pressure Transmitter
        return {
          title: isHigh ? "High Pressure Alarm" : "Low Pressure Alarm",
          steps: isHigh ? [
            "1. Check pressure relief valves (PRVs) for proper operation",
            "2. Verify downstream flow paths are not blocked",
            "3. Check control valves for correct positioning",
            "4. Inspect compressor/pump operation if applicable",
            "5. If critical: Initiate pressure relief/vent procedures"
          ] : [
            "1. Check for leaks in piping, flanges, and seals",
            "2. Verify pump/compressor operation and suction conditions",
            "3. Check upstream supply pressure and flow",
            "4. Inspect control valve operation",
            "5. Monitor for cavitation or suction issues"
          ],
          safety: priority >= 4 ? "⚠️ CRITICAL: Pressure excursions can cause rupture or process failure. Immediate action required." : "Monitor pressure trends. Check process stability."
        };
      
      case 'FT': // Flow Transmitter
        return {
          title: isHigh ? "High Flow Alarm" : isLow ? "Low Flow Alarm" : "Flow Alarm",
          steps: isHigh ? [
            "1. Check control valve position (may be fully open)",
            "2. Verify pressure differential is not excessive",
            "3. Check for bypass valve leakage",
            "4. Inspect for pump/compressor overspeed conditions",
            "5. Adjust flow control setpoint if process allows"
          ] : [
            "1. Check for line blockage or fouling",
            "2. Verify pump/compressor operation",
            "3. Check control valve operation and position",
            "4. Inspect strainers and filters for clogging",
            "5. Monitor upstream pressure and supply conditions"
          ],
          safety: priority >= 4 ? "⚠️ CRITICAL: Abnormal flow can affect product quality or equipment protection. Take prompt action." : "Document flow trends. Check process requirements."
        };
      
      case 'LT': // Level Transmitter
        return {
          title: isHigh ? "High Level Alarm" : "Low Level Alarm",
          steps: isHigh ? [
            "1. Check outlet flow/pump operation",
            "2. Verify level control valve operation",
            "3. Inspect for inlet flow surges or control issues",
            "4. Check overflow protection devices",
            "5. If critical: Initiate emergency drain procedures"
          ] : [
            "1. Check inlet flow/feed to vessel",
            "2. Verify outlet flow is not excessive",
            "3. Inspect level control valve operation",
            "4. Check for leaks or drain valve issues",
            "5. Monitor pump suction protection if applicable"
          ],
          safety: priority >= 4 ? "⚠️ CRITICAL: Level excursions can cause overflow, pump damage, or process upset. Act immediately." : "Monitor level trends. Verify control system response."
        };
      
      case 'VT': // Vibration Transmitter
        return {
          title: "High Vibration Alarm",
          steps: [
            "1. IMMEDIATELY reduce load if vibration is severe",
            "2. Check for bearing wear or lubrication issues",
            "3. Inspect for unbalance, misalignment, or looseness",
            "4. Verify coupling and mounting bolt tightness",
            "5. Check for resonance or process-induced vibration",
            "6. If >10 mm/s: Consider emergency shutdown"
          ],
          safety: "⚠️ CRITICAL: High vibration can cause catastrophic bearing or shaft failure. Shutdown if vibration increases rapidly."
        };
      
      case 'CT': // Current Transmitter
      case 'ST': // Speed Transmitter
        return {
          title: isHigh ? "High Motor Load/Speed Alarm" : "Low Motor Load/Speed Alarm",
          steps: isHigh ? [
            "1. Check motor load - may indicate mechanical binding",
            "2. Verify process conditions (pressure, flow, level)",
            "3. Inspect for equipment mechanical issues",
            "4. Check for phase imbalance or voltage issues",
            "5. Monitor motor temperature and bearing condition"
          ] : [
            "1. Verify motor is actually running (check physically)",
            "2. Check for VFD faults or control issues",
            "3. Inspect for mechanical slippage or coupling issues",
            "4. Verify power supply and control signals",
            "5. Check for process upset (no-load condition)"
          ],
          safety: priority >= 4 ? "⚠️ CRITICAL: Abnormal motor operation can indicate equipment failure. Investigate immediately." : "Monitor motor parameters. Check for trends."
        };
      
      default: // Generic alarm guidance
        return {
          title: "Process Alarm",
          steps: [
            "1. Verify alarm condition by checking process value",
            "2. Check for equipment or instrument malfunction",
            "3. Review recent process changes or upsets",
            "4. Consult operating procedures for this condition",
            "5. Contact supervisor/engineer if condition persists",
            "6. Document all actions taken in log book"
          ],
          safety: priority >= 4 ? "⚠️ CRITICAL: High priority alarm requires immediate attention. Follow site emergency procedures." : "Monitor condition. Investigate cause. Document response."
        };
    }
  };

  const getPriorityConfig = (alarm: Alarm) => {
    // Use alarm_priority if available, otherwise map severity to priority
    let priority = alarm.alarm_priority;
    if (priority === null || priority === undefined) {
      // Map severity to priority for old alarms
      switch (alarm.severity) {
        case 'CRITICAL': priority = 5; break;
        case 'URGENT': priority = 4; break;
        case 'HIGH': priority = 3; break;
        case 'WARNING': priority = 2; break;
        case 'LOW': priority = 1; break;
        default: priority = 1;
      }
    }
    
    switch (priority) {
      case 5: // CRITICAL
        return {
          bgColor: "bg-red-900/40",
          borderColor: "border-red-500",
          textColor: "text-red-400",
          iconColor: "text-red-500",
          glowColor: "shadow-red-500/50",
          icon: XCircle,
          label: "P5",
          labelFull: "CRITICAL"
        };
      case 4: // URGENT
        return {
          bgColor: "bg-orange-900/40",
          borderColor: "border-orange-500",
          textColor: "text-orange-400",
          iconColor: "text-orange-500",
          glowColor: "shadow-orange-500/50",
          icon: AlertTriangle,
          label: "P4",
          labelFull: "URGENT"
        };
      case 3: // HIGH PRIORITY
        return {
          bgColor: "bg-yellow-900/40",
          borderColor: "border-yellow-500",
          textColor: "text-yellow-400",
          iconColor: "text-yellow-500",
          glowColor: "shadow-yellow-500/50",
          icon: AlertCircle,
          label: "P3",
          labelFull: "HIGH PRI"
        };
      case 2: // MEDIUM/WARNING
        return {
          bgColor: "bg-blue-900/40",
          borderColor: "border-blue-500",
          textColor: "text-blue-400",
          iconColor: "text-blue-500",
          glowColor: "shadow-blue-500/50",
          icon: Bell,
          label: "P2",
          labelFull: "MEDIUM"
        };
      case 1: // LOW PRIORITY
        return {
          bgColor: "bg-green-900/40",
          borderColor: "border-green-500",
          textColor: "text-green-400",
          iconColor: "text-green-500",
          glowColor: "shadow-green-500/50",
          icon: CheckCircle,
          label: "P1",
          labelFull: "LOW PRI"
        };
      default: // INFO
        return {
          bgColor: "bg-slate-900/40",
          borderColor: "border-slate-500",
          textColor: "text-slate-400",
          iconColor: "text-slate-500",
          glowColor: "shadow-slate-500/50",
          icon: Bell,
          label: "P0",
          labelFull: "INFO"
        };
    }
  };

  // Show absolute HH:MM:SS — makes it obvious the value is frozen (first-hit time)
  const formatTimestamp = (timestamp: string) => {
    if (!timestamp) return '—';
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return timestamp;
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  // Live-compute elapsed time from a frozen raised_at timestamp
  const formatElapsed = (raisedAt: string) => {
    if (!raisedAt) return '';
    const date = new Date(raisedAt);
    if (isNaN(date.getTime())) return '';
    const diffMs = Date.now() - date.getTime();
    if (diffMs < 0) return '<1m';           // clock skew guard
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1)   return '<1m';
    if (diffMin < 60)  return `${diffMin}m`;
    const h = Math.floor(diffMin / 60);
    if (h < 24)        return `${h}h${diffMin % 60 > 0 ? ` ${diffMin % 60}m` : ''}`;
    return `${Math.floor(h / 24)}d${h % 24 > 0 ? ` ${h % 24}h` : ''}`;
  };

  const formatDuration = (minutes: number | null) => {
    if (!minutes) return "N/A";
    if (minutes < 60) return `${Math.floor(minutes)}m`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ${Math.floor(minutes % 60)}m`;
    const days = Math.floor(hours / 24);
    return `${days}d ${hours % 24}h`;
  };

  const isDatabaseBackedAlarm = (alarm: Alarm) => {
    return Number.isInteger(alarm.id) && alarm.id > 0 && alarm.id < 1000000000000;
  };

  const handleAcknowledge = async (alarm: Alarm, event: React.MouseEvent) => {
    event.stopPropagation();

    if (!isDatabaseBackedAlarm(alarm)) {
      // Live MQTT alarm — DB hasn't saved it yet, can't ACK without a DB id
      console.warn('ACK skipped — alarm not yet in DB:', alarm.tag_id);
      return;
    }

    const alarmId = alarm.id;

    // Duplicate click guard — ignore if request already in-flight for this alarm
    if (isPending(alarmId)) return;

    const username = user?.username || 'operator';
    const authToken = localStorage.getItem('auth_token') || '';
    // Capture the pre-optimistic state of THIS alarm only.
    // Using the specific alarm object (not the full array snapshot) means concurrent
    // ACK ALL rollbacks never clobber each other's optimistic updates.
    const alarmBeforeOptimistic = alarm; // the Alarm object passed into this call
    addPending(alarmId);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 12_000); // 12 s timeout

      const response = await fetch(
        `/api/alarms/acknowledge/${alarmId}?user=${encodeURIComponent(username)}`,
        {
          method: 'POST',
          signal: controller.signal,
          headers: {
            'Content-Type': 'application/json',
            ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {}),
          },
          body: JSON.stringify({ notes: '' }),
        }
      );
      clearTimeout(timeoutId);

      const rawText = await response.text();
      let data: any = {};
      try {
        data = rawText ? JSON.parse(rawText) : {};
      } catch {
        data = { success: false, error: rawText || `HTTP ${response.status}` };
      }

      if (response.status === 404 || (data.error || '').toLowerCase().includes('not found')) {
        // Alarm already gone — state machine moved it on. Refresh silently.
        scheduleRefresh();
        return;
      }

      if (response.status === 409) {
        // Another operator already acknowledged this alarm — not an error, just stale UI.
        console.info(`ACK race on alarm ${alarmId}: already handled (${data.current_state ?? 'unknown state'})`);
        scheduleRefresh();
        return;
      }

      if (!response.ok) {
        const errMsg = data.error || `Server error (HTTP ${response.status})`;
        console.error(`ACK failed for alarm ${alarmId}: HTTP ${response.status}`, errMsg);
        showOpMessage(alarmId, `❌ ACK failed: ${errMsg}`, 'error');
        scheduleRefresh();
        return;
      }

      if (data.success) {
        // Optimistic local update — avoids waiting for the next poll cycle
        setAlarms(prevAlarms =>
          prevAlarms.map(a =>
            a.id === alarmId
              ? { ...a, alarm_state: 'ACTIVE_ACK', acknowledged_by: username, acknowledged_at: new Date().toISOString() }
              : a
          )
        );
      } else {
        const errMsg = data.error || 'Acknowledge rejected by server';
        console.warn(`ACK returned success=false for alarm ${alarmId}:`, errMsg);
        showOpMessage(alarmId, `❌ ACK failed: ${errMsg}`, 'error');
        // Rollback only this alarm — safe for concurrent ACK ALL (no sibling clobber)
        setAlarms(prev => prev.map(a => a.id === alarmId ? alarmBeforeOptimistic : a));
        scheduleRefresh();
      }
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        console.warn(`ACK timed out for alarm ${alarmId} — network slow or C# overloaded`);
        showOpMessage(alarmId, '⏱ ACK timed out — server did not respond. Try again.', 'error');
      } else {
        console.error('ACK request failed:', error);
        showOpMessage(alarmId, '❌ ACK failed — could not reach server. Try again.', 'error');
      }
      // Rollback only this alarm — server never confirmed, revert to pre-optimistic state
      setAlarms(prev => prev.map(a => a.id === alarmId ? alarmBeforeOptimistic : a));
      scheduleRefresh();
    } finally {
      removePending(alarmId);
    }
  };

  const handleClear = async (alarmId: number, event: React.MouseEvent) => {
    event.stopPropagation();
    
    // Open clear dialog
    setClearingAlarmId(alarmId);
    setClearReason("");
    setClearNotes("");
  };

  const submitClearAlarm = async () => {
    if (!clearingAlarmId) return;
    
    // Validate that a reason is selected (ISA-18.2 requirement)
    if (!clearReason) {
      // No alert() — show inline message on the alarm card
      showOpMessage(clearingAlarmId, 'Select a clear reason (ISA-18.2 required)', 'warn');
      return;
    }
    
    const username = user?.username || 'operator';
    if (isPending(clearingAlarmId)) return; // duplicate click guard
    // Capture the pre-clear state of THIS alarm only (see ACK rollback rationale).
    const alarmBeforeClear = alarms.find(a => a.id === clearingAlarmId);
    addPending(clearingAlarmId);
    const clearAuthToken = localStorage.getItem('auth_token') || '';
    const authHeaders = {
      'Content-Type': 'application/json',
      ...(clearAuthToken ? { 'Authorization': `Bearer ${clearAuthToken}` } : {}),
    };

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 12_000);

      const res = await fetch(
        `/api/alarms/clear/${clearingAlarmId}?user=${encodeURIComponent(username)}`,
        { method: 'POST', signal: controller.signal, headers: authHeaders, body: JSON.stringify({ reason: clearReason, notes: clearNotes }) }
      );
      clearTimeout(timeoutId);

      const data = await res.json().catch(() => ({ success: false, error: `HTTP ${res.status}` }));

      if (res.status === 404 || (data.error || '').toLowerCase().includes('not found')) {
        setClearingAlarmId(null);
        scheduleRefresh();
        return;
      }

      if (res.status === 409) {
        console.info(`CLEAR race on alarm ${clearingAlarmId}: already handled`);
        setClearingAlarmId(null);
        scheduleRefresh();
        return;
      }

      if (data.success) {
        // Optimistic removal — cleared alarms leave the active panel immediately.
        // History panel (/history route) will show the full lifecycle.
        setAlarms(prev => prev.filter(a => a.id !== clearingAlarmId));
        console.log(`✅ Alarm ${clearingAlarmId} cleared by ${username}: ${clearReason}`);
        setClearingAlarmId(null);
        scheduleRefresh(); // re-sync so any backend-only state changes are reflected
      } else {
        const errMsg = data.error || data.reason || 'Clear rejected by server';
        console.error('CLEAR failed:', errMsg);
        showOpMessage(clearingAlarmId, `❌ Clear failed: ${errMsg}`, 'error');
        setClearingAlarmId(null);
        // Rollback only this alarm (safe for concurrent ops)
        if (alarmBeforeClear) setAlarms(prev => prev.map(a => a.id === clearingAlarmId ? alarmBeforeClear : a));
        scheduleRefresh();
      }
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        console.warn(`CLEAR timed out for alarm ${clearingAlarmId}`);
        showOpMessage(clearingAlarmId ?? 0, '⏱ Clear timed out — server did not respond. Try again.', 'error');
      } else {
        console.error('CLEAR request failed:', error);
        showOpMessage(clearingAlarmId ?? 0, '❌ Clear failed — could not reach server. Try again.', 'error');
      }
      setClearingAlarmId(null);
      // Rollback only this alarm
      if (alarmBeforeClear) setAlarms(prev => prev.map(a => a.id === clearingAlarmId ? alarmBeforeClear : a));
      scheduleRefresh();
    } finally {
      removePending(clearingAlarmId);
    }
  };

  // ISA-18.2: P3+ alarms (HIGH/URGENT/CRITICAL) must be acknowledged individually
  const ACK_ALL_MAX_PRIORITY = 2; // Only P1 (LOW) and P2 (MEDIUM) allowed in batch ACK

  // Toggle selection for ACK ALL (max 10 guard, priority filter)
  const toggleSelectForAck = (alarm: Alarm, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!isDatabaseBackedAlarm(alarm)) return;
    if (alarm.alarm_state !== 'ACTIVE_UNACK' && alarm.alarm_state !== 'RTN_UNACK' && alarm.alarm_state !== null) return;
    // ISA-18.2: Block HIGH/URGENT/CRITICAL from batch ACK — require individual deliberate action
    const priority = alarm.alarm_priority ?? 1;
    if (priority > ACK_ALL_MAX_PRIORITY) {
      const label = priority === 5 ? 'CRITICAL' : priority === 4 ? 'URGENT' : 'HIGH';
      showOpMessage(alarm.id, `${label} alarms require individual ACK (ISA-18.2)`, 'warn');
      return;
    }
    setSelectedForAck(prev => {
      const s = new Set(prev);
      if (s.has(alarm.id)) {
        s.delete(alarm.id);
      } else {
        if (s.size >= ACK_SELECTION_LIMIT) {
          showOpMessage(alarm.id, `Max ${ACK_SELECTION_LIMIT} alarms can be selected at once`, 'warn');
          return prev; // reject — no change
        }
        s.add(alarm.id);
      }
      return s;
    });
  };

  // Process selectedForAck in batches of 10 (already capped, but batch loop future-proofs)
  const executeAckAll = async () => {
    setShowAckAllConfirm(false);
    const ids = Array.from(selectedForAck);
    if (ids.length === 0) return;
    setSelectedForAck(new Set()); // clear selection immediately

    // Pre-validation: filter out alarms that are no longer unacknowledged
    // (another operator may have ACKed them between selection and confirmation)
    const validAlarms = ids
      .map(id => alarms.find(a => a.id === id))
      .filter((a): a is Alarm =>
        !!a &&
        (a.alarm_state === 'ACTIVE_UNACK' || a.alarm_state === 'RTN_UNACK' || a.alarm_state === null) &&
        isDatabaseBackedAlarm(a)
      );

    const skipped = ids.length - validAlarms.length;
    if (skipped > 0) console.info(`[ACK ALL] Skipped ${skipped} alarm(s) — already handled by another operator`);
    if (validAlarms.length === 0) { scheduleRefresh(); return; }

    const BATCH = 10;
    const STAGGER_MS = 50; // 50ms between requests — prevents socket burst on industrial networks
    const syntheticEvent = { stopPropagation: () => {} } as React.MouseEvent;
    for (let i = 0; i < validAlarms.length; i += BATCH) {
      const batch = validAlarms.slice(i, i + BATCH);
      // Fire batch with 50ms stagger to prevent proxy/threadpool spikes
      await Promise.allSettled(
        batch.map((a, idx) =>
          new Promise<void>(resolve =>
            setTimeout(() => handleAcknowledge(a, syntheticEvent).then(resolve).catch(resolve), idx * STAGGER_MS)
          )
        )
      );
    }
    scheduleRefresh();
  };

  const handleViewAuditTrail = async (alarmId: number, event: React.MouseEvent) => {
    event.stopPropagation();
    event.preventDefault();
    setAuditTrailAlarmId(alarmId);
    setLoadingAudit(true);
    setAuditRecords([]);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12_000);
    try {
      const response = await fetch(`/api/alarms/audit/${alarmId}`, { signal: controller.signal });
      clearTimeout(timeoutId);
      const data = await response.json();
      if (data.success && data.audit_trail) {
        setAuditRecords(sortAuditRecordsByTimeAndAction(data.audit_trail));
      } else {
        console.error('Audit trail fetch failed:', data.error);
        setAuditRecords([]);
      }
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        console.warn(`Audit trail timed out for alarm ${alarmId}`);
      } else {
        console.error('Audit trail fetch error:', error);
      }
      setAuditRecords([]);
    } finally {
      clearTimeout(timeoutId);
      setLoadingAudit(false);
    }
  };

  const submitSuppressAlarm = async () => {
    if (!suppressModalAlarm) return;
    if (!suppressReason) {
      showOpMessage(suppressModalAlarm.id, 'Select a suppress reason before confirming', 'warn');
      return;
    }
    // Guard: duration must be a positive number
    const safeDuration = Math.max(0.5, suppressDuration ?? 1);
    const alarmId = suppressModalAlarm.id;
    const username = user?.username || 'operator';
    const authToken = localStorage.getItem('auth_token') || '';
    setSuppressing(alarmId);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12_000);
    try {
      const res = await fetch(
        `/api/alarms/suppress/${alarmId}?user=${encodeURIComponent(username)}`,
        {
          method: 'POST',
          signal: controller.signal,
          headers: { 'Content-Type': 'application/json', ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
          body: JSON.stringify({ duration_hours: safeDuration, reason: suppressReason, notes: suppressNotes }),
        }
      );
      clearTimeout(timeoutId);
      const data = await res.json().catch(() => ({ success: false, error: `HTTP ${res.status}` }));
      if (data.success) {
        setSuppressModalAlarm(null);
        setSuppressReason('');
        setSuppressNotes('');
        setSuppressDuration(1);
        fetchSnapshotRef.current(); // always calls latest fetchSnapshot — no stale closure
      } else {
        console.error('Suppress failed:', data.error);
        showOpMessage(alarmId, `Suppress failed: ${data.error ?? 'unknown error'}`, 'err');
      }
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        console.warn(`Suppress timed out for alarm ${alarmId}`);
        showOpMessage(alarmId, 'Suppress request timed out — try again', 'err');
      } else {
        console.error('Suppress request failed:', e);
        showOpMessage(alarmId, 'Suppress request failed — check network', 'err');
      }
    } finally {
      clearTimeout(timeoutId);
      setSuppressing(null);
    }
  };

  const handleUnsuppress = async (eventId: number) => {
    const username = user?.username || 'operator';
    const authToken = localStorage.getItem('auth_token') || '';
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 12_000);
    try {
      const res = await fetch(
        `/api/alarms/unsuppress/${eventId}?user=${encodeURIComponent(username)}`,
        {
          method: 'POST',
          signal: controller.signal,
          headers: { 'Content-Type': 'application/json', ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}) },
        }
      );
      clearTimeout(timeoutId);
      const data = await res.json().catch(() => ({ success: false, error: `HTTP ${res.status}` }));
      if (data.success) {
        fetchSnapshotRef.current();
      } else {
        console.error('Unsuppress failed:', data.error);
      }
    } catch (e: any) {
      if (e?.name === 'AbortError') console.warn(`Unsuppress timed out for event ${eventId}`);
      else console.error('Unsuppress request failed:', e);
    } finally {
      clearTimeout(timeoutId);
    }
  };


  const activeAlarms = alarms.filter(a =>
    a.alarm_state === 'ACTIVE_UNACK' || a.alarm_state === 'ACTIVE_ACK' ||
    a.alarm_state === 'RTN_UNACK' || a.alarm_state === null
  );
  const criticalCount = activeAlarms.filter(a => a.alarm_priority === 5 || (a.alarm_priority === null && a.severity === 'CRITICAL')).length;
  
  // CRITICAL FIX: Remove duplicate alarms using composite key (tag_id + alarm_state)
  // This handles both database alarms (numeric IDs) and WebSocket alarms (temp IDs)
  // Duplicates occur when same tag has multiple ACTIVE alarms from different sources
  const deduplicatedAlarms = useMemo(() => {
    // Use tag_id + alarm_state as deduplication key (not just ID)
    const seen = new Map<string, Alarm>();
    
    alarms.forEach(alarm => {
      // Create composite key: tag_id + state + event_type
      const compositeKey = `${alarm.tag_id}_${alarm.alarm_state || 'ACTIVE_UNACK'}_${alarm.event_type}`;
      
      if (!seen.has(compositeKey)) {
        seen.set(compositeKey, alarm);
      } else {
        // Keep the alarm with the real database ID (lower number = from database)
        const existing = seen.get(compositeKey)!;
        if (alarm.id < 1000000000000 && existing.id > 1000000000000) {
          // DB id wins over temp WebSocket id
          seen.set(compositeKey, alarm);
        } else if (existing.id > 1000000000000 && alarm.id > 1000000000000) {
          // Both temp — keep the newer timestamp
          if (alarm.id > existing.id) seen.set(compositeKey, alarm);
        }
        // else: duplicate DB row — keep first seen (lower is older, more stable)
      }
    });
    return Array.from(seen.values());
  }, [alarms]);
  
  // Filtering + search — recomputes only when alarms, search, or toggle changes.
  // No console.log here: this memo runs on every keystroke and every poll cycle.
  const { displayedAlarms, matchedCount } = useMemo(() => {
    const baseFilteredAlarms = showClearedAlarms
      ? deduplicatedAlarms.slice()
      : deduplicatedAlarms.filter(a => a.alarm_state !== 'CLEARED');

    if (!searchTag.trim()) {
      return { displayedAlarms: baseFilteredAlarms, matchedCount: 0 };
    }

    const searchLower = searchTag.toLowerCase();
    const matchedAlarms: Alarm[] = [];
    const unmatchedAlarms: Alarm[] = [];

    for (const a of baseFilteredAlarms) {
      if (a.tag_name.toLowerCase().includes(searchLower) || a.tag_id.toLowerCase().includes(searchLower)) {
        matchedAlarms.push(a);
      } else {
        unmatchedAlarms.push(a);
      }
    }

    // Sort matched by priority desc, then timestamp desc
    matchedAlarms.sort((a, b) => {
      const pd = (b.alarm_priority || 1) - (a.alarm_priority || 1);
      if (pd !== 0) return pd;
      return new Date(b.raised_at).getTime() - new Date(a.raised_at).getTime();
    });

    return { displayedAlarms: [...matchedAlarms, ...unmatchedAlarms], matchedCount: matchedAlarms.length };
  }, [deduplicatedAlarms, searchTag, showClearedAlarms]);

  return (
    <div className={cn("relative flex flex-col h-full", className)}>
      {/* Alarm Header Bar - Compact for Sidebar */}
      <div
        className={cn(
          "flex items-center justify-between px-3 py-1 rounded-t-lg border transition-all cursor-pointer",
          criticalCount > 0
            ? "bg-orange-900/70 border-orange-500 animate-pulse"
            : activeAlarms.length > 0
            ? "bg-orange-900/60 border-orange-500"
            : "bg-amber-900/60 border-amber-600"
        )}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          <div className="relative">
            <Bell className={cn(
              "w-3 h-3",
              criticalCount > 0 ? "text-orange-300 animate-pulse" : 
              activeAlarms.length > 0 ? "text-orange-400" : "text-amber-400"
            )} />
            {activeAlarms.length > 0 && (
              <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-600 text-white text-[8px] font-bold rounded-full flex items-center justify-center animate-pulse">
                {activeAlarms.length}
              </span>
            )}
          </div>
          <div>
            <h3 className="text-[10px] font-bold text-white uppercase tracking-wide">
              Alarms
            </h3>
            <p className="text-[9px] text-slate-300">
              {criticalCount > 0 && <span className="text-red-400 font-bold">{criticalCount} Critical </span>}
              {activeAlarms.length === 0 ? "Normal" : `${activeAlarms.length} Active`}
              {/* ISA-18.2: Warn if alarm flood (>10 alarms) */}
              {activeAlarms.length > 10 && (
                <span className="text-orange-400 font-bold ml-1">⚠ FLOOD</span>
              )}
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {/* ACK ALL — only shown when unack alarms exist AND user can operate */}
          {canOperateAlarms && selectedForAck.size > 0 && (
            <button
              onClick={(e) => { e.stopPropagation(); setShowAckAllConfirm(true); }}
              className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded border transition-all bg-orange-700/70 border-orange-500 text-orange-100 hover:bg-orange-600/80 font-bold"
              title={`Acknowledge ${selectedForAck.size} selected alarm(s)`}
            >
              <CheckCircle className="w-2.5 h-2.5" />
              ACK {selectedForAck.size}/{ACK_SELECTION_LIMIT}
            </button>
          )}

          {/* Toggle cleared alarms visibility */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowClearedAlarms(!showClearedAlarms);
            }}
            className={cn(
              "text-[9px] px-1.5 py-0.5 rounded border transition-all",
              showClearedAlarms 
                ? "bg-green-700/50 border-green-500 text-green-300" 
                : "bg-slate-700/50 border-slate-500 text-slate-400"
            )}
            title={showClearedAlarms ? "Hide cleared alarms" : "Show cleared alarms"}
          >
            {showClearedAlarms ? "✓" : "✗"} Cleared
          </button>

          {/* Alarm History button */}
          <button
            onClick={(e) => { e.stopPropagation(); setShowHistoryModal(true); }}
            className="flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded border transition-all bg-blue-800/50 border-blue-600 text-blue-300 hover:bg-blue-700/70"
            title="Open Alarm History"
          >
            <BookOpen className="w-2.5 h-2.5" /> History
          </button>
          
          <span className="text-xs text-slate-400">
            {isExpanded ? "▼" : "▶"}
          </span>
        </div>
      </div>

      {/* Alarm List - Compact */}
      {isExpanded && (
        <div className="flex-1 overflow-hidden flex flex-col bg-gradient-to-br from-slate-900/95 via-slate-800/95 to-slate-900/95 border border-t-0 border-slate-600 rounded-b-lg shadow-xl">
          {/* Search Bar - ISA-18.2: Quick alarm filtering */}
          <div className="px-3 py-2 border-b border-slate-700/50 bg-slate-800/50">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
              <input
                type="text"
                value={searchTag}
                onChange={(e) => {
                  const newValue = e.target.value;
                  console.log('⌨️ Search input changed:', `"${searchTag}"`, '→', `"${newValue}"`);
                  setSearchTag(newValue);
                }}
                placeholder="Search by tag name..."
                className="w-full bg-slate-900/70 text-white text-xs pl-8 pr-8 py-1 rounded border border-slate-600 focus:border-blue-500 focus:outline-none placeholder-slate-500"
              />
              {searchTag && (
                <button
                  onClick={() => {
                    console.log('❌ Clearing search');
                    setSearchTag("");
                  }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white transition-colors"
                  title="Clear search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            {searchTag && (
              <div className="text-[10px] text-slate-400 mt-1">
                {matchedCount > 0 
                  ? `Found ${matchedCount} alarm(s) matching "${searchTag}" (shown at top)`
                  : `No alarms found matching "${searchTag}"`}
              </div>
            )}
          </div>

          {loading ? (
            <div className="p-4 text-center text-slate-400">
              <div className="animate-spin w-4 h-4 border-2 border-primary border-t-transparent rounded-full mx-auto mb-2" />
              <span className="text-xs">Loading...</span>
            </div>
          ) : (
            <>
              {/* ── Circuit breaker degraded banner ───────────────────────── */}
              {isDegraded && (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-red-950/80 border-b border-red-700 text-[9px] font-semibold text-red-300">
                  <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
                  <span>⚠ BACKEND UNREACHABLE — {consecutiveFailures.current} consecutive failures. Showing last known state.</span>
                  <button
                    onClick={() => { consecutiveFailures.current = 0; setIsDegraded(false); fetchSnapshot(true); }}
                    className="ml-auto px-2 py-0.5 rounded border border-red-500 hover:bg-red-800/50 transition-colors"
                  >
                    Retry
                  </button>
                </div>
              )}

              {/* ── Metrics bar ────────────────────────────────────────────── */}
              {(() => {
                void metricsSeq; // ensures 1-second tick re-renders this block
                const pendingCount = pendingOps.size;
                const queuedCount  = selectedForAck.size;
                const saturationPct = Math.round((queuedCount / ACK_SELECTION_LIMIT) * 100);
                const secAgo = lastSyncAt.current
                  ? Math.floor((Date.now() - lastSyncAt.current) / 1000)
                  : null;
                const lastSyncStr = secAgo === null
                  ? '—'
                  : secAgo < 5  ? 'just now'
                  : secAgo < 60 ? `${secAgo}s ago`
                  : `${Math.floor(secAgo / 60)}m ago`;
                const latencyStr = syncLatencyMs !== null ? `${syncLatencyMs}ms` : '—';
                // Latency colour: green <300ms, amber <1000ms, red ≥1000ms
                const latencyColor = syncLatencyMs === null ? 'text-slate-500'
                  : syncLatencyMs < 300  ? 'text-green-400'
                  : syncLatencyMs < 1000 ? 'text-amber-400'
                  : 'text-red-400';
                // Staleness warning: if last sync was >10s ago something is wrong
                const isStale = secAgo !== null && secAgo > 10;
                // Queue saturation colour: green <50%, amber ≥50%, red ≥80%
                const queueColor = queuedCount === 0 ? 'text-slate-500'
                  : saturationPct >= 80 ? 'text-red-400'
                  : saturationPct >= 50 ? 'text-amber-300'
                  : 'text-orange-300';
                return (
                  <div className={cn(
                    "flex items-center gap-3 px-3 py-1 border-b text-[9px] font-mono",
                    isStale
                      ? "bg-amber-950/40 border-amber-700/50"
                      : "bg-slate-900/60 border-slate-700/40"
                  )}>
                    {/* Pending ops */}
                    <span className={cn(
                      "flex items-center gap-1",
                      pendingCount > 0 ? "text-orange-300" : "text-slate-500"
                    )}>
                      <span className={cn(
                        "w-1.5 h-1.5 rounded-full",
                        pendingCount > 0 ? "bg-orange-400 animate-pulse" : "bg-slate-600"
                      )} />
                      Pending: {pendingCount}
                    </span>

                    <span className="text-slate-700">│</span>

                    {/* Queued for ACK — with saturation indicator */}
                    <span className={cn("flex items-center gap-1", queueColor)}>
                      Queued: {queuedCount}/{ACK_SELECTION_LIMIT}
                      {saturationPct >= 80 && <span title={`${saturationPct}% — near limit`}>⚠</span>}
                    </span>

                    <span className="text-slate-700">│</span>

                    {/* Last sync */}
                    <span className={isStale ? "text-amber-300" : "text-slate-500"}>
                      {isStale && <span className="mr-0.5">⚠</span>}
                      Sync: {lastSyncStr}
                    </span>

                    <span className="text-slate-700">│</span>

                    {/* Latency */}
                    <span className={latencyColor}>
                      {latencyStr}
                    </span>

                    {/* Manual refresh — Shift+Click bypasses debounce for hard reload */}
                    <button
                      onClick={(e) => {
                        if (e.shiftKey) {
                          // Hard reload: reset stale lock, bypass circuit breaker
                          pollingInProgress.current = false;
                          consecutiveFailures.current = 0;
                          fetchSnapshot(true);
                        } else {
                          scheduleRefresh();
                        }
                      }}
                      title="Refresh (Shift+Click = hard reload, bypasses all guards)"
                      className="ml-auto text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      ↻
                    </button>
                  </div>
                );
              })()}

              {/* Alarm list body */}
              {displayedAlarms.length === 0 ? (
                searchTag.trim() ? (
                  <div className="p-4 text-center">
                    <Search className="w-6 h-6 text-slate-500 mx-auto mb-2" />
                    <p className="text-xs font-semibold text-slate-400">No Alarms Found</p>
                    <p className="text-[10px] text-slate-500 mt-1">No matches for "{searchTag}"</p>
                  </div>
                ) : (
                  <div className="p-4 text-center">
                    <Bell className="w-6 h-6 text-green-500 mx-auto mb-2" />
                    <p className="text-xs font-semibold text-green-400">No Active Alarms</p>
                    <p className="text-[10px] text-slate-400 mt-1">System Normal</p>
                  </div>
                )
              ) : (
            <div className="overflow-y-auto flex-1" style={{ height: '100%' }}>
              {/* ISA-18.2: Show ALL active alarms (no limit), scrollable list */}
              <div className="p-2 space-y-2">
                {displayedAlarms.map((alarm, index) => {
                  const config = getPriorityConfig(alarm);
                  const Icon = config.icon;
                  
                  // Check if alarm matches search
                  const searchLower = searchTag.toLowerCase();
                  const isMatchingSearch = !searchTag.trim() || 
                    alarm.tag_name.toLowerCase().includes(searchLower) ||
                    alarm.tag_id.toLowerCase().includes(searchLower);

                  return (
                    <div
                      key={`alarm-${alarm.id}-${index}`}
                      className={cn(
                        "relative p-2 rounded-lg border-2 transition-all",
                        alarm.alarm_state === 'CLEARED' 
                          ? "bg-slate-800/30 border-slate-700/50 opacity-70" // Grayed out for cleared alarms
                          : config.bgColor,
                        alarm.alarm_state === 'CLEARED' 
                          ? "border-slate-700/50" 
                          : config.borderColor,
                        "shadow-lg hover:shadow-xl",
                        // Dim non-matching alarms during search
                        searchTag.trim() && !isMatchingSearch && "opacity-30 blur-[1px]",
                        // Highlight matching alarms with stronger border
                        searchTag.trim() && isMatchingSearch && "ring-2 ring-blue-500 border-blue-400 shadow-blue-500/50"
                      )}
                    >
                      {/* Search Match Indicator - Top Right */}
                      {searchTag.trim() && isMatchingSearch && (
                        <div className="absolute top-1 right-1 bg-blue-600/90 text-white text-[9px] font-bold px-1.5 py-0.5 rounded border border-blue-400 flex items-center gap-1 shadow-lg">
                          <Search className="w-2.5 h-2.5" />
                          MATCH
                        </div>
                      )}
                      
                      {/* CLEARED Badge - Top Right (below MATCH if present) */}
                      {alarm.alarm_state === 'CLEARED' && (
                        <div className={cn(
                          "absolute right-1 bg-green-700/80 text-white text-[9px] font-bold px-1.5 py-0.5 rounded border border-green-500",
                          searchTag.trim() && isMatchingSearch ? "top-8" : "top-1"
                        )}>
                          ✓ CLEARED
                        </div>
                      )}
                      
                      <div className="flex gap-1.5">
                        {/* Icon */}
                        <div className="flex-shrink-0">
                          <Icon className={cn("w-4 h-4", config.iconColor)} />
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          {/* Header Row: Tag Name Only */}
                          <div className="flex items-center gap-2 mb-1">
                            <span 
                              className="font-mono text-[11px] font-bold text-amber-400 bg-slate-950/90 px-2 py-0.5 rounded border border-amber-600/50 max-w-[180px] overflow-hidden text-ellipsis whitespace-nowrap"
                              title={alarm.tag_name}
                            >
                              {alarm.tag_name}
                            </span>
                          </div>

                          {/* Message */}
                          <p className={cn(
                            "text-[10px] font-medium leading-snug mb-1",
                            "text-slate-100",
                            "break-words pr-1"
                          )}>
                            {alarm.message}
                          </p>

                          {/* Setpoint vs Actual - Compact Inline */}
                          {alarm.alarm_setpoint !== null && alarm.alarm_actual_value !== null && (
                            <div className="flex items-center gap-2 mb-1 text-[10px] bg-slate-950/30 px-1.5 py-0.5 rounded">
                              <div className="flex items-center gap-1">
                                <span className="text-slate-400 font-medium">SP:</span>
                                <span className="font-mono font-bold text-cyan-300 min-w-[40px] text-right">{alarm.alarm_setpoint.toFixed(2)}</span>
                              </div>
                              <div className="flex items-center gap-1">
                                <span className="text-slate-400 font-medium" title="Frozen trigger value — the exact PV when alarm fired">PV@Trip:</span>
                                <span className={cn("font-mono font-bold min-w-[40px] text-right", config.textColor)}>
                                  {alarm.alarm_actual_value.toFixed(2)}
                                </span>
                                {alarm.alarm_actual_value > alarm.alarm_setpoint ? (
                                  <svg className="w-3 h-3 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                                  </svg>
                                ) : (
                                  <svg className="w-3 h-3 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
                                  </svg>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Footer - Compact Single Row */}
                          <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 pt-1 border-t border-slate-700/50">
                            {/* Help Button */}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setShowHelp(showHelp === alarm.id ? null : alarm.id);
                              }}
                              className={cn(
                                "flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold",
                                showHelp === alarm.id
                                  ? "bg-blue-700 text-white border-blue-400"
                                  : "bg-slate-700/70 hover:bg-slate-600 text-slate-300 hover:text-white border-slate-600 hover:border-slate-400",
                                "border transition-all duration-200"
                              )}
                              title="Operator Guidance"
                            >
                              <HelpCircle className="w-3 h-3" />
                            </button>
                            
                            {/* Audit Trail Button */}
                            <button
                              onClick={(e) => handleViewAuditTrail(alarm.id, e)}
                              className={cn(
                                "flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold",
                                "bg-slate-700/70 hover:bg-slate-600 text-slate-300 hover:text-white",
                                "border border-slate-600 hover:border-slate-400",
                                "transition-all duration-200"
                              )}
                              title="View Audit Trail"
                            >
                              <History className="w-3 h-3" />
                            </button>
                            
                            {/* Last ≤3 raise times — always live from DB, always updated */}
                            <div className="flex items-center gap-1 flex-wrap">
                              {(alarm.recent_raise_times && alarm.recent_raise_times.length > 0
                                ? alarm.recent_raise_times
                                : [alarm.raised_at]
                              ).map((t, i) => (
                                <div
                                  key={i}
                                  className={cn(
                                    "flex items-center gap-0.5 text-[9px] font-mono whitespace-nowrap",
                                    i === 0 ? "text-amber-300 font-bold" : "text-slate-400"
                                  )}
                                  title={i === 0 ? `Last raised: ${t}` : `Previous raise #${i + 1}: ${t}`}
                                >
                                  {i === 0 && <Clock className="w-3 h-3 text-amber-400" />}
                                  {i > 0 && <span className="text-slate-600">↩</span>}
                                  <span>{formatTimestamp(t)}</span>
                                </div>
                              ))}
                              {alarm.recent_raise_times && alarm.recent_raise_times.length > 1 && (
                                <span
                                  className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-900/60 border border-amber-600 text-amber-300 whitespace-nowrap"
                                  title={`Raised ${alarm.recent_raise_times.length}x recently — value keeps returning above limit`}
                                >
                                  ×{alarm.recent_raise_times.length}
                                </span>
                              )}
                            </div>

                            {/* Last ACK info */}
                            {alarm.acknowledged_by && alarm.acknowledged_at && (
                              <div
                                className="flex items-center gap-0.5 text-[9px] text-blue-300 whitespace-nowrap"
                                title={`Acknowledged at ${alarm.acknowledged_at}`}
                              >
                                <CheckCircle className="w-3 h-3" />
                                <span>{alarm.acknowledged_by} @ {formatTimestamp(alarm.acknowledged_at)}</span>
                              </div>
                            )}

                            {/* Last CLEAR info */}
                            {alarm.last_cleared_by && alarm.last_cleared_at && (
                              <div
                                className="flex items-center gap-0.5 text-[9px] text-green-400 whitespace-nowrap"
                                title={`Last cleared at ${alarm.last_cleared_at} — alarm re-triggered since then`}
                              >
                                <XCircle className="w-3 h-3" />
                                <span>Cleared {alarm.last_cleared_by} @ {formatTimestamp(alarm.last_cleared_at)}</span>
                              </div>
                            )}

                            {/* Spacer */}
                            <div className="flex-1 min-w-[4px]"></div>
                            
                            {/* Status Badge */}
                            {(alarm.alarm_state === 'ACTIVE_ACK' || alarm.alarm_state === 'CLEARED') && (
                              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider text-blue-300 bg-blue-900/70 border border-blue-500 whitespace-nowrap">
                                ✓ ACK
                              </span>
                            )}
                            {alarm.alarm_state === 'RTN_UNACK' && (
                              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider text-amber-300 bg-amber-900/70 border border-amber-500 whitespace-nowrap">
                                RTN
                              </span>
                            )}
                            {/* Alarm Level badge (H/HH/L/LL) — what limit was crossed */}
                            {alarm.alarm_level && (() => {
                              const lvl = alarm.alarm_level.toUpperCase();
                              const lvlStyle =
                                lvl === 'HIGHHIGH' || lvl === 'HH' ? 'border-red-500 text-red-300 bg-red-950/70' :
                                lvl === 'HIGH'     || lvl === 'H'  ? 'border-yellow-500 text-yellow-300 bg-yellow-950/70' :
                                lvl === 'LOWLOW'   || lvl === 'LL' ? 'border-purple-500 text-purple-300 bg-purple-950/70' :
                                lvl === 'LOW'      || lvl === 'L'  ? 'border-blue-500 text-blue-300 bg-blue-950/70' :
                                'border-slate-500 text-slate-300 bg-slate-900/70';
                              const lvlShort =
                                lvl === 'HIGHHIGH' ? 'HH' :
                                lvl === 'HIGH'     ? 'H'  :
                                lvl === 'LOWLOW'   ? 'LL' :
                                lvl === 'LOW'      ? 'L'  : lvl;
                              return (
                                <span className={cn(
                                  "text-[9px] font-bold px-1.5 py-0.5 rounded border-2 uppercase tracking-wider whitespace-nowrap",
                                  lvlStyle
                                )} title={`Alarm level: ${alarm.alarm_level}`}>
                                  {lvlShort}
                                </span>
                              );
                            })()}
                            {/* Priority badge (configured severity) */}
                            <span className={cn(
                              "text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider whitespace-nowrap",
                              "text-white bg-black/60 border-2",
                              config.borderColor
                            )} title={`Priority: ${config.label}`}>
                              {config.label}
                            </span>
                            
                            {/* Inline op message (replaces alert()) */}
                            {opMessages.has(alarm.id) && (() => {
                              const msg = opMessages.get(alarm.id)!;
                              return (
                                <span className={cn(
                                  "text-[9px] px-1.5 py-0.5 rounded border font-semibold whitespace-nowrap",
                                  msg.type === 'warn' ? "bg-amber-900/60 border-amber-500 text-amber-300" :
                                  msg.type === 'err'  ? "bg-red-900/60 border-red-500 text-red-300" :
                                  "bg-blue-900/60 border-blue-500 text-blue-300"
                                )}>
                                  {msg.text}
                                </span>
                              );
                            })()}

                            {/* Action Button */}
                            {(alarm.alarm_state === 'ACTIVE_UNACK' || alarm.alarm_state === 'RTN_UNACK' || alarm.alarm_state === null) ? (
                              <div className="flex items-center gap-1">
                                {/* Selection checkbox for ACK ALL — Viewer cannot operate */}
                                {canOperateAlarms && isDatabaseBackedAlarm(alarm) && (
                                  <button
                                    onClick={(e) => toggleSelectForAck(alarm, e)}
                                    title={selectedForAck.has(alarm.id) ? "Deselect for batch ACK" : selectedForAck.size >= ACK_SELECTION_LIMIT ? `Max ${ACK_SELECTION_LIMIT} selected` : "Select for batch ACK"}
                                    className={cn(
                                      "w-4 h-4 rounded border-2 flex items-center justify-center transition-all flex-shrink-0",
                                      selectedForAck.has(alarm.id)
                                        ? "bg-orange-600 border-orange-400 text-white"
                                        : selectedForAck.size >= ACK_SELECTION_LIMIT
                                        ? "bg-slate-800 border-slate-600 text-slate-600 cursor-not-allowed"
                                        : "bg-slate-800 border-slate-600 hover:border-orange-500 text-slate-500"
                                    )}
                                  >
                                    {selectedForAck.has(alarm.id) && <span className="text-[8px] font-bold leading-none">✓</span>}
                                  </button>
                                )}
                                {/* ACK — Viewer cannot operate */}
                                {canOperateAlarms && (
                                  <button
                                    onClick={(e) => handleAcknowledge(alarm, e)}
                                    disabled={isPending(alarm.id) || !isDatabaseBackedAlarm(alarm)}
                                    title={!isDatabaseBackedAlarm(alarm) ? "Waiting for DB save before acknowledge" : alarm.alarm_state === 'RTN_UNACK' ? "ACK this alarm — value returned to normal, ACK will CLEAR it" : "Acknowledge alarm"}
                                    className={cn(
                                      "flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold whitespace-nowrap",
                                      "bg-slate-700 hover:bg-slate-600 text-white",
                                      "border border-slate-500 hover:border-slate-400",
                                      "transition-all duration-200",
                                      "disabled:opacity-50 disabled:cursor-not-allowed",
                                      isPending(alarm.id) && "animate-pulse"
                                    )}
                                  >
                                    {isPending(alarm.id) ? (
                                      <><div className="animate-spin w-2.5 h-2.5 border-2 border-white border-t-transparent rounded-full" /><span>ACK</span></>
                                    ) : (
                                      <><CheckCircle className="w-3 h-3" /><span>ACK</span></>
                                    )}
                                  </button>
                                )}
                                {/* SUPP — Viewer cannot operate */}
                                {canOperateAlarms && isDatabaseBackedAlarm(alarm) && (
                                  <button
                                    onClick={(e) => { e.stopPropagation(); setSuppressModalAlarm(alarm); }}
                                    title="Suppress this alarm (hide from active panel)"
                                    className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold whitespace-nowrap bg-purple-900/70 hover:bg-purple-800 text-purple-200 border border-purple-600 hover:border-purple-400 transition-all duration-200"
                                  >
                                    SUPP
                                  </button>
                                )}
                              </div>
                            ) : alarm.alarm_state === 'ACTIVE_ACK' ? (
                              <>
                                {alarm.acknowledged_by && (
                                  <div className="flex flex-col gap-0.5">
                                    <div className="text-[9px] text-blue-300 font-semibold whitespace-nowrap">
                                      ✓ ACK: {alarm.acknowledged_by}
                                    </div>
                                    {alarm.acknowledged_at && (
                                      <div className="text-[9px] text-blue-200/70 font-mono whitespace-nowrap">
                                        @ {formatTimestamp(alarm.acknowledged_at)}
                                      </div>
                                    )}
                                  </div>
                                )}
                                {canOperateAlarms && <button
                                  onClick={(e) => handleClear(alarm.id, e)}
                                  disabled={isPending(alarm.id)}
                                  className={cn(
                                    "flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-bold whitespace-nowrap",
                                    "bg-green-700 hover:bg-green-600 text-white",
                                    "border border-green-500 hover:border-green-400",
                                    "transition-all duration-200",
                                    "disabled:opacity-50 disabled:cursor-not-allowed",
                                    isPending(alarm.id) && "animate-pulse"
                                  )}
                                >
                                  {isPending(alarm.id) ? (
                                    <>
                                      <div className="animate-spin w-2.5 h-2.5 border-2 border-white border-t-transparent rounded-full" />
                                      <span>CLR</span>
                                    </>
                                  ) : (
                                    <>
                                      <CheckCircle className="w-3 h-3" />
                                      <span>CLEAR</span>
                                    </>
                                  )}
                                </button>}
                              </>
                            ) : alarm.alarm_state === 'CLEARED' ? (
                              // CLEARED: always has ACK first (enforced by state machine)
                              // Show full audit trail: who ACKed when, who CLEARed when
                              <div className="flex flex-col gap-0.5">
                                {alarm.acknowledged_by && (
                                  <div className="text-[9px] text-blue-300 font-semibold whitespace-nowrap">
                                    ✓ ACK: {alarm.acknowledged_by}{alarm.acknowledged_at ? ` @ ${formatTimestamp(alarm.acknowledged_at)}` : ''}
                                  </div>
                                )}
                                {alarm.cleared_by && (
                                  <div className="text-[9px] text-green-300 font-semibold whitespace-nowrap">
                                    ✓ CLR: {alarm.cleared_by}{alarm.cleared_at ? ` @ ${formatTimestamp(alarm.cleared_at)}` : ''}
                                  </div>
                                )}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </div>

                      {/* Help Tooltip - ISA-18.2: Context-Sensitive Operator Guidance */}
                      {showHelp === alarm.id && (() => {
                        const help = getAlarmHelp(alarm);
                        return (
                          <div className="mt-2 p-3 bg-blue-950/95 border-2 border-blue-500 rounded-lg">
                            <div className="flex items-start gap-2 mb-2">
                              <HelpCircle className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
                              <div className="flex-1">
                                <h4 className="text-sm font-bold text-blue-300 mb-1">{help.title}</h4>
                                <p className="text-xs text-blue-200 mb-2">Operator Guidance (ISA-18.2)</p>
                              </div>
                            </div>
                            
                            <div className="mb-3">
                              <p className="text-xs font-semibold text-white mb-1.5">Recommended Actions:</p>
                              <ol className="space-y-1">
                                {help.steps.map((step, idx) => (
                                  <li key={idx} className="text-xs text-slate-200 leading-relaxed">
                                    {step}
                                  </li>
                                ))}
                              </ol>
                            </div>
                            
                            <div className="pt-2 border-t border-blue-800/50">
                              <div className="flex items-start gap-2">
                                <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0 mt-0.5" />
                                <p className="text-xs text-amber-200">{help.safety}</p>
                              </div>
                            </div>
                            
                            <div className="mt-2 pt-2 border-t border-blue-800/50">
                              <p className="text-[10px] text-blue-400 italic">
                                Note: Always follow site-specific operating procedures and safety protocols.
                              </p>
                            </div>
                          </div>
                        );
                      })()}

                      {/* Pulsing animation for critical alarms */}
                      {(alarm.alarm_priority === 5 || (alarm.alarm_priority === null && alarm.severity === 'CRITICAL')) && (alarm.alarm_state === 'ACTIVE_UNACK' || alarm.alarm_state === 'RTN_UNACK' || alarm.alarm_state === null) && (
                        <div className="absolute inset-0 rounded-lg border-2 border-red-500 animate-pulse opacity-30 pointer-events-none" />
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
            </>
          )}
        </div>
      )}

      {/* ACK ALL Confirmation Modal */}
      {showAckAllConfirm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setShowAckAllConfirm(false)}>
          <div className="bg-slate-800 border-2 border-orange-500 rounded-lg p-6 max-w-sm w-full mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle className="w-5 h-5 text-orange-400" />
              <h3 className="text-base font-bold text-white">Acknowledge {selectedForAck.size} Alarm{selectedForAck.size > 1 ? 's' : ''}?</h3>
            </div>
            <p className="text-sm text-slate-300 mb-1">
              You are about to acknowledge <span className="font-bold text-orange-300">{selectedForAck.size}</span> alarm{selectedForAck.size > 1 ? 's' : ''} as <span className="font-bold text-white">{user?.username || 'operator'}</span>.
            </p>
            <p className="text-xs text-slate-400 mb-5">Each acknowledgement is recorded in the audit trail (ISA-18.2).</p>
            <div className="flex gap-3">
              <button
                onClick={executeAckAll}
                className="flex-1 px-4 py-2 rounded font-bold text-sm bg-orange-600 hover:bg-orange-700 text-white border-2 border-orange-500 transition-all"
              >
                Confirm ACK All
              </button>
              <button
                onClick={() => setShowAckAllConfirm(false)}
                className="flex-1 px-4 py-2 rounded font-bold text-sm bg-slate-700 hover:bg-slate-600 text-white border-2 border-slate-600 transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Clear Alarm Dialog - ISA-18.2 Compliant */}
      {clearingAlarmId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setClearingAlarmId(null)}>
          <div 
            className="bg-slate-800 border-2 border-slate-600 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <h3 className="text-lg font-bold text-white">Clear Alarm</h3>
            </div>
            
            <div className="text-sm text-slate-300 mb-4">
              <p>Per <strong>ISA-18.2</strong> standard, please document the corrective action taken to resolve this alarm.</p>
            </div>

            {/* Clear Reason Selection (Required) */}
            <div className="mb-4">
              <label className="block text-sm font-semibold text-white mb-2">
                Clear Reason <span className="text-red-400">*</span>
              </label>
              <select
                value={clearReason}
                onChange={(e) => setClearReason(e.target.value)}
                className="w-full bg-slate-700 text-white border border-slate-600 rounded px-3 py-2 focus:border-blue-500 focus:outline-none"
              >
                <option value="">-- Select Reason --</option>
                <option value="Process adjusted to normal">Process adjusted to normal</option>
                <option value="Equipment repaired/restarted">Equipment repaired/restarted</option>
                <option value="Setpoint corrected">Setpoint corrected</option>
                <option value="Sensor calibrated">Sensor calibrated</option>
                <option value="Valve operated manually">Valve operated manually</option>
                <option value="System reset">System reset</option>
                <option value="Condition normalized automatically">Condition normalized automatically</option>
                <option value="False alarm - no action required">False alarm - no action required</option>
                <option value="Maintenance completed">Maintenance completed</option>
                <option value="Other (see notes)">Other (see notes)</option>
              </select>
            </div>

            {/* Additional Notes (Optional) */}
            <div className="mb-4">
              <label className="block text-sm font-semibold text-white mb-2">
                Additional Notes <span className="text-slate-400">(Optional)</span>
              </label>
              <textarea
                value={clearNotes}
                onChange={(e) => setClearNotes(e.target.value)}
                placeholder="Describe specific actions taken..."
                className="w-full bg-slate-700 text-white border border-slate-600 rounded px-3 py-2 focus:border-blue-500 focus:outline-none resize-none"
                rows={3}
              />
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              <button
                onClick={submitClearAlarm}
                disabled={!clearReason || isPending(clearingAlarmId ?? -1)}
                className={cn(
                  "flex-1 px-4 py-2 rounded font-bold text-sm",
                  "bg-green-600 hover:bg-green-700 text-white",
                  "border-2 border-green-500",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  "transition-all duration-200"
                )}
              >
                {isPending(clearingAlarmId ?? -1) ? "Clearing..." : "Confirm Clear"}
              </button>
              <button
                onClick={() => setClearingAlarmId(null)}
                disabled={isPending(clearingAlarmId ?? -1)}
                className="flex-1 px-4 py-2 rounded font-bold text-sm bg-slate-700 hover:bg-slate-600 text-white border-2 border-slate-600 transition-all duration-200"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Alarm History Modal ─────────────────────────────────── */}
      {showHistoryModal && (
        <AlarmHistoryModal onClose={() => setShowHistoryModal(false)} />
      )}

      {/* Audit Trail Modal - ISA-18.2 Compliance */}
      {auditTrailAlarmId && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={() => setAuditTrailAlarmId(null)}>
          <div 
            className="bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 border-2 border-blue-500/50 rounded-lg max-w-4xl w-full max-h-[85vh] overflow-hidden shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="bg-slate-800/90 border-b border-slate-600 px-6 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <History className="w-6 h-6 text-blue-400" />
                  <div>
                    <h3 className="text-lg font-bold text-white">Alarm Audit Trail</h3>
                    <p className="text-xs text-slate-400">ISA-18.2 Compliant - Event ID: {auditTrailAlarmId}</p>
                  </div>
                </div>
                <button
                  onClick={() => setAuditTrailAlarmId(null)}
                  className="text-slate-400 hover:text-white transition-colors p-2"
                >
                  <XCircle className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="overflow-y-auto p-6" style={{ maxHeight: 'calc(85vh - 100px)' }}>
              {loadingAudit ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
                  <span className="ml-3 text-slate-300">Loading audit trail...</span>
                </div>
              ) : auditRecords.length === 0 ? (
                <div className="text-center py-12">
                  <FileText className="w-12 h-12 text-slate-600 mx-auto mb-3" />
                  <p className="text-slate-400">No audit records found for this alarm.</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Timeline */}
                  <div className="relative">
                    {auditRecords.map((record, index) => {
                      const isLast = index === auditRecords.length - 1;
                      
                      // Action type colors
                      const actionConfig = {
                        RAISED: { bg: 'bg-red-900/40', border: 'border-red-500', text: 'text-red-400', icon: AlertCircle },
                        ACKNOWLEDGED: { bg: 'bg-blue-900/40', border: 'border-blue-500', text: 'text-blue-400', icon: CheckCircle },
                        CLEARED: { bg: 'bg-green-900/40', border: 'border-green-500', text: 'text-green-400', icon: CheckCircle },
                        SUPPRESSED: { bg: 'bg-orange-900/40', border: 'border-orange-500', text: 'text-orange-400', icon: XCircle },
                      }[record.action_type] || { bg: 'bg-slate-900/40', border: 'border-slate-500', text: 'text-slate-400', icon: Bell };
                      
                      const ActionIcon = actionConfig.icon;

                      return (
                        <div key={record.audit_id} className="relative flex gap-4 pb-6">
                          {/* Timeline Line */}
                          {!isLast && (
                            <div className="absolute left-[15px] top-10 bottom-0 w-0.5 bg-slate-700" />
                          )}
                          
                          {/* Icon */}
                          <div className={cn(
                            "relative z-10 flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
                            actionConfig.bg,
                            "border-2",
                            actionConfig.border
                          )}>
                            <ActionIcon className={cn("w-4 h-4", actionConfig.text)} />
                          </div>

                          {/* Content Card */}
                          <div className={cn(
                            "flex-1 rounded-lg border-2 p-4",
                            actionConfig.bg,
                            actionConfig.border
                          )}>
                            {/* Header */}
                            <div className="flex items-start justify-between mb-2">
                              <div>
                                <div className="flex items-center gap-2 mb-1">
                                  <span className={cn("text-sm font-bold uppercase", actionConfig.text)}>
                                    {record.action_type}
                                  </span>
                                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-black/30 text-slate-300">
                                    {record.priority_label}
                                  </span>
                                </div>
                                <p className="text-xs text-slate-400">
                                  Event Time: {new Date(record.action_timestamp).toLocaleString()}
                                  {record.response_time_seconds && (
                                    <span className="ml-2 text-amber-400 font-semibold">
                                      ⏱ Response: {Math.floor(record.response_time_seconds / 60)}m {Math.floor(record.response_time_seconds % 60)}s
                                    </span>
                                  )}
                                </p>
                              </div>
                              
                              {/* State Change Badge */}
                              {record.previous_state && (
                                <div className="text-xs font-mono px-2 py-1 rounded bg-black/40 text-slate-300">
                                  {record.previous_state} → {record.new_state}
                                </div>
                              )}
                            </div>

                            {/* Details Grid */}
                            <div className="grid grid-cols-2 gap-3 text-xs">
                              <div>
                                <span className="text-slate-400">Action:</span>
                                <span className="ml-2 text-white font-semibold uppercase">{record.action_type}</span>
                              </div>
                              <div>
                                <span className="text-slate-400">Event Time:</span>
                                <span className="ml-2 text-white">{new Date(record.action_timestamp).toLocaleString()}</span>
                              </div>
                              <div>
                                <span className="text-slate-400">Performed By:</span>
                                <span className="ml-2 text-white font-semibold">{record.performed_by}</span>
                              </div>
                              <div>
                                <span className="text-slate-400">Tag:</span>
                                <span className="ml-2 text-amber-400 font-mono">{record.tag_name || record.tag_id}</span>
                              </div>
                              
                              {record.equipment && (
                                <div>
                                  <span className="text-slate-400">Equipment:</span>
                                  <span className="ml-2 text-white">{record.equipment}</span>
                                </div>
                              )}
                              
                              {record.area && (
                                <div>
                                  <span className="text-slate-400">Area:</span>
                                  <span className="ml-2 text-white">{record.area}</span>
                                </div>
                              )}
                              
                              {record.alarm_actual_value !== null && record.alarm_actual_value !== undefined && (
                                <div>
                                  <span className="text-slate-400">Value:</span>
                                  <span className="ml-2 text-white font-mono">{record.alarm_actual_value.toFixed(2)}</span>
                                </div>
                              )}
                              
                              {record.alarm_setpoint !== null && record.alarm_setpoint !== undefined && (
                                <div>
                                  <span className="text-slate-400">Setpoint:</span>
                                  <span className="ml-2 text-white font-mono">{record.alarm_setpoint.toFixed(2)}</span>
                                </div>
                              )}
                            </div>

                            {/* Reason and Notes */}
                            {record.action_reason && (
                              <div className="mt-3 pt-3 border-t border-slate-700/50">
                                <p className="text-xs text-slate-400 mb-1">Reason:</p>
                                <p className="text-sm text-white">{record.action_reason}</p>
                              </div>
                            )}
                            
                            {record.action_notes && (
                              <div className="mt-2">
                                <p className="text-xs text-slate-400 mb-1">Notes:</p>
                                <p className="text-sm text-slate-300 italic">{record.action_notes}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {/* ── Suppress Modal ──────────────────────────────────────── */}
      {suppressModalAlarm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setSuppressModalAlarm(null)}>
          <div className="bg-slate-800 border-2 border-purple-600 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-4">
              <Bell className="w-5 h-5 text-purple-400" />
              <h3 className="text-lg font-bold text-white">Suppress Alarm</h3>
            </div>
            <p className="text-sm text-slate-300 mb-1 font-mono text-amber-300">{suppressModalAlarm.tag_name}</p>
            <p className="text-xs text-slate-400 mb-4">Alarm will be hidden from the active panel for the selected duration.</p>

            {/* Duration */}
            <div className="mb-4">
              <label className="block text-sm font-semibold text-white mb-2">Duration <span className="text-red-400">*</span></label>
              <div className="flex flex-wrap gap-2">
                {([0.25, 0.5, 1, 4, 8, 24] as const).map(h => (
                  <button key={h}
                    onClick={() => setSuppressDuration(h)}
                    className={cn("px-3 py-1.5 rounded text-sm font-bold border transition-all",
                      suppressDuration === h ? "bg-purple-700 border-purple-400 text-white" : "bg-slate-700 border-slate-500 text-slate-300 hover:border-purple-500"
                    )}
                  >{h === 0.25 ? '15m' : h === 0.5 ? '30m' : `${h}h`}</button>
                ))}
              </div>
              <p className="text-xs text-orange-400 mt-1">⚠ Maximum suppression is 24 hours. Indefinite suppression is not permitted.</p>
            </div>

            {/* Reason */}
            <div className="mb-4">
              <label className="block text-sm font-semibold text-white mb-2">Reason <span className="text-red-400">*</span></label>
              <select value={suppressReason} onChange={e => setSuppressReason(e.target.value)}
                className="w-full bg-slate-700 text-white border border-slate-600 rounded px-3 py-2 focus:border-purple-500 focus:outline-none">
                <option value="">-- Select Reason --</option>
                <option value="Engineering Test">Engineering Test</option>
                <option value="Planned Maintenance">Planned Maintenance</option>
                <option value="Sensor Fault">Sensor Fault</option>
                <option value="Process Upset">Process Upset</option>
                <option value="Nuisance Alarm">Nuisance Alarm</option>
                <option value="Other">Other (see notes)</option>
              </select>
            </div>

            {/* Notes */}
            <div className="mb-5">
              <label className="block text-sm font-semibold text-white mb-2">Notes <span className="text-slate-400">(Optional)</span></label>
              <textarea value={suppressNotes} onChange={e => setSuppressNotes(e.target.value)}
                placeholder="Additional context..."
                className="w-full bg-slate-700 text-white border border-slate-600 rounded px-3 py-2 h-16 resize-none focus:border-purple-500 focus:outline-none text-sm" />
            </div>

            <div className="flex gap-3">
              <button onClick={submitSuppressAlarm}
                disabled={!suppressReason || suppressing === suppressModalAlarm.id}
                className="flex-1 px-4 py-2 rounded font-bold text-sm bg-purple-700 hover:bg-purple-600 text-white border-2 border-purple-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed">
                {suppressing === suppressModalAlarm.id ? 'Suppressing…' : 'Suppress'}
              </button>
              <button onClick={() => setSuppressModalAlarm(null)}
                className="flex-1 px-4 py-2 rounded font-bold text-sm bg-slate-700 hover:bg-slate-600 text-white border-2 border-slate-600 transition-all">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Suppressed Alarms Section ───────────────────────────── */}
      {suppressedAlarms.length > 0 && (
        <div className="mt-2 border border-purple-700/50 rounded-lg overflow-hidden">
          <button
            onClick={() => setShowSuppressed(s => !s)}
            className="w-full flex items-center justify-between px-3 py-1.5 bg-purple-950/60 hover:bg-purple-900/60 text-purple-300 text-[10px] font-bold uppercase tracking-wider transition-all"
          >
            <span>⊘ Suppressed ({suppressedAlarms.length})</span>
            <span>{showSuppressed ? '▲' : '▼'}</span>
          </button>
          {showSuppressed && (
            <div className="divide-y divide-purple-900/40">
              {suppressedAlarms.map(s => (
                <div key={s.audit_id} className="flex items-center gap-2 px-3 py-2 bg-purple-950/30">
                  <div className="flex-1 min-w-0">
                    <span className="font-mono text-[10px] font-bold text-amber-400">{s.tag_name}</span>
                    {s.alarm_level && <span className="ml-1.5 text-[9px] text-purple-300 border border-purple-600 px-1 rounded">{s.alarm_level}</span>}
                    <div className="text-[9px] text-slate-400 mt-0.5">
                      {s.reason} · by <span className="text-purple-300">{s.suppressed_by}</span> · {formatTimestamp(s.suppressed_at)}
                      {s.suppress_until ? ` → until ${formatTimestamp(s.suppress_until)}` : ''}
                    </div>
                  </div>
                  <button
                    onClick={() => handleUnsuppress(s.event_id)}
                    className="text-[9px] font-bold px-2 py-1 rounded bg-purple-800 hover:bg-purple-700 text-white border border-purple-500 whitespace-nowrap transition-all"
                  >
                    Restore
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
