import { cn } from '@/lib/utils';
import type { MiniAppKind } from '@/data/site';

const bars = [38, 62, 46, 78, 55, 92, 70];

function Dashboard() {
  return (
    <div className="p-4 sm:p-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm font-semibold text-[#f2f4f5]">增长概览</p>
        <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-2 py-0.5 text-[11px] text-[#a0a6af]">近 7 天</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[
          { k: '新增用户', v: '2,481', d: '+12.4%' },
          { k: '活跃留存', v: '64.2%', d: '+3.1%' },
          { k: '付费转化', v: '8.7%', d: '-0.4%' },
        ].map((m) => (
          <div key={m.k} className="rounded-[10px] border border-[#24272d] bg-[#141619] p-2.5">
            <p className="text-[11px] text-[#6b727c]">{m.k}</p>
            <p className="font-mono-ui mt-1 text-base font-semibold text-[#f2f4f5]">{m.v}</p>
            <p className={cn('font-mono-ui text-[10px]', m.d.startsWith('+') ? 'text-[#4ade80]' : 'text-[#f87171]')}>{m.d}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 flex h-28 items-end gap-2 rounded-[10px] border border-[#24272d] bg-[#141619] p-3">
        {bars.map((b, i) => (
          <div key={i} className="flex-1 rounded-[3px] bg-[#c8f751]" style={{ height: `${b}%`, opacity: 0.35 + i * 0.09 }} />
        ))}
      </div>
    </div>
  );
}

function Landing() {
  return (
    <div className="p-4 sm:p-5">
      <div className="rounded-[10px] border border-[#24272d] bg-gradient-to-br from-[#1b1d21] to-[#141619] p-5">
        <p className="font-mono-ui text-[10px] uppercase tracking-[0.18em] text-[#c8f751]">brew club</p>
        <p className="mt-2 text-xl font-bold leading-tight text-[#f2f4f5]">每周一包<br />现烘手冲豆</p>
        <p className="mt-2 text-[12px] text-[#a0a6af]">按口味定制，随时暂停或更换。</p>
        <span className="mt-3 inline-block rounded-[8px] bg-[#c8f751] px-3 py-1.5 text-[12px] font-semibold text-[#0b0c0e]">
          开始订阅
        </span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {['轻盈果香', '均衡坚果', '浓郁可可'].map((t) => (
          <div key={t} className="rounded-[10px] border border-[#24272d] bg-[#141619] p-2.5 text-center">
            <div className="mx-auto h-8 w-8 rounded-full bg-[#24272d]" />
            <p className="mt-2 text-[11px] text-[#a0a6af]">{t}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function Todo() {
  const items = [
    { t: '梳理 Q3 增长实验清单', done: true },
    { t: '完成登录页改版评审', done: true },
    { t: '接入埋点上报 SDK', done: false },
    { t: '撰写版本发布说明', done: false },
  ];
  return (
    <div className="p-4 sm:p-5">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-[#f2f4f5]">本周任务</p>
        <span className="font-mono-ui text-[11px] text-[#a0a6af]">2 / 4 已完成</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#24272d]">
        <div className="h-full w-1/2 rounded-full bg-[#c8f751]" />
      </div>
      <ul className="mt-3 space-y-2">
        {items.map((it) => (
          <li key={it.t} className="flex items-center gap-2.5 rounded-[10px] border border-[#24272d] bg-[#141619] px-3 py-2.5">
            <span
              className={cn(
                'flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border text-[10px]',
                it.done ? 'border-[#c8f751] bg-[#c8f751] text-[#0b0c0e]' : 'border-[#3a3f47] text-transparent',
              )}
            >
              ✓
            </span>
            <span className={cn('text-[12px]', it.done ? 'text-[#6b727c] line-through' : 'text-[#f2f4f5]')}>{it.t}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function MiniApp({ kind }: { kind: MiniAppKind }) {
  if (kind === 'landing') return <Landing />;
  if (kind === 'todo') return <Todo />;
  return <Dashboard />;
}
