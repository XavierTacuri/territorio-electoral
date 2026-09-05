import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { ApiError } from '../api/errors';
import { apiRequest, tokenStore } from '../api/client';
import { queryClient } from '../app/queryClient';
import {
  clearSessionSnapshot,
  getSessionSnapshot,
  saveSessionSnapshot,
} from '../offline/sessionRepository';
import type { SessionUser } from './permissions';

type AuthContextValue = {
  user: SessionUser | null;
  loading: boolean;
  offlineSession: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};
const AuthContext = createContext<AuthContextValue | null>(null);
type BrowserToken = { access_token: string; user: SessionUser };

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [offlineSession, setOfflineSession] = useState(false);
  const expire = useCallback(() => {
    tokenStore.set(null);
    setUser(null);
    setOfflineSession(false);
    queryClient.clear();
    void clearSessionSnapshot();
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
        setOfflineSession(false);
        void saveSessionSnapshot(sessionUser);
      })
      .catch(async (error: unknown) => {
        // A real ApiError means the server rejected the session (expired,
        // revoked) — always log out. A network failure (offline, unreachable
        // host) does not: fall back to the last known identity so an already
        // authenticated coordinator can keep using cached field data instead
        // of being bounced to the login screen the moment connectivity drops.
        if (error instanceof ApiError || navigator.onLine) {
          expire();
          return;
        }
        const snapshot = await getSessionSnapshot();
        if (snapshot) {
          setUser(snapshot.user);
          setOfflineSession(true);
        } else {
          expire();
        }
      })
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
    setOfflineSession(false);
    void saveSessionSnapshot(result.user);
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
  const value = useMemo(
    () => ({ user, loading, offlineSession, login, logout }),
    [user, loading, offlineSession, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider requerido');
  return value;
}
