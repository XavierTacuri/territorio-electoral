import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiRequest, tokenStore } from '../api/client';
import { queryClient } from '../app/queryClient';
import type { SessionUser } from './permissions';

type AuthContextValue = {
  user: SessionUser | null;
  loading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};
const AuthContext = createContext<AuthContextValue | null>(null);
type BrowserToken = { access_token: string; user: SessionUser };

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const expire = useCallback(() => {
    tokenStore.set(null);
    setUser(null);
    queryClient.clear();
  }, []);
  useEffect(() => {
    tokenStore.onExpired(expire);
    apiRequest<{ user: SessionUser }>('/auth/browser/session', { retryAuth: false })
      .then(async ({ user: sessionUser }) => {
        const refreshed = await apiRequest<BrowserToken>('/auth/browser/refresh', {
          method: 'POST',
          retryAuth: false,
          headers: {
            'X-CSRF-Token': decodeURIComponent(
              document.cookie
                .split('; ')
                .find((x) => x.startsWith('te_csrf='))
                ?.split('=')[1] ?? '',
            ),
          },
        });
        tokenStore.set(refreshed.access_token);
        setUser(sessionUser);
      })
      .catch(expire)
      .finally(() => setLoading(false));
  }, [expire]);
  const login = useCallback(async (identifier: string, password: string) => {
    const result = await apiRequest<BrowserToken>('/auth/browser/login', {
      method: 'POST',
      retryAuth: false,
      body: JSON.stringify({ identifier, password }),
    });
    tokenStore.set(result.access_token);
    setUser(result.user);
  }, []);
  const logout = useCallback(async () => {
    const csrf = decodeURIComponent(
      document.cookie
        .split('; ')
        .find((x) => x.startsWith('te_csrf='))
        ?.split('=')[1] ?? '',
    );
    try {
      await apiRequest('/auth/browser/logout', {
        method: 'POST',
        retryAuth: false,
        headers: { 'X-CSRF-Token': csrf },
      });
    } finally {
      expire();
    }
  }, [expire]);
  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider requerido');
  return value;
}
