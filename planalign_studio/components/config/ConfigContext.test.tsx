import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { applyConfigToFormData, ConfigContextType, ConfigProvider, hasDcPlanChanges, useConfigContext } from './ConfigContext';
import { DEFAULT_FORM_DATA } from './constants';
import { buildConfigPayload } from './buildConfigPayload';
import { previewConfiguration, updateWorkspace, Workspace } from '../../services/api';

const hydration = vi.hoisted(() => ({ slot: 0, loaded: true, failed: false, resolved: null as unknown }));
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
      if (slot === 13) {
        const [value, setValue] = actual.useState(initial);
        return [value, (next: unknown) => { hydration.resolved = next; setValue(next); }];
      }
      return actual.useState(initial);
    },
  };
});

vi.mock('./constants', async importOriginal => {
  const actual = await importOriginal<typeof import('./constants')>();
  return { ...actual, DEFAULT_FORM_DATA: { ...actual.DEFAULT_FORM_DATA } };
});
vi.mock('../../services/api', () => ({ updateWorkspace: vi.fn(), previewConfiguration: vi.fn() }));

describe('DC section unsaved marker', () => {
  it.each(['dcMatchResponseUpwardParticipation', 'dcCoreContributionRate', 'dcAutoEnrollHireDateCutoff', 'dcVoluntaryEnrollmentRate', 'dcMatchMinHoursAnnual'] as const)(
    'tracks edits to %s', key => {
      const saved = { ...DEFAULT_FORM_DATA };
      const changed = { ...saved, [key]: typeof saved[key] === 'string' ? 'changed' : saved[key] + 1 };
      expect(hasDcPlanChanges(changed, saved)).toBe(true);
      expect(hasDcPlanChanges(saved, saved)).toBe(false);
    },
  );
});

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

describe('Enrollment and escalation cutoff hydration', () => {
  it.each([false, true])('does not invent a cutoff with escalation enabled=%s', enabled => {
    const form = applyConfigToFormData({
      simulation: { start_year: 2028 },
      dc_plan: { auto_escalation: enabled },
    }, { ...DEFAULT_FORM_DATA, dcEscalationHireDateCutoff: '' });
    expect(form.dcEscalationHireDateCutoff).toBe('');
    expect(buildConfigPayload(form, null, null).dc_plan.escalation_hire_date_cutoff).toBe('');
  });

  it.each([false, true])('honors cleared scenario cutoffs with enrollment/escalation enabled=%s', enabled => {
    const inherited = applyConfigToFormData({ dc_plan: {
      auto_enroll_hire_date_cutoff: '2019-04-03',
      escalation_hire_date_cutoff: '2018-06-01',
    } }, DEFAULT_FORM_DATA);
    const form = applyConfigToFormData({ dc_plan: {
      auto_enroll: enabled,
      auto_escalation: enabled,
      auto_enroll_hire_date_cutoff: '',
      escalation_hire_date_cutoff: '',
    } }, inherited);
    expect(form.dcAutoEnrollHireDateCutoff).toBe('');
    expect(form.dcEscalationHireDateCutoff).toBe('');
    const payload = buildConfigPayload(form, null, null);
    expect(payload.dc_plan.auto_enroll_hire_date_cutoff).toBe('');
    expect(payload.dc_plan.escalation_hire_date_cutoff).toBe('');
  });

  it('honors an explicit null escalation cutoff instead of restoring an inherited date', () => {
    const form = applyConfigToFormData({ dc_plan: { escalation_hire_date_cutoff: null } }, {
      ...DEFAULT_FORM_DATA, dcEscalationHireDateCutoff: '2018-06-01',
    });
    expect(form.dcEscalationHireDateCutoff).toBe('');
  });

  it.each([false, true])('retains inherited cutoffs when only enrollment/escalation enabled=%s changes', enabled => {
    const previous = { ...DEFAULT_FORM_DATA,
      dcAutoEnrollHireDateCutoff: '2019-04-03', dcEscalationHireDateCutoff: '2018-06-01',
    };
    const form = applyConfigToFormData({ dc_plan: { auto_enroll: enabled, auto_escalation: enabled } }, previous);
    expect(form.dcAutoEnrollHireDateCutoff).toBe(previous.dcAutoEnrollHireDateCutoff);
    expect(form.dcEscalationHireDateCutoff).toBe(previous.dcEscalationHireDateCutoff);
  });
});

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
    hydration.resolved = null;
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

  it('refreshes resolved engine variables after a successful save', async () => {
    vi.mocked(previewConfiguration).mockResolvedValueOnce({ configuration: {}, engine_variables: { employer_match: { apply_eligibility: true } }, scope: 'workspace' });
    expect(await saveFromProvider()()).toBe(true);
    expect(previewConfiguration).toHaveBeenCalledWith('synthetic', expect.objectContaining({ simulation: expect.any(Object) }), 'workspace');
    expect(hydration.resolved).toEqual({ employer_match: { apply_eligibility: true } });
  });

  it('clears the old engine view if the saved configuration cannot be previewed', async () => {
    vi.mocked(previewConfiguration).mockRejectedValueOnce(new Error('Preview unavailable'));
    expect(await saveFromProvider()()).toBe(true);
    expect(hydration.resolved).toEqual({});
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
