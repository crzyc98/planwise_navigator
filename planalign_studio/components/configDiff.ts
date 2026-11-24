import type { ConfigDelta } from '../services/api';

/**
 * "Not set" for the side of a one-sided row whose config lacks the setting,
 * else null. Studio saves only the settings an analyst edits, so a missing key
 * usually means the scenario never set it; the row is still a difference.
 */
export function unsetLabel(delta: { status: ConfigDelta['status'] }, side: 'a' | 'b'): string | null {
  return delta.status === (side === 'a' ? 'only_b' : 'only_a') ? 'Not set' : null;
}
