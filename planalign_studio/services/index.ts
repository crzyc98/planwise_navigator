/**
 * Services index - exports all API and WebSocket functionality
 */

// API client
export * from './api';

// WebSocket hooks
export { useSimulationSocket, useBatchSocket } from './websocket';
export type {
  WebSocketStatus,
  UseSimulationSocketResult,
  UseBatchSocketResult,
  BatchTelemetry,
} from './websocket';

// Re-export mock service for development/testing
export { useMockSimulationSocket, startMockSimulation } from './mockService';
