import { describe, expect, it } from 'vitest';
import { splitAcquiredHires } from './acquiredHires';

describe('splitAcquiredHires', () => {
  const trends = { hire: [10, 40, 12], termination: [5, 6, 7] };

  it('leaves runs without acquired members unchanged', () => {
    expect(splitAcquiredHires(trends, [])).toBe(trends);
    expect(splitAcquiredHires(trends, undefined)).toBe(trends);
    expect(splitAcquiredHires(trends, [0, 0, 0])).toBe(trends);
  });

  it('makes hire organic and adds acquired', () => {
    expect(splitAcquiredHires(trends, [0, 25, 0])).toEqual({ hire: [10, 15, 12], termination: [5, 6, 7], acquired: [0, 25, 0] });
  });
});
