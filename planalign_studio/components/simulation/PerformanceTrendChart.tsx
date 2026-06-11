/**
 * Live performance trend chart (feature 094, US3).
 *
 * Renders throughput (events/sec) and memory (MB) over elapsed time from the
 * run's performance samples. The sample buffer is bounded upstream (server
 * ring buffer + client downsampling), so render cost stays constant.
 */

import React, { useMemo } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { PerformanceSample } from '../../services/api';

interface PerformanceTrendChartProps {
  samples: PerformanceSample[];
}

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export default function PerformanceTrendChart({ samples }: PerformanceTrendChartProps) {
  const data = useMemo(
    () =>
      samples.map((s) => ({
        elapsed: s.elapsed_seconds,
        eventsPerSecond: Math.round(s.events_per_second * 10) / 10,
        memoryMb: Math.round(s.memory_mb),
      })),
    [samples]
  );

  if (data.length < 2) {
    return (
      <div className="h-40 bg-gray-50 rounded-lg border border-gray-200 flex items-center justify-center text-gray-400 text-sm">
        Collecting performance samples…
      </div>
    );
  }

  return (
    <div className="h-40">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="elapsed"
            tickFormatter={formatElapsed}
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            type="number"
            domain={['dataMin', 'dataMax']}
          />
          <YAxis
            yAxisId="throughput"
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            width={40}
          />
          <YAxis
            yAxisId="memory"
            orientation="right"
            tick={{ fontSize: 10, fill: '#9ca3af' }}
            width={45}
          />
          <Tooltip
            labelFormatter={(value: number) => `Elapsed ${formatElapsed(value)}`}
            contentStyle={{ fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line
            yAxisId="throughput"
            type="monotone"
            dataKey="eventsPerSecond"
            name="Events/sec"
            stroke="#00853F"
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
          <Line
            yAxisId="memory"
            type="monotone"
            dataKey="memoryMb"
            name="Memory (MB)"
            stroke="#8b5cf6"
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
