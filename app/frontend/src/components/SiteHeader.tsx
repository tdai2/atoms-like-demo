import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, LogOut, Menu, X } from 'lucide-react';
import { useStartFree } from '@/hooks/useStartFree';
import { useAuthStatus } from '@/hooks/useAuthStatus';

const NAV = [
  { label: '产品能力', href: '/#capabilities' },
  { label: '模板库', href: '/#templates' },
  { label: '定价', href: '/#pricing' },
  { label: '我的项目', to: '/projects' },
  { label: '文档', to: '/docs' },
  { label: '更新日志', to: '/changelog' },
];

const linkClass =
  'focus-ring rounded-[6px] text-[14px] text-[#a0a6af] transition-colors hover:text-[#f2f4f5]';

/** 账号区：未登录显示登录入口，已登录显示账号与登出按钮。 */
function AccountActions({ onNavigate }: { onNavigate?: () => void }) {
  const { state, user, logout } = useAuthStatus();
  const [loggingOut, setLoggingOut] = useState(false);
  const { startFree } = useStartFree();

  const handleLogout = async () => {
    onNavigate?.();
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
    }
  };

  if (state === 'loading') {
    return (
      <span className="font-mono-ui flex items-center gap-2 text-[13px] text-[#6b727c]">
        <Loader2 size={14} className="animate-spin" />
        账号检查中
      </span>
    );
  }

  if (state === 'authenticated') {
    return (
      <>
        <span
          title={user?.email}
          className="max-w-[160px] truncate font-mono-ui text-[13px] text-[#a0a6af]"
        >
          {user?.email ?? '已登录'}
        </span>
        <button
          type="button"
          onClick={handleLogout}
          disabled={loggingOut}
          className="focus-ring inline-flex items-center gap-1.5 rounded-[10px] border border-[#24272d] !bg-transparent px-3.5 py-2 text-[14px] font-medium text-[#a0a6af] transition-colors hover:!bg-transparent hover:text-[#f2f4f5] disabled:opacity-60"
        >
          <LogOut size={14} />
          {loggingOut ? '退出中…' : '退出登录'}
        </button>
      </>
    );
  }

  return (
    <>
      <Link
        to="/signin"
        className="focus-ring rounded-[10px] border border-[#24272d] !bg-transparent px-3.5 py-2 text-[14px] font-medium text-[#a0a6af] transition-colors hover:!bg-transparent hover:text-[#f2f4f5]"
      >
        登录
      </Link>
      <button
        type="button"
        onClick={startFree}
        className="focus-ring rounded-[10px] bg-[#c8f751] px-4 py-2 text-[14px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
      >
        免费开始
      </button>
    </>
  );
}

export default function SiteHeader() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-[#24272d] bg-[rgba(11,12,14,0.72)] backdrop-blur-[12px]">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-4 sm:px-6">
        <Link to="/" className="focus-ring flex items-center gap-2.5 rounded-[8px]">
          <span className="relative flex h-7 w-7 items-center justify-center rounded-[8px] border border-[#c8f751] bg-[rgba(200,247,81,0.12)]">
            <span className="h-2 w-2 rounded-full bg-[#c8f751]" />
          </span>
          <span className="font-mono-ui text-[15px] font-semibold tracking-[0.04em] text-[#f2f4f5]">atoms</span>
        </Link>

        <nav className="hidden items-center gap-7 md:flex">
          {NAV.map((n) =>
            n.to ? (
              <Link key={n.label} to={n.to} className={linkClass}>
                {n.label}
              </Link>
            ) : (
              <a key={n.label} href={n.href} className={linkClass}>
                {n.label}
              </a>
            ),
          )}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <AccountActions />
        </div>

        <button
          type="button"
          aria-label={open ? '关闭菜单' : '打开菜单'}
          onClick={() => setOpen((v) => !v)}
          className="focus-ring flex h-10 w-10 items-center justify-center rounded-[8px] border border-[#24272d] text-[#a0a6af] md:hidden"
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>

      {open && (
        <div className="border-t border-[#24272d] bg-[#0b0c0e] px-4 py-4 md:hidden">
          <div className="flex flex-col gap-1">
            {NAV.map((n) =>
              n.to ? (
                <Link
                  key={n.label}
                  to={n.to}
                  onClick={() => setOpen(false)}
                  className="rounded-[8px] px-2 py-2.5 text-[15px] text-[#a0a6af]"
                >
                  {n.label}
                </Link>
              ) : (
                <a
                  key={n.label}
                  href={n.href}
                  onClick={() => setOpen(false)}
                  className="rounded-[8px] px-2 py-2.5 text-[15px] text-[#a0a6af]"
                >
                  {n.label}
                </a>
              ),
            )}

            <div className="mt-3 flex flex-col gap-2 border-t border-[#24272d] pt-3">
              <AccountActions onNavigate={() => setOpen(false)} />
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
