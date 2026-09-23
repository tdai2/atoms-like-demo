import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Check, Loader2, UserPlus } from 'lucide-react';
import SiteHeader from '@/components/SiteHeader';
import { useAuthStatus } from '@/hooks/useAuthStatus';

/**
 * 注册入口：Atoms 账号体系与平台登录页共用同一入口（登录页内含注册），
 * 因此这里作为产品侧的「注册页」，说明注册权益并提供明确的注册按钮。
 */
export default function SignUp() {
  const { state, login } = useAuthStatus();
  const navigate = useNavigate();
  const [redirecting, setRedirecting] = useState(false);

  // 已登录用户不需要再注册，直接回到需求输入区开始生成。
  useEffect(() => {
    if (state === 'authenticated') navigate('/', { replace: true });
  }, [state, navigate]);

  // 只有用户明确点击才离开本页：平台账号页可返回，避免自动跳转形成循环。
  const handleSignUp = () => {
    setRedirecting(true);
    login();
  };

  const benefits = [
    '注册即送 20 次生成额度，按自然月重置',
    '一句话需求生成可运行的应用预览',
    '项目、版本与六阶段流水线记录自动归档',
  ];

  return (
    <div className="min-h-screen bg-[#0b0c0e]">
      <SiteHeader />
      <main className="mx-auto max-w-[720px] px-4 py-20 sm:px-6">
        <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">sign up</p>
        <h1 className="mt-3 text-[30px] font-bold leading-[1.15] tracking-[-0.01em] text-[#f2f4f5] sm:text-[36px]">
          创建你的 Atoms 账号
        </h1>
        <p className="mt-3 max-w-[56ch] text-[15px] leading-[1.65] text-[#a0a6af]">
          账号由 Atoms 统一提供，注册与登录使用同一个入口。完成后会自动回到首页，直接开始生成你的第一个应用。
        </p>

        <ul className="mt-8 space-y-3">
          {benefits.map((item) => (
            <li key={item} className="flex items-start gap-2.5 text-[14px] text-[#a0a6af]">
              <Check size={16} className="mt-0.5 shrink-0 text-[#c8f751]" />
              {item}
            </li>
          ))}
        </ul>

        {state === 'loading' && (
          <div className="mt-10 flex items-center gap-3 rounded-[14px] border border-[#24272d] bg-[#17191d] px-5 py-6">
            <Loader2 size={18} className="animate-spin text-[#c8f751]" />
            <span className="font-mono-ui text-[13px] text-[#a0a6af]">正在检查账号状态…</span>
          </div>
        )}

        {state === 'anonymous' && (
          <div className="mt-10 rounded-[14px] border border-[#c8f751] bg-[#17191d] p-6">
            <h2 className="text-[18px] font-semibold text-[#f2f4f5]">
              {redirecting ? '正在前往注册页面' : '前往注册'}
            </h2>
            <p className="mt-2 text-[14px] leading-[1.65] text-[#a0a6af]">
              点击下方按钮前往账号页，在页面中选择「注册」即可完成账号创建。
            </p>
            <button
              type="button"
              onClick={handleSignUp}
              className="focus-ring mt-6 inline-flex h-11 items-center gap-2 rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
            >
              <UserPlus size={16} />
              注册 / 登录
            </button>
            <p className="mt-4 text-[13px] text-[#6b727c]">
              已有账号？
              <Link to="/signin" className="focus-ring ml-1 rounded-[6px] text-[#c8f751] underline">
                使用登录入口
              </Link>
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
