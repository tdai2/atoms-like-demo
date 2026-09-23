import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2 } from 'lucide-react';

/** 平台登出后的回跳页：确认登出完成并自动回到首页。 */
export default function LogoutCallbackPage() {
  useEffect(() => {
    const timer = window.setTimeout(() => {
      window.location.assign('/');
    }, 2000);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0b0c0e] px-4">
      <div className="w-full max-w-[420px] rounded-[14px] border border-[#24272d] bg-[#17191d] p-8 text-center">
        <span className="inline-flex h-11 w-11 items-center justify-center rounded-full bg-[rgba(74,222,128,0.14)]">
          <CheckCircle2 size={22} className="text-[#4ade80]" />
        </span>
        <h1 className="mt-4 text-[20px] font-semibold text-[#f2f4f5]">已退出登录</h1>
        <p className="mt-2 text-[14px] leading-[1.65] text-[#a0a6af]">账号状态已清理，正在返回首页…</p>
        <Link
          to="/"
          className="focus-ring mt-6 inline-flex h-11 items-center rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
        >
          回到首页
        </Link>
      </div>
    </div>
  );
}
