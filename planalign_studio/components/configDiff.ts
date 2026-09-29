import type { ConfigDelta } from '../services/api';

/**
 * Split real setting changes from settings only one run's saved config
 * recorded. A one-sided key usually means the other run predates the setting,
 * so its effective value is unknown -- not that the scenarios differ.
 */
export function splitConfigDeltas<T extends { status: ConfigDelta['status'] }>(deltas: T[]): { changed: T[]; unrecorded: T[] } {
  return {
    changed: deltas.filter(delta => delta.status === 'changed'),
    unrecorded: deltas.filter(delta => delta.status !== 'changed'),
  };
}

export const UNRECORDED_NOTE =
  "These settings appear in only one run's saved configuration, usually because the other run was produced by an earlier build that did not record them. Its effective value is unknown, so they are listed separately rather than counted as differences.";
