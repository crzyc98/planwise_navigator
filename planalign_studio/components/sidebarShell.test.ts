import { describe, expect, it } from 'vitest';
import { sidebarShell } from './sidebarShell';

const classes = (className: string) => className.split(' ');

describe('sidebarShell', () => {
  it('keeps the desktop sidebar in the page flow, expanded or collapsed by the toggle', () => {
    const expanded = sidebarShell({ isNarrow: false, desktopCollapsed: false, overlayOpen: false });
    expect(expanded.collapsed).toBe(false);
    expect(expanded.overlay).toBe(false);
    expect(classes(expanded.asideClassName)).toEqual(expect.arrayContaining(['w-64', 'z-10', 'flex-shrink-0']));
    expect(classes(expanded.asideClassName)).not.toContain('fixed');

    const collapsed = sidebarShell({ isNarrow: false, desktopCollapsed: true, overlayOpen: false });
    expect(collapsed.collapsed).toBe(true);
    expect(classes(collapsed.asideClassName)).toContain('w-16');
  });

  it('ignores the overlay flag on desktop', () => {
    const shell = sidebarShell({ isNarrow: false, desktopCollapsed: false, overlayOpen: true });
    expect(shell.overlay).toBe(false);
    expect(classes(shell.asideClassName)).not.toContain('fixed');
  });

  it('rests collapsed at phone width even when the desktop sidebar is expanded', () => {
    const shell = sidebarShell({ isNarrow: true, desktopCollapsed: false, overlayOpen: false });
    expect(shell.collapsed).toBe(true);
    expect(shell.overlay).toBe(false);
    expect(classes(shell.asideClassName)).toContain('w-16');
  });

  it('expands over the page at phone width instead of pushing it', () => {
    const shell = sidebarShell({ isNarrow: true, desktopCollapsed: true, overlayOpen: true });
    expect(shell.collapsed).toBe(false);
    expect(shell.overlay).toBe(true);
    expect(classes(shell.asideClassName)).toEqual(expect.arrayContaining(['w-64', 'fixed', 'inset-y-0', 'left-0', 'z-40']));
  });
});
