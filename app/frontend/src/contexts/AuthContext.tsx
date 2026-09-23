import React, { createContext, useCallback, useContext, useMemo, ReactNode } from 'react';
import { useAuthStatus, type AuthUser } from '@/hooks/useAuthStatus';

/**
 * 账号上下文：唯一数据源是 Atoms 内置账号体系（`client.auth.*`）。
 * 仓库内不再保留第二套自建登录实现，`user` 直接来自 `client.auth.me()`。
 */

export type { AuthUser };

interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  refetch: () => Promise<void>;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const { state, user, login, logout, refresh } = useAuthStatus();

  const handleLogin = useCallback(async () => {
    login();
  }, [login]);

  const handleLogout = useCallback(async () => {
    logout();
  }, [logout]);

  const value = useMemo<AuthContextType>(
    () => ({
      user,
      loading: state === 'loading',
      error: null,
      login: handleLogin,
      logout: handleLogout,
      refetch: refresh,
      isAdmin: user?.role === 'admin',
    }),
    [user, state, handleLogin, handleLogout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
