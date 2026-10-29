import type { NDTAvailableYearsResponse } from '../services/api';

export function combineNDTAvailability(responses: NDTAvailableYearsResponse[]) {
  const years = responses.length === 0 ? [] : responses[0].years
    .filter(year => responses.every(response => response.years.includes(year)))
    .sort((a, b) => a - b);
  const designs = [...new Set(responses.flatMap(response => response.plan_design_ids))].sort();
  return { years, designs };
}

/** Invalidate responses when a selection changes or a newer request starts. */
export function createNDTRequestGate() {
  let generation = 0;
  let selection = '';
  return {
    select(key: string) {
      if (key !== selection) { selection = key; generation += 1; }
    },
    begin() { generation += 1; return generation; },
    isCurrent(token: number) { return token === generation; },
  };
}
