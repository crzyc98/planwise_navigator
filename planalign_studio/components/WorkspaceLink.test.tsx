import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import WorkspaceLink from './WorkspaceLink';

const render = (entry: string, routePath: string) => renderToStaticMarkup(
  <MemoryRouter initialEntries={[entry]}>
    <Routes>
      <Route path={routePath} element={<WorkspaceLink to="/simulate/s1">Open</WorkspaceLink>} />
    </Routes>
  </MemoryRouter>,
);

describe('WorkspaceLink', () => {
  it('keeps the link inside the workspace in the current route', () => {
    expect(render('/w/client-a/simulate', '/w/:workspaceId/*')).toContain('href="/w/client-a/simulate/s1"');
  });

  it('leaves the path alone outside a workspace route', () => {
    expect(render('/elsewhere', '/elsewhere')).toContain('href="/simulate/s1"');
  });
});
