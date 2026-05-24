import { io, Socket } from 'socket.io-client';

// Connect directly to Flask on port 6001 (CORS is * on the server).
// No Vite proxy needed — avoids WS upgrade proxy issues.
const SOCKET_URL = import.meta.env.VITE_WS_URL || window.location.origin.replace(/^http/, 'ws').replace(':8090', ':6001');

// Base HTTP URL for health checks — direct to Flask, NOT through Vite proxy.
// Override via VITE_FLASK_URL env var for production deployments.
const FLASK_BASE: string = import.meta.env.VITE_FLASK_URL
    || window.location.origin.replace(':8090', ':6001');

// How long without any data/heartbeat before we mark the data feed as stale (ms)
const STALE_DATA_THRESHOLD_MS = 60_000;  // 60s — quiet plant won't trigger false alarm

export interface MQTTHealth {
    socketConnected: boolean;
    lastDataReceivedAt: number | null;   // epoch ms
    dataIsStale: boolean;
    reconnectAttempts: number;
    flaskReachable: boolean | null;      // null = not yet checked
    flaskLastCheckedAt: number | null;
}

type HealthChangeListener = (health: MQTTHealth) => void;

class MQTTWebSocketService {
    private socket: Socket | null = null;
    private listeners: Map<string, Function[]> = new Map();
    private connectionListeners: ((connected: boolean) => void)[] = [];
    private healthListeners: HealthChangeListener[] = [];

    // ── Health tracking ────────────────────────────────────────────────────
    private _health: MQTTHealth = {
        socketConnected: false,
        lastDataReceivedAt: null,
        dataIsStale: false,
        reconnectAttempts: 0,
        flaskReachable: null,
        flaskLastCheckedAt: null,
    };
    private _staleTimer: ReturnType<typeof setInterval> | null = null;
    private _flaskTimer: ReturnType<typeof setInterval> | null = null;
    private _flaskFailCount = 0;                         // consecutive health-check failures
    private readonly FLASK_FAIL_THRESHOLD = 3;           // require 3 consecutive fails before alarm

    private updateHealth(patch: Partial<MQTTHealth>) {
        this._health = { ...this._health, ...patch };
        this.healthListeners.forEach(cb => cb({ ...this._health }));
    }

    getHealth(): MQTTHealth {
        return { ...this._health };
    }

    onHealthChange(cb: HealthChangeListener): () => void {
        this.healthListeners.push(cb);
        cb({ ...this._health }); // fire immediately with current state
        return () => { this.healthListeners = this.healthListeners.filter(f => f !== cb); };
    }

    // ── Connection-change listeners (kept for backward compat) ─────────────
    onConnectionChange(cb: (connected: boolean) => void): () => void {
        this.connectionListeners.push(cb);
        return () => { this.connectionListeners = this.connectionListeners.filter(f => f !== cb); };
    }

    private notifyConnectionChange(connected: boolean) {
        this.connectionListeners.forEach(cb => cb(connected));
    }

    // ── Stale-data watchdog ────────────────────────────────────────────────
    private startStaleWatchdog() {
        if (this._staleTimer) return;
        this._staleTimer = setInterval(() => {
            const last = this._health.lastDataReceivedAt;
            const stale = last === null || (Date.now() - last) > STALE_DATA_THRESHOLD_MS;
            if (stale !== this._health.dataIsStale) {
                this.updateHealth({ dataIsStale: stale });
            }
        }, 3_000);
    }

    private stopStaleWatchdog() {
        if (this._staleTimer) { clearInterval(this._staleTimer); this._staleTimer = null; }
    }

    // ── Flask health ping (direct to :6001, not through Vite proxy) ─────────────────
    private startFlaskHealthCheck() {
        if (this._flaskTimer) return;
        const check = async () => {
            try {
                const r = await fetch(`${FLASK_BASE}/api/health`, {
                    method: 'GET',
                    signal: AbortSignal.timeout(5_000),
                });
                if (r.ok) {
                    if (this._flaskFailCount > 0) {
                        console.info(`[Health] Flask reachable again after ${this._flaskFailCount} failure(s)`);
                    }
                    this._flaskFailCount = 0;
                    this.updateHealth({ flaskReachable: true, flaskLastCheckedAt: Date.now() });
                } else {
                    this._flaskFailCount++;
                    console.warn(`[Health] Flask returned ${r.status} (fail #${this._flaskFailCount})`);
                }
            } catch (err) {
                this._flaskFailCount++;
                console.warn(`[Health] Flask ping failed (fail #${this._flaskFailCount}):`, err);
            }
            // Only mark down after FLASK_FAIL_THRESHOLD consecutive failures
            if (this._flaskFailCount >= this.FLASK_FAIL_THRESHOLD) {
                console.error(`[Health] Flask marked UNREACHABLE after ${this._flaskFailCount} consecutive failures`);
                this.updateHealth({ flaskReachable: false, flaskLastCheckedAt: Date.now() });
            }
        };
        check(); // immediate first check
        this._flaskTimer = setInterval(check, 30_000);
    }

    private stopFlaskHealthCheck() {
        if (this._flaskTimer) { clearInterval(this._flaskTimer); this._flaskTimer = null; }
    }

