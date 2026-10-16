import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConfigContextType, ConfigProvider, useConfigContext } from './ConfigContext';
import { DEFAULT_FORM_DATA } from './constants';
import { updateWorkspace, Workspace } from '../../services/api';

const hydration = vi.hoisted(() => ({ slot: 0, loaded: true, failed: false }));
vi.mock('react', async importOriginal => {
  const actual = await importOriginal<typeof import('react')>();
  return {
    ...actual,
    // SSR does not run fetch effects. Seed only the provider's loading state;
    // keep its actual React state, refs, save handler and payload construction.
    useState: (initial: unknown) => {
      const slot = hydration.slot++;
      if (slot === 1) return actual.useState(hydration.loaded ? { ...DEFAULT_FORM_DATA, startYear: 2025, endYear: 2029, dcEligibilityMonths: 3 } : null);
      if (slot === 4) return actual.useState(hydration.failed);
      if (slot === 11) return actual.useState(hydration.loaded ? {} : null);
      return actual.useState(initial);
    },
  };
});

vi.mock('./constants', async importOriginal => {
  const actual = await importOriginal<typeof import('./constants')>();
  return { ...actual, DEFAULT_FORM_DATA: { ...actual.DEFAULT_FORM_DATA } };
});
vi.mock('../../services/api', () => ({ updateWorkspace: vi.fn() }));

function saveFromProvider() {
  hydration.slot = 0;
  let context!: ConfigContextType;
  function Probe() { context = useConfigContext(); return null; }
  renderToStaticMarkup(
    <ConfigProvider activeWorkspace={{ id: 'synthetic', base_config: { simulation: { start_year: 2025, end_year: 2029 } } } as unknown as Workspace} scenarioId={undefined}>
      <Probe />
    </ConfigProvider>,
  );
  return context.handleSaveConfig;
}

describe('Configuration save year validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.stubGlobal('document', { activeElement: null });
    vi.stubGlobal('HTMLElement', class {});
    DEFAULT_FORM_DATA.startYear = 2025;
    DEFAULT_FORM_DATA.endYear = 2029;
    DEFAULT_FORM_DATA.dcEligibilityMonths = 3;
    DEFAULT_FORM_DATA.dcVoluntaryEnrollmentMode = undefined;
    DEFAULT_FORM_DATA.dcVoluntaryEnrollmentRate = '65';
    hydration.loaded = true;
    hydration.failed = false;
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('rejects end-before-start before any persistence', async () => {
    DEFAULT_FORM_DATA.endYear = 2024;
    expect(await saveFromProvider()()).toBe(false);
    expect(updateWorkspace).not.toHaveBeenCalled();
  });

  it('rejects a new fractional-month duration rather than silently truncating it', async () => {
    DEFAULT_FORM_DATA.dcEligibilityMonths = 1.5;
    expect(await saveFromProvider()()).toBe(false);
    expect(updateWorkspace).not.toHaveBeenCalled();
  });

  it('does not turn a blank specified enrollment rate into inheritance', async () => {
    DEFAULT_FORM_DATA.dcVoluntaryEnrollmentMode = 'specified';
    DEFAULT_FORM_DATA.dcVoluntaryEnrollmentRate = '';
    expect(await saveFromProvider()()).toBe(false);
    expect(updateWorkspace).not.toHaveBeenCalled();
  });

  it('permits single-year simulations and persists the validated horizon', async () => {
    DEFAULT_FORM_DATA.endYear = 2025;
    expect(await saveFromProvider()()).toBe(true);
    expect(updateWorkspace).toHaveBeenCalledWith('synthetic', {
      base_config: expect.objectContaining({ simulation: expect.objectContaining({ start_year: 2025, end_year: 2025 }) }),
    });
  });

  it('returns explicit failure when persistence rejects', async () => {
    vi.mocked(updateWorkspace).mockRejectedValueOnce(new Error('Synthetic save failure'));
    expect(await saveFromProvider()()).toBe(false);
  });

  it.each(['loading', 'failed'])('blocks saving when configuration is %s', async status => {
    hydration.loaded = status !== 'loading';
    hydration.failed = status === 'failed';
    expect(await saveFromProvider()()).toBe(false);
    expect(updateWorkspace).not.toHaveBeenCalled();
  });
});
