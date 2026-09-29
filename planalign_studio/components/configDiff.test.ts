import { describe, expect, it } from 'vitest';

import { splitConfigDeltas } from './configDiff';

describe('config delta split', () => {
  it('keeps only real changes in the headline list', () => {
    const { changed, unrecorded } = splitConfigDeltas([
      { path: 'dc_plan.match_cap_percent', status: 'changed' as const },
      { path: 'dc_plan.core_age_schedule', status: 'only_a' as const },
      { path: 'setup', status: 'only_b' as const },
    ]);
    expect(changed.map(item => item.path)).toEqual(['dc_plan.match_cap_percent']);
    expect(unrecorded.map(item => item.path)).toEqual(['dc_plan.core_age_schedule', 'setup']);
  });
});