    // ── Main connect ───────────────────────────────────────────────────────
    connect() {
        if (this.socket?.connected) {
            console.log('Socket already connected');
            return;
        }

        console.log('🔌 Connecting to WebSocket:', SOCKET_URL);
        this.startStaleWatchdog();
        this.startFlaskHealthCheck();

        const token = localStorage.getItem('auth_token') || '';
        this.socket = io(SOCKET_URL, {
            transports: ['websocket'],       // websocket only — no polling fallback
            reconnection: true,
            reconnectionDelay: 1_000,
            reconnectionDelayMax: 15_000,
            reconnectionAttempts: Infinity,
            timeout: 180_000,                // must match server ping_timeout=180
            auth: { token },
        });

        this.socket.on('connect', () => {
            console.info('✅ [Socket] Connected', { id: this.socket?.id });
            this.updateHealth({ socketConnected: true, reconnectAttempts: 0 });
            this.notifyConnectionChange(true);
        });

        this.socket.on('disconnect', (reason) => {
            console.warn(`⚠️ [Socket] Disconnected | reason: ${reason}`);
            this.updateHealth({ socketConnected: false });
            this.notifyConnectionChange(false);
        });

        this.socket.io.on('reconnect_attempt', (attempt: number) => {
            console.info(`🔄 [Socket] Reconnect attempt #${attempt}`);
            this.updateHealth({ reconnectAttempts: attempt });
        });

        this.socket.io.on('reconnect', (attempt: number) => {
            console.info(`✅ [Socket] Reconnected after ${attempt} attempt(s)`);
            this.updateHealth({ socketConnected: true, reconnectAttempts: 0 });
            this.notifyConnectionChange(true);
        });

        this.socket.io.on('reconnect_failed', () => {
            console.error('❌ [Socket] All reconnect attempts exhausted');
        });

        this.socket.io.on('error', (err: Error) => {
            console.error('❌ [Socket] Transport error:', err?.message ?? err);
        });

        // ── Data events ───────────────────────────────────────────────────
        const trackAndEmit = (event: string, data: any) => {
            this.updateHealth({ lastDataReceivedAt: Date.now(), dataIsStale: false });
            this.emit(event, data);
        };

        this.socket.on('mqtt_tag_update',  (d: any) => trackAndEmit('mqtt_tag_update',  d));
        this.socket.on('mqtt_alarm',       (d: any) => trackAndEmit('mqtt_alarm',        d));
        this.socket.on('mqtt_interlock',   (d: any) => trackAndEmit('mqtt_interlock',    d));
        this.socket.on('tag_update',       (d: any) => trackAndEmit('tag_update',        d));

        // Server heartbeat — resets stale watchdog even when no tag values change.
        // Emitted every 30s by the Flask _heartbeat_emitter greenlet.
        this.socket.on('heartbeat', (_d: any) => {
            this.updateHealth({ lastDataReceivedAt: Date.now(), dataIsStale: false });
        });

        this.socket.on('connect_error', (error) => {
            console.error('❌ [Socket] Connection error:', error?.message ?? error);
            this.updateHealth({ socketConnected: false });
        });
    }

    disconnect() {
        this.stopStaleWatchdog();
        this.stopFlaskHealthCheck();
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
            this.listeners.clear();
        }
    }

    /** Force a manual reconnect (e.g. after user clicks "Reconnect" button) */
    forceReconnect() {
        console.log('🔄 Manual reconnect requested');
        this.disconnect();
        setTimeout(() => this.connect(), 500);
    }

    on(event: string, callback: Function) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event)?.push(callback);
    }

    off(event: string, callback: Function) {
        const listeners = this.listeners.get(event);
        if (listeners) {
            const index = listeners.indexOf(callback);
            if (index > -1) {
                listeners.splice(index, 1);
            }
        }
    }

    private emit(event: string, data: any) {
        const listeners = this.listeners.get(event);
        if (listeners) {
            listeners.forEach(callback => callback(data));
        }
    }

    isConnected(): boolean {
        return this.socket?.connected || false;
    }

    /**
     * Subscribe to MQTT tag updates for specific tag IDs.
     * @param tagIds - Array of tag IDs to watch (empty array = all tags)
     * @param callback - Called with {tagId: tagData} map whenever matching tags arrive
     * @returns unsubscribe function
     */
    subscribe(tagIds: string[], callback: (updates: Record<string, any>) => void): () => void {
        const handler = (data: any) => {
            // Payload from websocket_bridge: { tags: [{tag_id, value, quality, time, ...}] }
            const tagList: any[] = data.tags ?? (Array.isArray(data) ? data : []);
            if (tagList.length === 0) return;

            const updates: Record<string, any> = {};
            tagList.forEach((tag: any) => {
                const id = tag.tag_id ?? tag.id;
                if (!id) return;
                if (tagIds.length === 0 || tagIds.includes(id)) {
                    updates[id] = tag;
                }
            });

            if (Object.keys(updates).length > 0) {
                callback(updates);
            }
        };

        this.on('mqtt_tag_update', handler);
        return () => this.off('mqtt_tag_update', handler);
    }
}

export const mqttWebSocketService = new MQTTWebSocketService();
export default mqttWebSocketService;
