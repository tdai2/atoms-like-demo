import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Menu, X } from 'lucide-react';

const NAV = [
  { label: '产品能力', href: '/#capabilities' },
  { label: '模板库', href: '/#templates' },
  { label: '定价', href: '/#pricing' },
  { label: '我的项目', to: '/projects' },
  { label: '文档', to: '/docs' },
  { label: '更新日志', to: '/changelog' },
];

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
              <Link key={n.label} to={n.to} className="focus-ring rounded-[6px] text-[14px] text-[#a0a6af] transition-colors hover:text-[#f2f4f5]">
                {n.label}
              </Link>
            ) : (
              <a key={n.label} href={n.href} className="focus-ring rounded-[6px] text-[14px] text-[#a0a6af] transition-colors hover:text-[#f2f4f5]">
                {n.label}
              </a>
            ),
          )}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            to="/signin"
            className="focus-ring rounded-[10px] border border-[#24272d] !bg-transparent px-3.5 py-2 text-[14px] font-medium text-[#a0a6af] transition-colors hover:!bg-transparent hover:text-[#f2f4f5]"
          >
            登录
          </Link>
          <a
            href="#console"
            className="focus-ring rounded-[10px] bg-[#c8f751] px-4 py-2 text-[14px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
          >
            免费开始
          </a>
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
                <Link key={n.label} to={n.to} onClick={() => setOpen(false)} className="rounded-[8px] px-2 py-2.5 text-[15px] text-[#a0a6af]">
                  {n.label}
                </Link>
              ) : (
                <a key={n.label} href={n.href} onClick={() => setOpen(false)} className="rounded-[8px] px-2 py-2.5 text-[15px] text-[#a0a6af]">
                  {n.label}
                </a>
              ),
            )}
            <a
              href="#console"
              onClick={() => setOpen(false)}
              className="mt-2 rounded-[10px] bg-[#c8f751] px-4 py-2.5 text-center text-[15px] font-semibold text-[#0b0c0e]"
            >
              免费开始
            </a>
          </div>
        </div>
      )}
    </header>
  );
}
