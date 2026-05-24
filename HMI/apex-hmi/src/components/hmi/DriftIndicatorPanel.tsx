/**
 * DriftIndicatorPanel
 * ===================
 * Displays long-term baseline drift alerts per tag.
 * Three detection methods shown with individual badges:
 *   CUSUM   — cumulative sum (slow monotonic drift)
 *   EWMA    — exponentially weighted MA (gradual degradation)
 *   Z-SCORE — rolling standardised score (step changes)
 *
 * Severity colour coding follows ISA-18.2:
 *   critical → red    (act now)
 *   warning  → amber  (investigate within 24 h)
 *   info     → cyan   (watch — trend is moving)
 */

import { useState, useEffect, useCallback } from "react";

// Base URL: honour VITE_API_URL env var when set (e.g. in production builds),
// otherwise fall back to the known Flask origin used across all HMI panels.
const API = (import.meta.env.VITE_API_URL ?? 'http://localhost:6001').replace(/\/$/, '') + '/api';

// ── Types ─────────────────────────────────────────────────────────────────────
interface DriftAlert {
  id: number;
  tag_id: string;
  method: 'cusum' | 'ewma' | 'zscore';
  severity: 'info' | 'warning' | 'critical';
  direction: 'UP' | 'DOWN';
  baseline_mean: number;
  baseline_std: number;
  current_mean: number;
  drift_magnitude: number;
  drift_pct: number;
  cusum_score?: number;
  ewma_value?: number;
  consecutive_hours: number;
  is_active: boolean;
  acknowledged: boolean;
  acknowledged_by?: string;
  acknowledged_at?: string;
  started_at: string;
  last_updated: string;
  resolved_at?: string;
  eval_window_hours: number;
  baseline_days: number;
}

interface DriftStatus {
  running: boolean;
  cycle_count: number;
  last_run_at?: string;
  last_error?: string;
  tags_checked: number;
  alerts_active: number;
  interval_sec: number;
  methods: string[];
  config: {
    baseline_days: number;
    eval_window_hours: number;
    zscore_threshold: number;
    severity_thresholds: { info: number; warning: number; critical: number };
  };
}

// ── Colour helpers ────────────────────────────────────────────────────────────
const SEV_COLORS = {
  critical: { bg: 'rgba(255,68,68,0.15)',  border: '#FF4444', text: '#FF6B6B', dot: '#FF4444' },
  warning:  { bg: 'rgba(255,179,0,0.12)',  border: '#FFB300', text: '#FFCC40', dot: '#FFB300' },
  info:     { bg: 'rgba(0,200,200,0.10)',  border: '#00C8C8', text: '#4DD9D9', dot: '#00C8C8' },
};

const METHOD_COLORS: Record<string, string> = {
  cusum:  '#A78BFA',  // purple
  ewma:   '#34D399',  // green
  zscore: '#60A5FA',  // blue
};

const METHOD_LABELS: Record<string, string> = {
  cusum:  'CUSUM',
  ewma:   'EWMA',
  zscore: 'Z-SCORE',
};

