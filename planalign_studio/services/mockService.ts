import { useState, useEffect, useCallback } from 'react';
import { SimulationStatus, LogEvent, WorkflowStage } from '../types';

const STAGES: WorkflowStage[] = [
  'INITIALIZATION',
  'FOUNDATION',
  'EVENT_GENERATION',
  'STATE_ACCUMULATION',
  'VALIDATION',
  'REPORTING'
];

const EVENT_TYPES: ('HIRE' | 'TERMINATION' | 'PROMOTION' | 'RAISE')[] = ['HIRE', 'TERMINATION', 'PROMOTION', 'RAISE'];

export const useMockSimulationSocket = (simulationId: string | null) => {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [recentEvents, setRecentEvents] = useState<LogEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!simulationId) {
      setStatus(null);
      setRecentEvents([]);
      setIsConnected(false);
      return;
    }

    setIsConnected(true);

    // Initial State
    setStatus({
      simulation_id: simulationId,
      status: 'running',
      current_year: 2025,
      total_years: 3,
      current_stage: 'INITIALIZATION',
      progress_percent: 0,
      elapsed_seconds: 0,
      events_generated: 0,
      performance_metrics: {
        events_per_second: 0,
        memory_usage_mb: 256,
        memory_pressure: 'low',
        cpu_percent: 10
      }
    });

    const interval = setInterval(() => {
      setStatus((prev) => {
        if (!prev || prev.status === 'completed') return prev;

        let newProgress = prev.progress_percent + Math.random() * 5;
        let newStage = prev.current_stage;
        let newYear = prev.current_year;
        let newStatus = prev.status;

        if (newProgress >= 100) {
          const currentStageIndex = STAGES.indexOf(prev.current_stage);
          if (currentStageIndex < STAGES.length - 1) {
            newStage = STAGES[currentStageIndex + 1];
            newProgress = 0;
          } else {
             // End of year
             if (prev.current_year < 2025 + prev.total_years - 1) {
                newYear = prev.current_year + 1;
                newStage = 'INITIALIZATION';
                newProgress = 0;
             } else {
               newStatus = 'completed';
               newProgress = 100;
             }
          }
        }

        // Generate mock event
        if (Math.random() > 0.5 && newStatus === 'running') {
            const type = EVENT_TYPES[Math.floor(Math.random() * EVENT_TYPES.length)];
            const newEvent: LogEvent = {
                id: Math.random().toString(36).substr(2, 9),
                timestamp: new Date().toLocaleTimeString(),
                type,
                details: `Employee ${Math.floor(Math.random() * 9000) + 1000} processed`
            };
            setRecentEvents(prevEvents => [newEvent, ...prevEvents].slice(0, 50));
        }

        // Simulate memory pressure
        const currentMem = 400 + Math.floor(Math.random() * 800);
        let pressure: 'low' | 'moderate' | 'high' | 'critical' = 'low';
        if (currentMem > 1000) pressure = 'critical';
        else if (currentMem > 800) pressure = 'high';
        else if (currentMem > 600) pressure = 'moderate';

        return {
          ...prev,
          status: newStatus,
          current_stage: newStage,
          current_year: newYear,
          progress_percent: Math.min(newProgress, 100),
          elapsed_seconds: prev.elapsed_seconds + 1,
          events_generated: prev.events_generated + Math.floor(Math.random() * 150),
          performance_metrics: {
            events_per_second: Math.floor(Math.random() * 50) + 100,
            memory_usage_mb: currentMem,
            memory_pressure: pressure,
            cpu_percent: 30 + Math.floor(Math.random() * 40)
          }
        };
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [simulationId]);

  return { status, recentEvents, isConnected };
};

export const startMockSimulation = async (configId: string): Promise<string> => {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve(`sim_${Math.floor(Math.random() * 10000)}`);
    }, 800);
  });
};
