import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Bug, Gauge, Sparkles } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import SiteHeader from '@/components/SiteHeader';
import { CHANGELOG, type ChangeType } from '@/data/changelog';

type FilterId = 'all' | ChangeType;

const TYPE_META: Record<ChangeType, { label: string; icon: LucideIcon; color: string; bg: string }> = {
  feature: { label: '新增', icon: Sparkles, color: '#c8f751', bg: 'rgba(200,247,81,0.12)' },
  improve: { label: '优化', icon: Gauge, color: '#7dd3fc', bg: 'rgba(125,211,252,0.12)' },
  fix: { label: '修复', icon: Bug, color: '#fbbf24', bg: 'rgba(251,191,36,0.12)' },
};

const FILTERS: Array<{ id: FilterId; label: string }> = [
  { id: 'all', label: '全部' },
  { id: 'feature', label: '新增' },
  { id: 'improve', label: '优化' },
  { id: 'fix', label: '修复' },
];

export default function Changelog() {
  const [active, setActive] = useState<FilterId>('all');

  const counts = useMemo(() => {
    const acc: Record<FilterId, number> = { all: 0, feature: 0, improve: 0, fix: 0 };
    CHANGELOG.forEach((release) => {
      release.items.forEach((item) => {
        acc.all += 1;
        acc[item.type] += 1;
      });
    });
    return acc;
  }, []);

  const releases = useMemo(
    () =>
      CHANGELOG.map((release) => ({
        ...release,
        items: active === 'all' ? release.items : release.items.filter((item) => item.type === active),
      })).filter((release) => release.items.length > 0),
    [active],
  );

  const latestVersion = CHANGELOG[0]?.version;

  return (
    <div className="min-h-screen bg-[#0b0c0e]">
      <SiteHeader />
      <main className="relative overflow-hidden">
        <div className="atom-grid absolute inset-0 opacity-60" aria-hidden />
        <div className="atom-glow absolute inset-0" aria-hidden />
        <div className="relative mx-auto max-w-[1200px] px-4 py-16 sm:px-6 sm:py-20">
          <p className="font-mono-ui text-[12px] font-medium uppercase tracking-[0.06em] text-[#6b727c]">release notes</p>
          <h1 className="mt-3 text-[36px] font-bold leading-[1.15] tracking-[-0.02em] text-[#f2f4f5] sm:text-[48px]">
            更新日志
          </h1>
          <p className="mt-4 max-w-[620px] text-[16px] leading-[1.65] text-[#a0a6af]">
            记录平台的功能迭代与模型升级。可以按类型筛选，也可以直接跳到某个版本。
          </p>
          <p className="font-mono-ui mt-5 text-[12px] text-[#6b727c]">
            {`total: ${counts.all} · versions: ${CHANGELOG.length} · latest: ${CHANGELOG[0]?.date ?? '—'}`}
          </p>

          <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,1fr)_240px] lg:gap-12">
            <div>
              <div className="flex flex-wrap gap-2" role="group" aria-label="按变更类型筛选">
                {FILTERS.map((filter) => {
                  const selected = active === filter.id;
                  return (
                    <button
                      key={filter.id}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => setActive(filter.id)}
                      className={`focus-ring rounded-[6px] border px-3 py-1.5 text-[13px] font-medium transition-colors ${
                        selected
                          ? 'border-[#c8f751] bg-[rgba(200,247,81,0.12)] text-[#c8f751]'
                          : 'border-[#24272d] text-[#a0a6af] hover:border-[#3a3f47] hover:text-[#f2f4f5]'
                      }`}
                    >
                      {filter.label}
                      <span className="font-mono-ui ml-2 text-[11px] text-[#6b727c]">{counts[filter.id]}</span>
                    </button>
                  );
                })}
              </div>

              {releases.length === 0 ? (
                <p className="font-mono-ui mt-8 rounded-[14px] border border-[#24272d] bg-[#17191d] px-4 py-6 text-center text-[13px] text-[#6b727c]">
                  no entries — 该类型暂无更新记录。
                </p>
              ) : (
                <ol className="mt-8 flex flex-col gap-5">
                  {releases.map((release) => (
                    <li key={release.version}>
                      <article
                        id={release.version}
                        className="scroll-mt-24 rounded-[14px] border border-[#24272d] bg-[#17191d] p-6"
                      >
                        <div className="flex flex-wrap items-center gap-3">
                          <span className="font-mono-ui rounded-[6px] border border-[#24272d] bg-[#0b0c0e] px-2.5 py-1 text-[12px] font-medium tracking-[0.06em] text-[#f2f4f5]">
                            {release.version}
                          </span>
                          {release.version === latestVersion && (
                            <span className="font-mono-ui rounded-[6px] bg-[#c8f751] px-2 py-1 text-[11px] font-semibold tracking-[0.06em] text-[#0b0c0e]">
                              LATEST
                            </span>
                          )}
                          <time className="font-mono-ui text-[12px] text-[#6b727c]" dateTime={release.date}>
                            {release.date}
                          </time>
                        </div>

                        <h2 className="mt-4 text-[20px] font-semibold leading-[1.4] text-[#f2f4f5]">{release.title}</h2>
                        <p className="mt-2 text-[14px] leading-[1.65] text-[#a0a6af]">{release.summary}</p>

                        <ul className="mt-5 flex flex-col gap-3">
                          {release.items.map((item, index) => {
                            const meta = TYPE_META[item.type];
                            const Icon = meta.icon;
                            return (
                              <li key={`${release.version}-${index}`} className="flex gap-3">
                                <span
                                  className="mt-0.5 flex h-6 shrink-0 items-center gap-1.5 rounded-[6px] px-2 text-[11px] font-medium"
                                  style={{ color: meta.color, backgroundColor: meta.bg }}
                                >
                                  <Icon size={12} />
                                  {meta.label}
                                </span>
                                <span className="text-[14px] leading-[1.6] text-[#a0a6af]">{item.text}</span>
                              </li>
                            );
                          })}
                        </ul>

                        <div className="mt-5 flex flex-wrap gap-2">
                          {release.tags.map((tag) => (
                            <span
                              key={tag}
                              className="font-mono-ui rounded-[6px] border border-[#24272d] px-2 py-1 text-[11px] text-[#6b727c]"
                            >
                              #{tag}
                            </span>
                          ))}
                        </div>
                      </article>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <aside className="lg:sticky lg:top-24 lg:self-start">
              <p className="font-mono-ui text-[12px] font-medium uppercase tracking-[0.06em] text-[#6b727c]">versions</p>
              <nav className="mt-4 flex flex-col gap-1" aria-label="版本快速跳转">
                {releases.map((release) => (
                  <a
                    key={release.version}
                    href={`#${release.version}`}
                    className="focus-ring flex items-center justify-between rounded-[8px] px-2.5 py-2 text-[13px] text-[#a0a6af] transition-colors hover:bg-[#17191d] hover:text-[#f2f4f5]"
                  >
                    <span className="font-mono-ui">{release.version}</span>
                    <span className="font-mono-ui text-[11px] text-[#6b727c]">{release.date}</span>
                  </a>
                ))}
              </nav>
              <div className="mt-6 flex flex-col gap-1 border-t border-[#24272d] pt-6">
                <Link
                  to="/docs"
                  className="focus-ring rounded-[8px] px-2.5 py-2 text-[13px] text-[#a0a6af] transition-colors hover:text-[#f2f4f5]"
                >
                  文档中心
                </Link>
                <Link
                  to="/"
                  className="focus-ring inline-flex items-center gap-2 rounded-[8px] px-2.5 py-2 text-[13px] text-[#a0a6af] transition-colors hover:text-[#f2f4f5]"
                >
                  <ArrowLeft size={14} /> 返回首页
                </Link>
              </div>
            </aside>
          </div>
        </div>
      </main>
    </div>
  );
}
