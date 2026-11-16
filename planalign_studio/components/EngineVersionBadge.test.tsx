import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import EngineVersionBadge from './EngineVersionBadge';

function render(gap: 'patch' | 'minor' | 'major' | null, version: string | null = '3.1.0') {
  return renderToStaticMarkup(
    <MemoryRouter>
      <EngineVersionBadge scenario={{ id: 's1', result_engine_version: version, result_engine_version_gap: gap }} />
    </MemoryRouter>,
  );
}

describe('EngineVersionBadge', () => {
  it('flags a minor or major gap as a warning with a rerun action', () => {
    for (const gap of ['minor', 'major'] as const) {
      const html = render(gap);
      expect(html).toContain('Run on 3.1.0');
      expect(html).toContain('bg-warning-surface');
      expect(html).toContain('Rerun');
    }
  });

  it('shows a patch-only gap without warning styling', () => {
    const html = render('patch', '3.2.0');
    expect(html).toContain('Run on 3.2.0');
    expect(html).not.toContain('warning');
    expect(html).toContain('text-ink-muted');
  });

  it('shows a current version quietly, without a warning or rerun action', () => {
    const html = render(null, '3.2.0');
    expect(html).toContain('Run on 3.2.0');
    expect(html).toContain('text-ink-muted');
    expect(html).not.toContain('warning');
    expect(html).not.toContain('Rerun');
    expect(html).not.toContain('<svg');
  });

  it('renders nothing when the version is unknown', () => {
    expect(render(null, null)).toBe('');
    expect(render('minor', null)).toBe('');
  });
});
