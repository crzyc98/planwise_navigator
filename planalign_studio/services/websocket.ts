/**
 * WebSocket hooks for real-time simulation telemetry
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { SimulationTelemetry } from './api';

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

// ============================================================================
// Types
// ============================================================================

export interface WebSocketStatus {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  reconnectAttempts: number;
}

export interface UseSimulationSocketResult {
  status: WebSocketStatus;
  telemetry: SimulationTelemetry | null;
  recentEvents: SimulationTelemetry['recent_events'];
  connect: () => void;
  disconnect: () => void;
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

// ============================================================================
// Simulation WebSocket Hook
// ============================================================================

export function useSimulationSocket(runId: string | null): UseSimulationSocketResult {
  const [status, setStatus] = useState<WebSocketStatus>({
    isConnected: false,
    isConnecting: false,
    error: null,
    reconnectAttempts: 0,
  });
  const [telemetry, setTelemetry] = useState<SimulationTelemetry | null>(null);
  const [recentEvents, setRecentEvents] = useState<SimulationTelemetry['recent_events']>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 2000;

  const connect = useCallback(() => {
    if (!runId || wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    setStatus(prev => ({ ...prev, isConnecting: true, error: null }));

    const ws = new WebSocket(`${WS_BASE}/ws/simulation/${runId}`);
    wsRef.current = ws;

    ws.onopen = () => {
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

        // Handle heartbeat
        if (data.type === 'heartbeat') {
          return;
        }

        // Update telemetry
        setTelemetry(data as SimulationTelemetry);

        // Accumulate recent events (keep last 50)
        if (data.recent_events && data.recent_events.length > 0) {
          setRecentEvents(prev => {
            const newEvents = [...data.recent_events, ...prev];
            return newEvents.slice(0, 50);
          });
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
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

      // Attempt reconnect if not intentionally closed
      if (event.code !== 1000 && status.reconnectAttempts < maxReconnectAttempts) {
        reconnectTimeoutRef.current = setTimeout(() => {
          setStatus(prev => ({
            ...prev,
            reconnectAttempts: prev.reconnectAttempts + 1,
          }));
          connect();
        }, reconnectDelay * Math.pow(2, status.reconnectAttempts));
      }
    };
  }, [runId, status.reconnectAttempts]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }

    setStatus({
      isConnected: false,
      isConnecting: false,
      error: null,
      reconnectAttempts: 0,
    });
    setTelemetry(null);
    setRecentEvents([]);
  }, []);

  // Auto-connect when runId changes
  useEffect(() => {
    if (runId) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [runId]);

  return {
    status,
    telemetry,
    recentEvents,
    connect,
    disconnect,
  };
}

// ============================================================================
// Batch WebSocket Hook
// ============================================================================

export function useBatchSocket(batchId: string | null): UseBatchSocketResult {
  const [status, setStatus] = useState<WebSocketStatus>({
    isConnected: false,
    isConnecting: false,
    error: null,
    reconnectAttempts: 0,
  });
  const [batchStatus, setBatchStatus] = useState<BatchTelemetry | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
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

    const ws = new WebSocket(`${WS_BASE}/ws/batch/${batchId}`);
    wsRef.current = ws;

    ws.onopen = () => {
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

      if (event.code !== 1000 && status.reconnectAttempts < maxReconnectAttempts) {
        reconnectTimeoutRef.current = setTimeout(() => {
          setStatus(prev => ({
            ...prev,
            reconnectAttempts: prev.reconnectAttempts + 1,
          }));
          connect();
        }, reconnectDelay * Math.pow(2, status.reconnectAttempts));
      }
    };
  }, [batchId, status.reconnectAttempts]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }

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
  }, [batchId]);

  return {
    status,
    batchStatus,
    connect,
    disconnect,
  };
}
