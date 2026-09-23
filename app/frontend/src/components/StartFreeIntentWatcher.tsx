import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuthStatus } from '@/hooks/useAuthStatus';
import { consumeStartFreeIntent, emitStartFreeFocus, peekStartFreeIntent } from '@/lib/startFree';

/**
 * 在任意路由消费「免费开始」意图。
 *
 * 登录后的落点由平台回调页决定，本应用无法指定，所以这里全局兜底：
 * 只要账号态解析为已登录且仍有未消费的意图，就回到首页需求输入区并聚焦。
 */
export default function StartFreeIntentWatcher() {
  const { state } = useAuthStatus();
  const { pathname } = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (state !== 'authenticated' || !peekStartFreeIntent()) return;
    if (pathname !== '/') {
      navigate('/');
      return;
    }
    consumeStartFreeIntent();
    emitStartFreeFocus();
  }, [state, pathname, navigate]);

  return null;
}
