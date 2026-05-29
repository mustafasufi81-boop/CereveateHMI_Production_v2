/**
 * useOpcPlcStatus — polls /api/opc-plc-status every 10s
 * Returns real-time OPC server and PLC connection state from the C# backend.
 */
import { useState, useEffect, useRef } from "react";

export interface OpcStatus {
  connected: boolean;
  status: string;         // "Connected" | "Disconnected" | "Unknown" etc.
  serverName: string;
  tagsConnected: number;
  healthScore: number;
  lastError: string | null;
}

export interface PlcAlert {
  level: string;   // "error" | "warning" | "info"
  code: string;    // "PLC_FROZEN" | "PLC_DISCONNECTED" | "NO_PLC_CONFIGURED"
  message: string;
}

export interface PlcStatus {
  id: string;
  name: string;
  status: string;
  connected: boolean;
  protocol: string;
  ipAddress: string;
  lastUpdate: string;
  // Gap 8: PLC mode + freeze info
  mode: string;            // "RUN" | "FROZEN" | "UNKNOWN"
  frozenForMs: number;
  lastValueChange: string;
  alerts: PlcAlert[];
  isNoPlcSentinel: boolean;
}

export interface OpcPlcStatusResult {
  opc: OpcStatus | null;
  plcs: PlcStatus[];
  anyPlcDisconnected: boolean;
  anyPlcFrozen: boolean;
  noPlcConfigured: boolean;
  backendReachable: boolean;
  loading: boolean;
  lastUpdated: Date | null;
}

const POLL_INTERVAL_MS = 10_000;

export function useOpcPlcStatus(): OpcPlcStatusResult {
  const [result, setResult] = useState<OpcPlcStatusResult>({
    opc: null,
    plcs: [],
    anyPlcDisconnected: false,
    anyPlcFrozen: false,
    noPlcConfigured: false,
    backendReachable: true,
    loading: true,
    lastUpdated: null,
  });

  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    const poll = async () => {
      try {
        const token = localStorage.getItem("auth_token") || "";
        const res = await fetch("/api/opc-plc-status", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!mountedRef.current) return;
        setResult({
          opc: data.opc ?? null,
          plcs: (data.plcs ?? []).map((p: Partial<PlcStatus>) => ({
            id: p.id ?? "",
            name: p.name ?? "",
            status: p.status ?? "",
            connected: !!p.connected,
            protocol: p.protocol ?? "",
            ipAddress: p.ipAddress ?? "",
            lastUpdate: p.lastUpdate ?? "",
            mode: p.mode ?? "UNKNOWN",
            frozenForMs: p.frozenForMs ?? 0,
            lastValueChange: p.lastValueChange ?? "",
            alerts: p.alerts ?? [],
            isNoPlcSentinel: !!p.isNoPlcSentinel,
          })),
          anyPlcDisconnected: data.anyPlcDisconnected ?? false,
          anyPlcFrozen: data.anyPlcFrozen ?? false,
          noPlcConfigured: data.noPlcConfigured ?? false,
          backendReachable: data.backendReachable ?? true,
          loading: false,
          lastUpdated: new Date(),
        });
      } catch {
        if (!mountedRef.current) return;
        // Keep previous data but mark backend unreachable
        setResult((prev) => ({
          ...prev,
          backendReachable: false,
          loading: false,
          lastUpdated: new Date(),
        }));
      }
    };

    poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      mountedRef.current = false;
      clearInterval(timer);
    };
  }, []);

  return result;
}
