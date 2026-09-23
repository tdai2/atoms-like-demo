import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import SiteHeader from '@/components/SiteHeader';
import { useAuthStatus } from '@/hooks/useAuthStatus';

/**
 * 登录入口：统一走 Atoms 账号体系。
 * 未登录时自动跳转登录页；已登录则直接进入项目列表。
 */
export default function SignIn() {
  const { state, login } = useAuthStatus();

  useEffect(() => {
    if (state === 'anonymous') login();
  }, [state, login]);

  return (
    <div className="min-h-screen bg-[#0b0c0e]">
      <SiteHeader />
      <main className="mx-auto flex max-w-[720px] flex-col items-center px-4 py-24 text-center sm:px-6">
        {state === 'loading' && (
          <div className="flex flex-col items-center gap-3">
            <Loader2 size={22} className="animate-spin text-[#c8f751]" />
            <p className="font-mono-ui text-[13px] text-[#a0a6af]">正在检查登录状态…</p>
          </div>
        )}

        {state === 'anonymous' && (
          <>
            <h1 className="text-[28px] font-bold leading-[1.2] text-[#f2f4f5]">正在跳转到登录页</h1>
            <p className="mt-3 text-[15px] leading-[1.65] text-[#a0a6af]">
              如果没有自动跳转，请手动点击下方按钮使用 Atoms 账号登录。
            </p>
            <button
              type="button"
              onClick={login}
              className="focus-ring mt-6 inline-flex h-11 items-center gap-2 rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
            >
              重新发起登录
            </button>
          </>
        )}

        {state === 'authenticated' && (
          <>
            <h1 className="text-[28px] font-bold leading-[1.2] text-[#f2f4f5]">你已登录</h1>
            <p className="mt-3 text-[15px] leading-[1.65] text-[#a0a6af]">可以直接查看账号下的项目列表。</p>
            <Link
              to="/projects"
              className="focus-ring mt-6 inline-flex h-11 items-center gap-2 rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
            >
              前往我的项目
            </Link>
          </>
        )}
      </main>
    </div>
  );
}
