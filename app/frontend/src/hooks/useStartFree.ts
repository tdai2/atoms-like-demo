import { useCallback, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuthStatus } from '@/hooks/useAuthStatus';
import { consumeStartFreeIntent, emitStartFreeFocus, markStartFreeIntent } from '@/lib/startFree';

/**
 * 统一的「免费开始」入口：未登录先进入注册/登录流程，完成后回到首页需求输入区；
 * 已登录则直接回到输入区并聚焦，省去一次多余跳转。
 */
export function useStartFree() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { state } = useAuthStatus();
  // 账号态未解析完成时点击：先记住点击，待解析后再决定去注册页还是回输入区。
  const pendingClick = useRef(false);

  const startFree = useCallback(() => {
    if (state === 'loading') {
      pendingClick.current = true;
      markStartFreeIntent('register');
      return;
    }
    if (state !== 'authenticated') {
      markStartFreeIntent('register');
      navigate('/signup');
      return;
    }
    if (pathname !== '/') {
      // 交给路由与首页消费意图，避免在这里直接操作尚未挂载的 DOM。
      markStartFreeIntent('console');
      navigate('/');
      return;
    }
    consumeStartFreeIntent();
    emitStartFreeFocus();
  }, [state, pathname, navigate]);

  useEffect(() => {
    if (state === 'loading' || !pendingClick.current) return;
    pendingClick.current = false;
    if (state === 'authenticated') {
      if (pathname !== '/') navigate('/');
      return;
    }
    navigate('/signup');
  }, [state, pathname, navigate]);

  return { startFree, resolving: state === 'loading' };
}
