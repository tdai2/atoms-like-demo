import { useCallback, useEffect, useState } from 'react';
import { client } from '@/lib/api';

export interface AuthUser {
  id: string;
  email: string;
  name?: string;
  role?: string;
}

export type AuthState = 'loading' | 'authenticated' | 'anonymous';

/**
 * Atoms 账号状态：loading / authenticated / anonymous 三态。
 * 仅在 me() 返回空或失败时判定为未登录，业务接口失败不会触发跳转登录。
 */
export function useAuthStatus() {
  const [state, setState] = useState<AuthState>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await client.auth.me();
      const profile = response?.data as AuthUser | undefined;
      if (profile) {
        setUser(profile);
        setState('authenticated');
        return;
      }
      setUser(null);
      setState('anonymous');
    } catch {
      setUser(null);
      setState('anonymous');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(() => {
    client.auth.toLogin();
  }, []);

  const logout = useCallback(() => {
    client.auth.logout();
  }, []);

  return { state, user, login, logout, refresh };
}
