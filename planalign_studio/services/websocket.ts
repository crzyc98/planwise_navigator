/**
 * WebSocket hooks for real-time simulation telemetry.
 *
 * Feature 094: useRunTelemetry implements the reliability contract in
 * specs/094-live-run-dashboard/contracts/websocket-messages.md —
 * exponential-backoff reconnect (counter in refs, not React state),
 * full snapshot resync on every (re)connect, staleness detection, REST
 * polling fallback, and guaranteed terminal-state convergence.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  fetchRunTelemetrySnapshot,
  PerformanceSample,
  RunTelemetrySnapshot,
  RunTelemetryUpdate,
  TelemetryMilestone,
  TelemetryWsMessage,
} from './api';

function getWebSocketBase(): string {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}`;
}

const WS_BASE = getWebSocketBase();
const API_TOKEN = import.meta.env.VITE_PLANALIGN_API_TOKEN as string | undefined;

function websocketUrl(path: string): string {
  const url = new URL(`${WS_BASE}${path}`);
  if (API_TOKEN) url.searchParams.set('token', API_TOKEN);
  return url.toString();
}

// ============================================================================
// Run telemetry hook (feature 094)
// ============================================================================

export type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'live'
  | 'stale'
  | 'reconnecting'
  | 'polling'
  | 'terminal';

export interface UseRunTelemetryResult {
  connectionState: ConnectionState;
  snapshot: RunTelemetrySnapshot | null;
  secondsSinceUpdate: number | null;
}

const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY_MS = 2_000;
const STALE_AFTER_MS = 15_000;
const POLL_INTERVAL_MS = 5_000;
const WS_UPGRADE_RETRY_MS = 30_000;
const MAX_CLIENT_SAMPLES = 600;

const TERMINAL_STATUSES = ['completed', 'failed', 'cancelled'];

function isTerminal(status: string | undefined | null): boolean {
  return !!status && TERMINAL_STATUSES.includes(status);
}

/** Append a perf sample derived from an update, keeping the buffer bounded. */
function appendSample(
  samples: PerformanceSample[],
  update: RunTelemetryUpdate
): PerformanceSample[] {
  const last = samples[samples.length - 1];
  if (last && last.elapsed_seconds === update.performance_metrics.elapsed_seconds) {
    return samples;
  }
  let next = [
    ...samples,
    {
      timestamp: update.last_update_at,
      elapsed_seconds: update.performance_metrics.elapsed_seconds,
      events_per_second: update.performance_metrics.events_per_second,
      memory_mb: update.performance_metrics.memory_mb,
    },
  ];
  if (next.length > MAX_CLIENT_SAMPLES) {
    // Drop every other point to stay bounded while preserving the trend shape
    next = next.filter((_, idx) => idx % 2 === 0 || idx === next.length - 1);
  }
  return next;
}

function appendMilestone(
  milestones: TelemetryMilestone[],
  milestone: TelemetryMilestone
): TelemetryMilestone[] {
  const lastSeq = milestones.length
    ? milestones[milestones.length - 1].sequence
    : 0;
  if (milestone.sequence <= lastSeq) {
    return milestones; // duplicate already delivered via snapshot
  }
  return [...milestones, milestone];
}

