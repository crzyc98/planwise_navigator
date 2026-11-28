import { useEffect, useState } from 'react';

// Below Tailwind's `sm` breakpoint a 256px in-flow sidebar leaves too little room
// for the page, so there the sidebar rests collapsed and expands as an overlay.
export const NARROW_VIEWPORT_QUERY = '(max-width: 639px)';

export function useNarrowViewport(): boolean {
  const [isNarrow, setIsNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(NARROW_VIEWPORT_QUERY).matches,
  );

  useEffect(() => {
    const mediaQuery = window.matchMedia(NARROW_VIEWPORT_QUERY);
    const handleChange = (event: MediaQueryListEvent) => setIsNarrow(event.matches);
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  return isNarrow;
}

export interface SidebarShellInput {
  isNarrow: boolean;
  desktopCollapsed: boolean;
  overlayOpen: boolean;
}

export interface SidebarShell {
  collapsed: boolean;
  overlay: boolean;
  asideClassName: string;
}

const BASE_ASIDE_CLASSES = 'bg-surface-raised border-r border-border flex flex-col flex-shrink-0 transition-all duration-200';

export function sidebarShell({ isNarrow, desktopCollapsed, overlayOpen }: SidebarShellInput): SidebarShell {
  if (isNarrow && overlayOpen) {
    return {
      collapsed: false,
      overlay: true,
      asideClassName: `w-64 ${BASE_ASIDE_CLASSES} fixed inset-y-0 left-0 z-40 shadow-xl`,
    };
  }
  const collapsed = isNarrow || desktopCollapsed;
  return {
    collapsed,
    overlay: false,
    asideClassName: `${collapsed ? 'w-16' : 'w-64'} ${BASE_ASIDE_CLASSES} z-10`,
  };
}
