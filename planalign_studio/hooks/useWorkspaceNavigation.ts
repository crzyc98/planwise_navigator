import { useCallback } from 'react';
import { NavigateOptions, useNavigate, useParams } from 'react-router-dom';

/** Navigate within the workspace encoded in the current route. */
export function useWorkspaceNavigate() {
  const navigate = useNavigate();
  const { workspaceId } = useParams<{ workspaceId: string }>();

  return useCallback((path: string | number, options?: NavigateOptions) => {
    if (typeof path === 'number') {
      navigate(path);
      return;
    }
    if (!workspaceId || !path.startsWith('/')) {
      navigate(path, options);
      return;
    }
    navigate(`/w/${workspaceId}${path === '/' ? '' : path}`, options);
  }, [navigate, workspaceId]);
}

/** Build an absolute link that retains the current workspace route segment. */
export function useWorkspacePath(path: string): string {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  if (!workspaceId || !path.startsWith('/')) return path;
  return `/w/${workspaceId}${path === '/' ? '' : path}`;
}
