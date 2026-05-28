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

export interface PlcStatus {
  id: string;
  name: string;
  status: string;
  connected: boolean;
  protocol: string;
  ipAddress: string;
  lastUpdate: string;
}

export interface OpcPlcStatusResult {
  opc: OpcStatus | null;
  plcs: PlcStatus[];
  anyPlcDisconnected: boolean;
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
          plcs: data.plcs ?? [],
          anyPlcDisconnected: data.anyPlcDisconnected ?? false,
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
