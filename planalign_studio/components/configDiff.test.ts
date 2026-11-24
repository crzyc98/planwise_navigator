import { describe, expect, it } from 'vitest';

import { unsetLabel } from './configDiff';

describe('unset label', () => {
  it('names the side whose config lacks a one-sided setting', () => {
    const onlyA = { status: 'only_a' as const };
    expect(unsetLabel(onlyA, 'b')).toBe('Not set');
    expect(unsetLabel(onlyA, 'a')).toBeNull();
    expect(unsetLabel({ status: 'only_b' as const }, 'a')).toBe('Not set');
  });

  it('leaves an explicit null that both runs recorded alone', () => {
    expect(unsetLabel({ status: 'changed' as const }, 'a')).toBeNull();
    expect(unsetLabel({ status: 'changed' as const }, 'b')).toBeNull();
  });
});
