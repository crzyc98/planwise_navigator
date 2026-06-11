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
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">
          <Wifi size={12} className="mr-1" /> Live
        </span>
      );
    case 'stale':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-700">
          <WifiOff size={12} className="mr-1" />
          Stale{secondsSinceUpdate !== null ? ` — last update ${secondsSinceUpdate}s ago` : ''}
        </span>
      );
    case 'connecting':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">
          <Loader2 size={12} className="mr-1 animate-spin" /> Connecting…
        </span>
      );
    case 'reconnecting':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700">
          <RefreshCw size={12} className="mr-1 animate-spin" /> Reconnecting…
        </span>
      );
    case 'polling':
      return (
        <span
          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700"
          title="Live connection unavailable — updating via periodic status checks"
        >
          <Radio size={12} className="mr-1" /> Degraded — polling
        </span>
      );
    case 'terminal':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-200 text-gray-600">
          <Flag size={12} className="mr-1" /> Finished
        </span>
      );
    default:
      return null;
  }
}
