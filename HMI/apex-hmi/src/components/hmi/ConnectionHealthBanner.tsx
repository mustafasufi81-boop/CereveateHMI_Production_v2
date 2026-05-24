/**
 * ConnectionHealthBanner
 * Floating banner shown at the top of the screen whenever the MQTT / Flask
 * data pipeline has a problem.  Disappears automatically when everything is OK.
 */
import React, { useEffect, useState } from 'react';
import { useConnectionHealth } from '@/hooks/useConnectionHealth';
import { WifiOff, RefreshCw, AlertTriangle, CheckCircle } from 'lucide-react';

const BANNER_Z = 9999;

/** milliseconds to keep the "all clear" flash visible before hiding the banner */
const ALL_CLEAR_FLASH_MS = 4_000;

export const ConnectionHealthBanner: React.FC = () => {
    const health = useConnectionHealth();
    const [showAllClear, setShowAllClear] = useState(false);
    const [prevProblem, setPrevProblem] = useState<string | null>(null);
    const [reconnecting, setReconnecting] = useState(false);
    const [lastDataLabel, setLastDataLabel] = useState('');

    // Update "X s ago" label every second when stale
    useEffect(() => {
        if (!health.dataIsStale) return;
        const id = setInterval(() => {
            const secs = health.secondsSinceData ?? 0;
            setLastDataLabel(secs < 60 ? `${secs}s ago` : `${Math.floor(secs / 60)}m ${secs % 60}s ago`);
        }, 1_000);
        return () => clearInterval(id);
    }, [health.dataIsStale, health.secondsSinceData]);

    // Flash "all clear" when a problem resolves
    useEffect(() => {
        if (prevProblem !== null && health.problem === null) {
            setShowAllClear(true);
            const t = setTimeout(() => setShowAllClear(false), ALL_CLEAR_FLASH_MS);
            setPrevProblem(null);
            return () => clearTimeout(t);
        }
        if (health.problem !== null) {
            setPrevProblem(health.problem);
        }
    }, [health.problem]);

    const handleReconnect = () => {
        setReconnecting(true);
        health.forceReconnect();
        setTimeout(() => setReconnecting(false), 3_000);
    };

    // Nothing to show
    if (!health.problem && !showAllClear) return null;

    // ── All-clear flash ────────────────────────────────────────────────────
    if (showAllClear) {
        return (
            <div style={{
                position: 'fixed', bottom: 16, left: '50%', transform: 'translateX(-50%)',
                zIndex: BANNER_Z,
                background: '#0d3320', border: '1px solid #00c851',
                borderRadius: 20, padding: '4px 16px',
                display: 'inline-flex', alignItems: 'center', gap: 7,
                fontFamily: 'Consolas, monospace', fontSize: 11, color: '#00c851',
                boxShadow: '0 2px 10px rgba(0,200,81,0.25)',
                whiteSpace: 'nowrap',
                animation: 'slideUp 0.25s ease',
            }}>
                <CheckCircle size={13} />
                <span>Connection restored</span>
            </div>
        );
    }

    // ── Problem banner ─────────────────────────────────────────────────────
    const isHard = !health.socketConnected || health.flaskReachable === false;
    const bg        = isHard ? '#2d0a0a' : '#2d1f00';
    const border    = isHard ? '#ff3b3b' : '#ffaa00';
    const textColor = isHard ? '#ff6b6b' : '#ffcc44';

    return (
        <div style={{
            position: 'fixed', bottom: 16, left: '50%', transform: 'translateX(-50%)',
            zIndex: BANNER_Z,
            background: bg, border: `1px solid ${border}`,
            borderRadius: 20, padding: '4px 14px',
            display: 'inline-flex', alignItems: 'center', gap: 8,
            fontFamily: 'Consolas, monospace', fontSize: 11, color: textColor,
            boxShadow: `0 2px 12px rgba(0,0,0,0.5)`,
            whiteSpace: 'nowrap', maxWidth: '90vw',
        }}>
            {isHard
                ? <WifiOff size={13} style={{ flexShrink: 0 }} />
                : <AlertTriangle size={13} style={{ flexShrink: 0 }} />}
            <span style={{ fontWeight: 700 }}>
                {isHard ? 'CONNECTION LOST' : 'WARNING'}
            </span>
            {health.dataIsStale && lastDataLabel && (
                <span style={{ opacity: 0.7 }}>· {lastDataLabel}</span>
            )}
            {health.reconnectAttempts > 0 && (
                <span style={{ opacity: 0.6 }}>· #{health.reconnectAttempts}</span>
            )}
            <button
                onClick={handleReconnect}
                disabled={reconnecting}
                style={{
                    display: 'flex', alignItems: 'center', gap: 4,
                    padding: '2px 8px', cursor: reconnecting ? 'default' : 'pointer',
                    background: 'rgba(255,255,255,0.12)', border: `1px solid ${border}`,
                    borderRadius: 10, color: textColor,
                    fontFamily: 'Consolas, monospace', fontSize: 10, fontWeight: 700,
                    opacity: reconnecting ? 0.6 : 1, marginLeft: 4,
                }}
            >
                <RefreshCw size={10} style={{ animation: reconnecting ? 'spin 1s linear infinite' : undefined }} />
                {reconnecting ? '…' : 'Retry'}
            </button>
        </div>
    );
};

export default ConnectionHealthBanner;
