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

  /**
   * 发起登录。Atoms 账号不支持独立的注册接口（登录页内含注册入口），
   * 因此未登录用户统一进入平台账号页，由平台页面区分注册与登录。
   */
  const login = useCallback(() => {
    client.auth.toLogin();
  }, []);

  /** 登出：SDK 会清除本地令牌并跳回首页，先本地复位避免顶栏残留登录态。 */
  const logout = useCallback(async () => {
    setUser(null);
    setState('anonymous');
    await client.auth.logout();
  }, []);

  return { state, user, login, logout, refresh };
}
