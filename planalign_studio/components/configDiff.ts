import type { ConfigDelta } from '../services/api';
import { canonicalSetting, formatNumberPair, formatSetting, NONE_WHEN_UNSET, settingLabel } from './comparisonIntegrity';

type Side = 'a' | 'b';

const NOT_SET = 'Not set';

/**
 * "Not set" for the side of a one-sided row whose config lacks the setting,
 * else null. Studio saves only the settings an analyst edits, so a missing key
 * usually means the scenario never set it; the row is still a difference.
 */
export function unsetLabel(delta: { status: ConfigDelta['status'] }, side: Side): string | null {
  return delta.status === (side === 'a' ? 'only_b' : 'only_a') ? NOT_SET : null;
}

export interface ConfigDiffRow {
  /** The delta the row's copy buttons act on, with its raw path and value. */
  delta: ConfigDelta;
  label: string;
  /** Raw config paths the row stands for: the delta's, then any mirror folded into it. */
  paths: string[];
  a: string;
  b: string;
}

function isUnset(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === 'string' && value.trim() === '');
}

/** A side's value in the words the like-for-like banner uses. */
function cellText(path: string, value: unknown, unset: boolean): string {
  // No minimum wage or acquisitions is "None", as the banner says.
  if (NONE_WHEN_UNSET.has(path)) return capitalise(formatSetting(path, unset ? null : value) ?? JSON.stringify(value));
  if (unset || isUnset(value)) return NOT_SET;
  const text = formatSetting(path, value);
  if (text === null) return JSON.stringify(value);
  // Recorded strings show verbatim; the helper's own words start a cell.
  return typeof value === 'string' ? text : capitalise(text);
}

function capitalise(text: string): string {
  return text.replace(/^./, letter => letter.toUpperCase());
}

/** Both sides, in one unit and with enough precision that a change never reads as equal. */
function cellTexts(delta: ConfigDelta): [string, string] {
  const a = canonicalSetting(delta.path, delta.a);
  const b = canonicalSetting(delta.path, delta.b);
  const unsetA = unsetLabel(delta, 'a') !== null;
  const unsetB = unsetLabel(delta, 'b') !== null;
  if (!unsetA && !unsetB && typeof a.value === 'number' && typeof b.value === 'number') {
    return formatNumberPair(a.path, a.value, b.value);
  }
  return [cellText(a.path, a.value, unsetA), cellText(b.path, b.value, unsetB)];
}

/** Comparable form of a canonical value; scaling can leave float noise (0.07 * 100). */
function comparable(value: unknown): string {
  return JSON.stringify(typeof value === 'number' ? Number(value.toPrecision(12)) : value ?? null);
}

function sameSetting(left: ConfigDelta, right: ConfigDelta): boolean {
  if (left.status !== right.status) return false;
  return (['a', 'b'] as const).every(side =>
    comparable(canonicalSetting(left.path, left[side]).value) === comparable(canonicalSetting(right.path, right[side]).value));
}

/**
 * One row per difference. A setting recorded under two paths that agree after
 * scaling becomes one row; copies that disagree both stay, so the conflict shows.
 * The row keeps the copy the mirror rule rewrites (the engine's pay decimal,
 * Studio's dc_plan match-response copy), so copying writes what that row did.
 */
export function configDiffRows(deltas: ConfigDelta[]): ConfigDiffRow[] {
  const byCanonical = new Map<string, ConfigDelta[]>();
  deltas.forEach(delta => {
    const key = canonicalSetting(delta.path, null).path;
    byCanonical.set(key, [...(byCanonical.get(key) ?? []), delta]);
  });
  // Kept path -> the mirror path folded into its row.
  const mirrorOf = new Map<string, string>();
  byCanonical.forEach((group, canonical) => {
    const kept = group.find(delta => delta.path !== canonical);
    const mirror = group.find(delta => delta.path === canonical);
    if (group.length === 2 && kept && mirror && sameSetting(kept, mirror)) mirrorOf.set(kept.path, mirror.path);
  });
  const folded = new Set(mirrorOf.values());
  return deltas
    .filter(delta => !folded.has(delta.path))
    .map(delta => {
      const mirror = mirrorOf.get(delta.path);
      const [a, b] = cellTexts(delta);
      return { delta, label: settingLabel(delta.path), paths: mirror ? [delta.path, mirror] : [delta.path], a, b };
    });
}
