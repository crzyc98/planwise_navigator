import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { DEFAULT_FORM_DATA } from './constants';
import { DataSourcesSection } from './DataSourcesSection';

const state = vi.hoisted(() => ({ value: {} as Record<string, unknown> }));
vi.mock('./ConfigContext', () => ({ useConfigContext: () => state.value }));
vi.mock('../../hooks/useWorkspaceNavigation', () => ({ useWorkspacePath: () => '/import' }));

beforeEach(() => {
  state.value = { formData: { ...DEFAULT_FORM_DATA }, scenarioLoading: false };
});

const render = () => renderToStaticMarkup(<MemoryRouter><DataSourcesSection /></MemoryRouter>);

it('displays the same resolved scenario census used by the analysis controls', () => {
  state.value.formData = {
    ...DEFAULT_FORM_DATA, censusDataPath: '/workspace/custom.parquet',
    censusDataSource: 'scenario', censusDataStatus: 'loaded', censusRowCount: 17,
  };
  const html = render();
  expect(html).toContain('custom.parquet');
  expect(html).toContain('own census file');
  expect(html).toContain('17');
});

it('shows inherited census after a missing override falls back', () => {
  state.value.formData = {
    ...DEFAULT_FORM_DATA, censusDataPath: '/workspace/census.parquet',
    censusDataSource: 'workspace', censusDataStatus: 'loaded', censusRowCount: 12,
  };
  expect(render()).toContain('inherited from this workspace');
  expect(render()).toContain('census.parquet');
});

it('does not show stale loaded data while a scenario is loading', () => {
  state.value.scenarioLoading = true;
  state.value.formData = { ...DEFAULT_FORM_DATA, censusDataPath: 'old.parquet', censusDataStatus: 'loaded' };
  expect(render()).toContain('Checking census file');
  expect(render()).not.toContain('old.parquet');
});
