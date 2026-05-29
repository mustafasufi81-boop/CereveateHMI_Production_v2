/**
 * useConnectionHealth
 * Subscribes to mqttWebSocketService health events and returns a reactive
 * health object.  Also exposes a `forceReconnect()` action.
 */
import { useEffect, useState, useCallback } from 'react';
import mqttWebSocketService, { type MQTTHealth } from '@/services/mqtt-websocket';

export interface ConnectionHealth extends MQTTHealth {
    /** Human-readable summary of the worst problem, or null if everything is OK */
    problem: string | null;
    /** Seconds since last data received, or null if never received */
    secondsSinceData: number | null;
}

function buildProblem(h: MQTTHealth): string | null {
    // RED: No connection at all
    if (!h.socketConnected)
        return 'System Reconnecting';
    
    // ORANGE: Connected but using fallback (Flask unreachable or data stale)
    if (h.flaskReachable === false)
        return 'Using Backup Connection';
    if (h.dataIsStale)
        return 'Data Update Delayed';
    
    // GREEN: All good
    return null;
}

export function useConnectionHealth(): ConnectionHealth & { forceReconnect: () => void } {
    const [health, setHealth] = useState<MQTTHealth>(mqttWebSocketService.getHealth());

    useEffect(() => {
        const unsub = mqttWebSocketService.onHealthChange(setHealth);
        return unsub;
    }, []);

    const forceReconnect = useCallback(() => {
        mqttWebSocketService.forceReconnect();
    }, []);

    const secondsSinceData = health.lastDataReceivedAt
        ? Math.floor((Date.now() - health.lastDataReceivedAt) / 1000)
        : null;

    return {
        ...health,
        problem: buildProblem(health),
        secondsSinceData,
        forceReconnect,
    };
}
