import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import type { SessionUser } from './permissions';
export function RoleGuard({
  check,
  children,
}: {
  check: (user: SessionUser | null) => boolean;
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  return check(user) ? <>{children}</> : <Navigate to="/403" replace />;
}
