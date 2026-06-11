/**
 * Milestone activity feed for the active run (feature 094, US2).
 *
 * Replaces the raw per-employee event stream with stage transitions,
 * per-year summaries, warnings, and errors. Newest entries first; pinned to
 * the newest unless the user scrolls away.
 */

import React, { useMemo, useRef, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CalendarCheck,
  CircleDot,
  Flag,
  Play,
  XCircle,
} from 'lucide-react';
import { TelemetryMilestone } from '../../services/api';

interface ActivityFeedProps {
  milestones: TelemetryMilestone[];
}

const KIND_ICONS: Record<
  TelemetryMilestone['kind'],
  React.ComponentType<{ size?: number; className?: string }>
> = {
  run_started: Play,
  stage_started: CircleDot,
  stage_completed: CircleDot,
  year_completed: CalendarCheck,
  warning: AlertTriangle,
  error: XCircle,
  terminal: Flag,
};

function severityClasses(milestone: TelemetryMilestone): {
  container: string;
  icon: string;
} {
  if (milestone.severity === 'error') {
    return { container: 'bg-red-50 border-l-red-500', icon: 'text-red-600' };
  }
  if (milestone.severity === 'warning') {
    return { container: 'bg-yellow-50 border-l-yellow-500', icon: 'text-yellow-600' };
  }
  if (milestone.kind === 'year_completed') {
    return { container: 'bg-green-50 border-l-fidelity-green', icon: 'text-fidelity-green' };
  }
  if (milestone.kind === 'terminal') {
    return { container: 'bg-gray-100 border-l-gray-500', icon: 'text-gray-600' };
  }
  return { container: 'border-l-transparent', icon: 'text-gray-400' };
}

export default function ActivityFeed({ milestones }: ActivityFeedProps) {
  const newestFirst = useMemo(
    () => [...milestones].sort((a, b) => b.sequence - a.sequence),
    [milestones]
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  // Newest entries render at the top; stay pinned there unless the user scrolls
  useEffect(() => {
    if (pinned && scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [newestFirst.length, pinned]);

  const handleScroll = () => {
    if (scrollRef.current) {
      setPinned(scrollRef.current.scrollTop < 8);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-4 border-b border-gray-200 bg-gray-50 flex justify-between items-center">
        <h3 className="font-semibold text-gray-800 flex items-center">
          <Activity size={16} className="mr-2 text-gray-500" />
          Run Activity
        </h3>
        <span className="bg-gray-200 text-gray-600 px-2 py-0.5 rounded text-xs">
          {newestFirst.length} milestone{newestFirst.length === 1 ? '' : 's'}
        </span>
      </div>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto text-sm"
      >
        {newestFirst.length === 0 ? (
          <div className="p-4 text-gray-400 italic">
            Milestones will appear as the run progresses…
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {newestFirst.map((milestone) => {
              const Icon = KIND_ICONS[milestone.kind] ?? CircleDot;
              const classes = severityClasses(milestone);
              return (
                <li
                  key={milestone.sequence}
                  className={`px-3 py-2 border-l-4 ${classes.container}`}
                >
                  <div className="flex items-start">
                    <Icon size={14} className={`mr-2 mt-0.5 shrink-0 ${classes.icon}`} />
                    <div className="min-w-0 flex-1">
                      <p className="text-gray-800 break-words">{milestone.message}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5">
                        {new Date(milestone.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
