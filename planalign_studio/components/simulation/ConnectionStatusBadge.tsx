/**
 * Connection state indicator for live run telemetry (feature 094, US4).
 * Maps the useRunTelemetry state machine onto a compact badge.
 */

import React from 'react';
import { Wifi, WifiOff, RefreshCw, Radio, Flag, Loader2 } from 'lucide-react';
import { ConnectionState } from '../../services/websocket';

interface ConnectionStatusBadgeProps {
  state: ConnectionState;
  secondsSinceUpdate: number | null;
}

export default function ConnectionStatusBadge({
  state,
  secondsSinceUpdate,
}: ConnectionStatusBadgeProps) {
  switch (state) {
    case 'live':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-success-surface text-success-ink">
          <Wifi size={12} className="mr-1" /> Live
        </span>
      );
    case 'stale':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-warning-surface text-warning-ink">
          <WifiOff size={12} className="mr-1" />
          Stale{secondsSinceUpdate !== null ? ` — last update ${secondsSinceUpdate}s ago` : ''}
        </span>
      );
    case 'connecting':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-info-surface text-info-ink">
          <Loader2 size={12} className="mr-1 animate-spin" /> Connecting…
        </span>
      );
    case 'reconnecting':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-warning-surface text-warning-ink">
          <RefreshCw size={12} className="mr-1 animate-spin" /> Reconnecting…
        </span>
      );
    case 'polling':
      return (
        <span
          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-warning-surface text-warning-ink"
          title="Live connection unavailable — updating via periodic status checks"
        >
          <Radio size={12} className="mr-1" /> Degraded — polling
        </span>
      );
    case 'terminal':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-surface-disabled text-ink-muted">
          <Flag size={12} className="mr-1" /> Finished
        </span>
      );
    default:
      return null;
  }
}
