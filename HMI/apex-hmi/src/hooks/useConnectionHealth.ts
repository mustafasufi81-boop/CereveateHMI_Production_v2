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
    if (!h.socketConnected && h.reconnectAttempts > 0)
        return `OPC backend (C# service on port 5001) disconnected — reconnecting (attempt ${h.reconnectAttempts})…`;
    if (!h.socketConnected)
        return 'OPC backend (C# service on port 5001) not connected — waiting for server…';
    if (h.flaskReachable === false)
        return 'Flask backend (port 6001) is not reachable — data may be stale';
    if (h.dataIsStale && h.lastDataReceivedAt !== null)
        return 'No OPC data received for >15 s — check C# OPC service and SignalR connection';
    if (h.dataIsStale && h.lastDataReceivedAt === null)
        return 'Connected but no OPC data yet — waiting for first tag update…';
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