const METHOD_DESC: Record<string, string> = {
  cusum:  'Cumulative sum — best for slow monotonic drift (bearing wear, fouling)',
  ewma:   'Exponential weighted MA — best for gradual degradation',
  zscore: 'Rolling Z-score — best for step changes and instrument drift',
};

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('token') || sessionStorage.getItem('token') || '';
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch(path: string, opts?: RequestInit) {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders(), ...opts?.headers },
  });
  if (!res.ok) {
    // Surface the HTTP status so callers can show a meaningful message
    // instead of a cryptic JSON parse error on HTML error pages.
    throw new Error(`HTTP ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MethodBadge({ method }: { method: string }) {
  return (
    <span title={METHOD_DESC[method]} style={{
      fontSize: '9px', fontWeight: 700, letterSpacing: '0.6px',
      padding: '2px 6px', borderRadius: '3px',
      border: `1px solid ${METHOD_COLORS[method]}`,
      color: METHOD_COLORS[method],
      backgroundColor: `${METHOD_COLORS[method]}18`,
      fontFamily: 'Consolas, monospace',
      cursor: 'help',
    }}>
      {METHOD_LABELS[method] ?? method.toUpperCase()}
    </span>
  );
}

function SeverityDot({ severity }: { severity: string }) {
  const c = SEV_COLORS[severity as keyof typeof SEV_COLORS] ?? SEV_COLORS.info;
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8,
      borderRadius: '50%', backgroundColor: c.dot,
      boxShadow: `0 0 6px ${c.dot}`,
      flexShrink: 0,
    }} />
  );
}

function MagnitudeBar({ pct, severity }: { pct: number; severity: string }) {
  const c = SEV_COLORS[severity as keyof typeof SEV_COLORS] ?? SEV_COLORS.info;
  const fill = Math.min(pct, 100);
  return (
    <div style={{ background: '#1a1a1a', borderRadius: 2, height: 4, width: '100%' }}>
      <div style={{
        width: `${fill}%`, height: '100%', borderRadius: 2,
        backgroundColor: c.dot,
        transition: 'width 0.4s',
        boxShadow: `0 0 4px ${c.dot}`,
      }} />
    </div>
  );
}

function DriftAlertCard({
  alert, onAck, ackingId
}: { alert: DriftAlert; onAck: (id: number) => void; ackingId: number | null }) {
  const c = SEV_COLORS[alert.severity] ?? SEV_COLORS.info;
  const dir = alert.direction === 'UP' ? '▲' : '▼';
  const dirColor = alert.direction === 'UP' ? '#FF6B6B' : '#60A5FA';
  const hours = alert.consecutive_hours;
  const age = hours < 24
    ? `${hours}h`
    : `${Math.floor(hours / 24)}d ${hours % 24}h`;

  return (
    <div style={{
      backgroundColor: c.bg,
      border: `1px solid ${c.border}`,
      borderRadius: 6,
      padding: '10px 12px',
      marginBottom: 8,
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <SeverityDot severity={alert.severity} />
        <span style={{
          color: '#E5E5E5', fontWeight: 700, fontSize: 12,
          fontFamily: 'Consolas, monospace', flex: 1,
        }}>
          {alert.tag_id}
        </span>
        <MethodBadge method={alert.method} />
        <span style={{ color: c.text, fontSize: 10, fontWeight: 700 }}>
          {alert.severity.toUpperCase()}
        </span>
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: 20, marginBottom: 6, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 10, color: '#9CA3AF' }}>
          <span style={{ color: '#6B7280' }}>Baseline: </span>
          <span style={{ color: '#E5E5E5' }}>{alert.baseline_mean.toFixed(2)}</span>
          <span style={{ color: '#6B7280' }}> ±{alert.baseline_std.toFixed(2)}</span>
        </div>
        <div style={{ fontSize: 10, color: '#9CA3AF' }}>
          <span style={{ color: '#6B7280' }}>Current: </span>
          <span style={{ color: '#E5E5E5' }}>{alert.current_mean.toFixed(2)}</span>
        </div>
        <div style={{ fontSize: 10 }}>
          <span style={{ color: '#6B7280' }}>Shift: </span>
          <span style={{ color: dirColor, fontWeight: 700 }}>
            {dir} {alert.drift_magnitude.toFixed(2)}
          </span>
          <span style={{ color: '#6B7280' }}> ({alert.drift_pct.toFixed(0)}%σ)</span>
        </div>
        <div style={{ fontSize: 10, color: '#6B7280' }}>
          Active: <span style={{ color: '#D1D5DB' }}>{age}</span>
        </div>
        {alert.cusum_score != null && (
          <div style={{ fontSize: 10, color: '#6B7280' }}>
            CUSUM: <span style={{ color: '#A78BFA' }}>{alert.cusum_score.toFixed(2)}</span>
          </div>
        )}
        {alert.ewma_value != null && (
          <div style={{ fontSize: 10, color: '#6B7280' }}>
            EWMA: <span style={{ color: '#34D399' }}>{alert.ewma_value.toFixed(2)}</span>
          </div>
        )}
      </div>

      {/* Magnitude bar */}
      <div style={{ marginBottom: 6 }}>
        <MagnitudeBar pct={Math.min(alert.drift_pct, 100)} severity={alert.severity} />
      </div>

      {/* Footer row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 9, color: '#4B5563' }}>
          Started: {new Date(alert.started_at).toLocaleString()}
          {alert.acknowledged && (
            <span style={{ color: '#34D399', marginLeft: 8 }}>
              ✓ Ack'd by {alert.acknowledged_by}
            </span>
          )}
        </span>
        {!alert.acknowledged && (
          <button
            onClick={() => onAck(alert.id)}
            disabled={ackingId !== null}
            style={{
              fontSize: 9, padding: '2px 8px',
              cursor: ackingId !== null ? 'not-allowed' : 'pointer',
              backgroundColor: 'transparent',
              border: `1px solid ${c.border}`,
              borderRadius: 3,
              color: ackingId === alert.id ? '#6B7280' : c.text,
              opacity: ackingId !== null ? 0.6 : 1,
              fontFamily: 'Consolas, monospace',
            }}
          >
            {ackingId === alert.id ? '…' : 'ACK'}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Method legend / explainer ─────────────────────────────────────────────────
function MethodLegend() {
  return (
    <div style={{
      backgroundColor: '#111827', border: '1px solid #1F2937',
      borderRadius: 6, padding: '10px 14px', marginBottom: 12,
    }}>
      <div style={{ fontSize: 10, color: '#6B7280', marginBottom: 6, letterSpacing: '0.5px' }}>
        DETECTION METHODS
      </div>
      {Object.entries(METHOD_DESC).map(([m, desc]) => (
        <div key={m} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
          <MethodBadge method={m} />
          <span style={{ fontSize: 10, color: '#6B7280', lineHeight: 1.4 }}>{desc}</span>
        </div>
      ))}
      <div style={{ marginTop: 8, fontSize: 9, color: '#374151' }}>
        Evaluation: last 1h vs 30-day rolling baseline &nbsp;·&nbsp;
        <span style={{ color: SEV_COLORS.info.text }}>INFO ≥1.5σ</span> &nbsp;·&nbsp;
        <span style={{ color: SEV_COLORS.warning.text }}>WARN ≥2.5σ</span> &nbsp;·&nbsp;
        <span style={{ color: SEV_COLORS.critical.text }}>CRIT ≥4σ</span>
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function last_run_str(status: DriftStatus | null): string {
  if (!status?.last_run_at) return 'Never run';
  const d = new Date(status.last_run_at);
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1)  return 'Updated just now';
  if (mins < 60) return `Updated ${mins}m ago`;
  return `Updated ${Math.floor(mins / 60)}h ago`;
}

// ── Main component ────────────────────────────────────────────────────────────
export default function DriftIndicatorPanel() {
  const [alerts,  setAlerts]  = useState<DriftAlert[]>([]);
  const [status,  setStatus]  = useState<DriftStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [filter,  setFilter]  = useState<'all' | 'critical' | 'warning' | 'info'>('all');
  const [showResolved, setShowResolved] = useState(false);
  const [ackingId, setAckingId] = useState<number | null>(null);
  const [cycleError, setCycleError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [alertsRes, statusRes] = await Promise.all([
        apiFetch(`/predictive/drift/alerts?include_resolved=${showResolved}`),
        apiFetch('/predictive/drift/status'),
      ]);
      if (alertsRes.success) setAlerts(alertsRes.data ?? []);
      if (statusRes.success) setStatus(statusRes.data);
    } catch (e: any) {
      setError(e.message ?? 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [showResolved]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  const handleAck = async (id: number) => {
    if (ackingId !== null) return;   // guard against double-click
    setAckingId(id);
    try {
      await apiFetch(`/predictive/drift/alerts/${id}/ack`, { method: 'POST' });
      await load();
    } catch (e: any) {
      setError(`ACK failed: ${e.message}`);
    } finally {
      setAckingId(null);
    }
  };

  const handleForceCycle = async () => {
    setCycleError(null);
    try {
      await apiFetch('/predictive/drift/engine/cycle', { method: 'POST' });
      setTimeout(load, 1000);
    } catch (e: any) {
      setCycleError(e.message);
    }
  };

  const filtered = filter === 'all'
    ? alerts
    : alerts.filter(a => a.severity === filter);

  const counts = {
    critical: alerts.filter(a => a.severity === 'critical' && a.is_active).length,
    warning:  alerts.filter(a => a.severity === 'warning'  && a.is_active).length,
    info:     alerts.filter(a => a.severity === 'info'     && a.is_active).length,
  };

  // Group by tag for compact view
  const byTag = filtered.reduce<Record<string, DriftAlert[]>>((acc, a) => {
    (acc[a.tag_id] ??= []).push(a);
    return acc;
  }, {});

  return (
    <div style={{
      padding: 16, fontFamily: 'Consolas, monospace',
      backgroundColor: '#0d1117', minHeight: '100%', color: '#E5E5E5',
    }}>

      {/* ── Status bar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        backgroundColor: '#111827', border: '1px solid #1F2937',
        borderRadius: 6, padding: '8px 12px', marginBottom: 12,
        flexWrap: 'wrap',
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          backgroundColor: status?.running ? '#00C851' : '#FF4444',
          boxShadow: status?.running ? '0 0 6px #00C851' : 'none',
          flexShrink: 0, display: 'inline-block',
        }} />
        <span style={{ fontSize: 10, color: '#9CA3AF' }}>
          DRIFT DETECTOR &nbsp;·&nbsp;
          {status?.running ? 'RUNNING' : 'STOPPED'} &nbsp;·&nbsp;
          Cycle #{status?.cycle_count ?? 0} &nbsp;·&nbsp;
          {status?.tags_checked ?? 0} tags &nbsp;·&nbsp;
          {status?.interval_sec ? `${status.interval_sec / 60}min interval` : ''}
        </span>

        {/* Severity counters */}
        {counts.critical > 0 && (
          <span style={{ padding: '2px 8px', borderRadius: 3, fontSize: 10, fontWeight: 700,
            backgroundColor: 'rgba(255,68,68,0.2)', color: '#FF6B6B', border: '1px solid #FF4444' }}>
            {counts.critical} CRITICAL
          </span>
        )}
        {counts.warning > 0 && (
          <span style={{ padding: '2px 8px', borderRadius: 3, fontSize: 10, fontWeight: 700,
            backgroundColor: 'rgba(255,179,0,0.15)', color: '#FFCC40', border: '1px solid #FFB300' }}>
            {counts.warning} WARNING
          </span>
        )}
        {counts.info > 0 && (
          <span style={{ padding: '2px 8px', borderRadius: 3, fontSize: 10,
            backgroundColor: 'rgba(0,200,200,0.1)', color: '#4DD9D9', border: '1px solid #00C8C8' }}>
            {counts.info} INFO
          </span>
        )}

        <div style={{ flex: 1 }} />

        <button onClick={handleForceCycle} title={cycleError ?? undefined} style={{
          fontSize: 9, padding: '3px 10px', cursor: 'pointer',
          backgroundColor: 'transparent', border: '1px solid #374151',
          borderRadius: 3, color: cycleError ? '#FF6B6B' : '#9CA3AF',
        }}>⚡ {cycleError ? 'CYCLE FAILED' : 'FORCE CYCLE'}</button>

        <button onClick={load} style={{
          fontSize: 9, padding: '3px 10px', cursor: 'pointer',
          backgroundColor: 'transparent', border: '1px solid #374151',
          borderRadius: 3, color: '#9CA3AF',
        }}>↻ REFRESH</button>
      </div>

      {/* ── Method legend ── */}
      <MethodLegend />

      {/* ── Filters ── */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12, alignItems: 'center' }}>
        {(['all', 'critical', 'warning', 'info'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            fontSize: 9, padding: '3px 10px', cursor: 'pointer',
            fontFamily: 'Consolas, monospace', borderRadius: 3,
            border: `1px solid ${filter === f ? '#3B82F6' : '#374151'}`,
            backgroundColor: filter === f ? 'rgba(59,130,246,0.15)' : 'transparent',
            color: filter === f ? '#60A5FA' : '#6B7280',
          }}>
            {f.toUpperCase()}
            {f !== 'all' && counts[f] != null && ` (${counts[f as keyof typeof counts]})`}
          </button>
        ))}
        <label style={{ fontSize: 9, color: '#6B7280', marginLeft: 8, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={showResolved}
            onChange={e => setShowResolved(e.target.checked)}
            style={{ marginRight: 4 }}
          />
          Show resolved
        </label>
        <span style={{ fontSize: 9, color: '#4B5563', marginLeft: 'auto' }}>
          {last_run_str(status)}
        </span>
      </div>

      {/* ── Content ── */}
      {loading && (
        <div style={{ color: '#6B7280', fontSize: 11, padding: 20, textAlign: 'center' }}>
          Loading drift alerts…
        </div>
      )}

      {!loading && error && (
        <div style={{ color: '#FF6B6B', fontSize: 11, padding: 12,
          backgroundColor: 'rgba(255,68,68,0.1)', borderRadius: 4, border: '1px solid #FF4444' }}>
          ⚠ {error}
        </div>
      )}

      {!loading && !error && Object.keys(byTag).length === 0 && (
        <div style={{
          textAlign: 'center', padding: '40px 20px',
          color: '#374151', fontSize: 11,
        }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>
          <div>No drift alerts {filter !== 'all' ? `(${filter})` : ''}.</div>
          <div style={{ fontSize: 10, color: '#1F2937', marginTop: 4 }}>
            {showResolved
              ? 'All tags are within baseline.'
              : 'All tags stable — no active drift detected.'}
          </div>
          {!status?.running && (
            <div style={{ fontSize: 10, color: '#FFB300', marginTop: 8 }}>
              ⚠ Drift detector is not running. Click FORCE CYCLE to evaluate.
            </div>
          )}
        </div>
      )}

      {!loading && !error && Object.entries(byTag).map(([tagId, tagAlerts]) => (
        <div key={tagId} style={{ marginBottom: 16 }}>
          <div style={{
            fontSize: 10, color: '#4B5563', letterSpacing: '0.5px',
            marginBottom: 6, borderBottom: '1px solid #1F2937', paddingBottom: 4,
          }}>
            TAG: <span style={{ color: '#9CA3AF' }}>{tagId}</span>
            &nbsp;·&nbsp;{tagAlerts.length} method{tagAlerts.length > 1 ? 's' : ''} detecting
          </div>
          {tagAlerts.map(alert => (
            <DriftAlertCard key={alert.id} alert={alert} onAck={handleAck} ackingId={ackingId} />
          ))}
        </div>
      ))}
    </div>
  );
}
