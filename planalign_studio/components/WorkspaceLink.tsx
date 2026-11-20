import React from 'react';
import { Link, LinkProps } from 'react-router-dom';
import { useWorkspacePath } from '../hooks/useWorkspaceNavigation';

/** A link that stays inside the workspace encoded in the current route. */
export default function WorkspaceLink({ to, ...props }: Omit<LinkProps, 'to'> & { to: string }) {
  return <Link to={useWorkspacePath(to)} {...props} />;
}