export function useRunTelemetry(
  runId: string | null,
  scenarioId: string | null
): UseRunTelemetryResult {
  const [connectionState, setConnectionState] = useState<ConnectionState>('idle');
  const [snapshot, setSnapshot] = useState<RunTelemetrySnapshot | null>(null);
  const [secondsSinceUpdate, setSecondsSinceUpdate] = useState<number | null>(null);

  // All mutable connection bookkeeping lives in refs so reconnect logic never
  // reads stale closures (the bug in the pre-094 hook).
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const lastMessageAtRef = useRef<number | null>(null);
  const terminalRef = useRef(false);
  const timersRef = useRef<{ [key: string]: ReturnType<typeof setTimeout> | null }>({
    reconnect: null,
    poll: null,
    wsUpgrade: null,
    staleCheck: null,
  });
  const stateRef = useRef<ConnectionState>('idle');

  const setState = useCallback((next: ConnectionState) => {
    stateRef.current = next;
    setConnectionState(next);
  }, []);

  const clearTimer = useCallback((name: string) => {
    const timer = timersRef.current[name];
    if (timer) {
      clearTimeout(timer);
      timersRef.current[name] = null;
    }
  }, []);

  const clearAllTimers = useCallback(() => {
    Object.keys(timersRef.current).forEach((name) => clearTimer(name));
  }, [clearTimer]);

  const closeSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onopen = null;
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
  }, []);

  const enterTerminal = useCallback(() => {
    if (terminalRef.current) return;
    terminalRef.current = true;
    clearAllTimers();
    closeSocket();
    setState('terminal');
  }, [clearAllTimers, closeSocket, setState]);

  const noteLiveness = useCallback(() => {
    lastMessageAtRef.current = Date.now();
    setSecondsSinceUpdate(0);
    if (stateRef.current === 'stale') {
      setState('live');
    }
  }, [setState]);

  const handleMessage = useCallback(
    (raw: string) => {
      let message: TelemetryWsMessage;
      try {
        message = JSON.parse(raw);
      } catch {
        console.error('[Telemetry] Failed to parse message');
        return;
      }
      noteLiveness();

      switch (message.type) {
        case 'heartbeat':
          return;
        case 'snapshot':
          // Full replacement — never merge into possibly-stale state
          setSnapshot(message.data);
          if (isTerminal(message.data.status)) enterTerminal();
          return;
        case 'update':
          setSnapshot((prev) => {
            const base: RunTelemetrySnapshot = prev ?? {
              ...message.data,
              milestones: [],
              performance_samples: [],
            };
            return {
              ...base,
              ...message.data,
              milestones: base.milestones,
              performance_samples: appendSample(
                base.performance_samples,
                message.data
              ),
            };
          });
          if (isTerminal(message.data.status)) enterTerminal();
          return;
        case 'milestone':
          setSnapshot((prev) =>
            prev
              ? { ...prev, milestones: appendMilestone(prev.milestones, message.data) }
              : prev
          );
          return;
        default:
          // Forward compatibility: ignore unknown message types
          return;
      }
    },
    [enterTerminal, noteLiveness]
  );

  // Poll the REST snapshot endpoint (degraded mode and terminal safety net)
  const pollOnce = useCallback(async () => {
    if (!scenarioId || terminalRef.current) return;
    try {
      const result = await fetchRunTelemetrySnapshot(scenarioId);
      if (result.telemetry) {
        setSnapshot(result.telemetry);
        noteLiveness();
        if (isTerminal(result.telemetry.status)) enterTerminal();
      } else if (isTerminal(result.run.status)) {
        // State lost server-side (API restart) but the run is over
        setSnapshot((prev) =>
          prev ? { ...prev, status: result.run.status as RunTelemetrySnapshot['status'] } : prev
        );
        enterTerminal();
      }
    } catch (err) {
      console.warn('[Telemetry] Poll failed:', err);
    }
  }, [scenarioId, enterTerminal, noteLiveness]);

  const connectRef = useRef<() => void>(() => {});

  const enterPolling = useCallback(() => {
    if (terminalRef.current) return;
    setState('polling');
    const schedulePoll = () => {
      timersRef.current.poll = setTimeout(async () => {
        await pollOnce();
        if (!terminalRef.current && stateRef.current === 'polling') schedulePoll();
      }, POLL_INTERVAL_MS);
    };
    schedulePoll();
    // Periodically try to upgrade back to the live connection
    const scheduleUpgrade = () => {
      timersRef.current.wsUpgrade = setTimeout(() => {
        if (terminalRef.current || stateRef.current !== 'polling') return;
        retryCountRef.current = 0;
        connectRef.current();
        scheduleUpgrade();
      }, WS_UPGRADE_RETRY_MS);
    };
    scheduleUpgrade();
    void pollOnce();
  }, [pollOnce, setState]);

  const scheduleReconnect = useCallback(() => {
    if (terminalRef.current) return;
    if (retryCountRef.current >= MAX_RECONNECT_ATTEMPTS) {
      enterPolling();
      return;
    }
    const delay = BASE_RECONNECT_DELAY_MS * Math.pow(2, retryCountRef.current);
    retryCountRef.current += 1;
    setState('reconnecting');
    console.log(
      `[Telemetry] Reconnect attempt ${retryCountRef.current}/${MAX_RECONNECT_ATTEMPTS} in ${delay}ms`
    );
    timersRef.current.reconnect = setTimeout(() => connectRef.current(), delay);
  }, [enterPolling, setState]);

  const connect = useCallback(() => {
    if (!runId || terminalRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    closeSocket();

    if (stateRef.current !== 'polling') {
      setState(retryCountRef.current > 0 ? 'reconnecting' : 'connecting');
    }

    const ws = new WebSocket(websocketUrl(`/ws/simulation/${runId}`));
    wsRef.current = ws;

    ws.onopen = () => {
      retryCountRef.current = 0;
      // Leaving polling mode: stop the poll/upgrade timers
      clearTimer('poll');
      clearTimer('wsUpgrade');
      setState('live');
      noteLiveness();
    };

    ws.onmessage = (event) => handleMessage(event.data);

    ws.onerror = () => {
      console.error('[Telemetry] WebSocket error');
    };

    ws.onclose = (event) => {
      wsRef.current = null;
      if (event.code === 1000 || terminalRef.current) return;
      if (stateRef.current === 'polling') return; // upgrade attempt failed; keep polling
      scheduleReconnect();
    };
  }, [runId, closeSocket, clearTimer, setState, noteLiveness, handleMessage, scheduleReconnect]);

  connectRef.current = connect;

  // Staleness watcher (heartbeats count as liveness)
  useEffect(() => {
    if (!runId) return;
    const interval = setInterval(() => {
      const last = lastMessageAtRef.current;
      if (last === null) return;
      const elapsed = Date.now() - last;
      setSecondsSinceUpdate(Math.floor(elapsed / 1000));
      if (
        elapsed > STALE_AFTER_MS &&
        stateRef.current === 'live' &&
        !terminalRef.current
      ) {
        setState('stale');
      }
    }, 1_000);
    return () => clearInterval(interval);
  }, [runId, setState]);

  // Lifecycle: connect for the active run; full reset when the run changes
  useEffect(() => {
    if (!runId) {
      setState('idle');
      setSnapshot(null);
      setSecondsSinceUpdate(null);
      return;
    }

    terminalRef.current = false;
    retryCountRef.current = 0;
    lastMessageAtRef.current = null;
    setSnapshot(null);

    // Instant restore on mount/refresh while the socket connects
    void pollOnce();
    connectRef.current();

    return () => {
      clearAllTimers();
      closeSocket();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  return { connectionState, snapshot, secondsSinceUpdate };
}

// ============================================================================
// Batch WebSocket Hook (pre-094 protocol, unchanged)
// ============================================================================

export interface WebSocketStatus {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  reconnectAttempts: number;
}

export interface UseBatchSocketResult {
  status: WebSocketStatus;
  batchStatus: BatchTelemetry | null;
  connect: () => void;
  disconnect: () => void;
}

export interface BatchTelemetry {
  batch_id: string;
  status: string;
  scenarios: Array<{
    scenario_id: string;
    name: string;
    status: string;
    progress: number;
  }>;
  overall_progress: number;
  timestamp: string;
}

export function useBatchSocket(batchId: string | null): UseBatchSocketResult {
  const [status, setStatus] = useState<WebSocketStatus>({
    isConnected: false,
    isConnecting: false,
    error: null,
    reconnectAttempts: 0,
  });
  const [batchStatus, setBatchStatus] = useState<BatchTelemetry | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 2000;

  const connect = useCallback(() => {
    if (!batchId || wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    if (wsRef.current) {
      wsRef.current.close();
    }

    setStatus(prev => ({ ...prev, isConnecting: true, error: null }));

    const ws = new WebSocket(websocketUrl(`/ws/batch/${batchId}`));
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptsRef.current = 0;
      setStatus({
        isConnected: true,
        isConnecting: false,
        error: null,
        reconnectAttempts: 0,
      });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'heartbeat') {
          return;
        }

        setBatchStatus(data as BatchTelemetry);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onerror = () => {
      setStatus(prev => ({
        ...prev,
        error: 'Connection error',
      }));
    };

    ws.onclose = (event) => {
      setStatus(prev => ({
        ...prev,
        isConnected: false,
        isConnecting: false,
      }));

      if (event.code !== 1000 && reconnectAttemptsRef.current < maxReconnectAttempts) {
        const attempt = reconnectAttemptsRef.current;
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectAttemptsRef.current = attempt + 1;
          setStatus(prev => ({
            ...prev,
            reconnectAttempts: attempt + 1,
          }));
          connect();
        }, reconnectDelay * Math.pow(2, attempt));
      }
    };
  }, [batchId]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }

    reconnectAttemptsRef.current = 0;
    setStatus({
      isConnected: false,
      isConnecting: false,
      error: null,
      reconnectAttempts: 0,
    });
    setBatchStatus(null);
  }, []);

  useEffect(() => {
    if (batchId) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId]);

  return {
    status,
    batchStatus,
    connect,
    disconnect,
  };
}
