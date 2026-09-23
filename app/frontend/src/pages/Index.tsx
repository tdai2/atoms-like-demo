import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Check, Play, Loader2, AlertTriangle } from 'lucide-react';
import SiteHeader from '@/components/SiteHeader';
import MiniApp from '@/components/MiniApp';
import {
  BUILD_STEPS,
  CAPABILITIES,
  PLANS,
  PROMPT_PRESETS,
  TEMPLATES,
  TEMPLATE_CATEGORIES,
  type MiniAppKind,
} from '@/data/site';
import { cn } from '@/lib/utils';
import { useAuthStatus } from '@/hooks/useAuthStatus';
import { useCreateProject, useProjectPipeline } from '@/hooks/useProjects';
import { apiErrorMessage, type StageState } from '@/lib/projects';
import { consumeStartFreeIntent, onStartFreeFocus, peekStartFreeIntent } from '@/lib/startFree';

/** 依据服务端方案（页面与实体）决定预览窗渲染哪种迷你应用。 */
function pickKind(prompt: string, pages: string[], entities: string[]): MiniAppKind {
  const text = `${prompt} ${pages.join(' ')} ${entities.join(' ')}`.toLowerCase();
  if (/商城|电商|商品|订单|结算|购物车|落地页|官网|品牌/.test(text)) return 'landing';
  if (/任务|待办|todo|协作|清单/.test(text)) return 'todo';
  return 'dashboard';
}

function Wireframe({ wire, accent }: { wire: string; accent: string }) {
  return (
    <div className="flex h-28 flex-col gap-1.5 rounded-[10px] border border-[#24272d] bg-[#141619] p-3">
      {wire === 'chart' && (
        <div className="flex h-full items-end gap-1.5">
          {[40, 68, 52, 84, 60, 92].map((h, i) => (
            <div key={i} className="flex-1 rounded-[2px]" style={{ height: `${h}%`, background: accent, opacity: 0.3 + i * 0.12 }} />
          ))}
        </div>
      )}
      {wire === 'hero' && (
        <>
          <div className="h-2 w-1/3 rounded-full" style={{ background: accent }} />
          <div className="h-3 w-4/5 rounded-full bg-[#2c3036]" />
          <div className="h-3 w-3/5 rounded-full bg-[#2c3036]" />
          <div className="mt-auto h-5 w-20 rounded-[6px]" style={{ background: accent, opacity: 0.85 }} />
        </>
      )}
      {wire === 'list' && (
        <>
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="h-4 w-4 shrink-0 rounded-[4px]" style={{ background: accent, opacity: 0.55 }} />
              <div className="h-2.5 flex-1 rounded-full bg-[#2c3036]" />
            </div>
          ))}
          <div className="mt-auto h-2 w-1/2 rounded-full bg-[#24272d]" />
        </>
      )}
      {wire === 'grid' && (
        <div className="grid h-full grid-cols-3 gap-1.5">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="rounded-[5px] bg-[#2c3036]" style={i % 4 === 0 ? { background: accent, opacity: 0.6 } : undefined} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Index() {
  const [input, setInput] = useState('');
  const [projectId, setProjectId] = useState<number | null>(null);
  const [category, setCategory] = useState<(typeof TEMPLATE_CATEGORIES)[number]>('全部');
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const { state: authState, login } = useAuthStatus();
  const create = useCreateProject();
  const pipeline = useProjectPipeline(projectId, true);

  // 滚动到需求输入区并聚焦，供「免费开始」入口与意图监听复用。
  useEffect(() => {
    const focusPrompt = () => {
      const section = document.getElementById('console');
      const smooth = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      section?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' });
      promptRef.current?.focus({ preventScroll: true });
    };
    return onStartFreeFocus(focusPrompt);
  }, []);

  // 入口点击时登录会离开本页，回到首页后在这里消费意图，直接落到输入区。
  useEffect(() => {
    if (authState !== 'authenticated' || !peekStartFreeIntent()) return;
    consumeStartFreeIntent();
    // 等布局稳定后再滚动，避免与浏览器恢复的滚动位置相互覆盖。
    const timer = window.setTimeout(() => {
      document.getElementById('console')?.scrollIntoView({ block: 'start' });
      promptRef.current?.focus({ preventScroll: true });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [authState]);

  const project = pipeline.data?.project;
  const stages = pipeline.data?.stages ?? [];
  const spec = pipeline.data?.spec;
  const testReport = pipeline.data?.test_report ?? [];
  const quota = pipeline.data?.quota;

  const phase: 'idle' | 'running' | 'done' | 'failed' = !project
    ? 'idle'
    : project.status === 'failed'
      ? 'failed'
      : project.status === 'succeeded'
        ? 'done'
        : 'running';
  const activeStage = stages.find((s) => s.stage_state === 'running');
  const busy = create.isPending || phase === 'running';

  // 有后端流水线时展示真实阶段状态，否则展示待执行的阶段清单。
  const timeline: { id: string; title: string; detail: string; state: StageState }[] = stages.length
    ? stages.map((s) => ({
        id: s.stage,
        title: s.stage_name,
        detail: s.stage_log.split('\n').filter(Boolean).slice(-1)[0] ?? '',
        state: s.stage_state,
      }))
    : BUILD_STEPS.map((s) => ({ id: s.id, title: s.title, detail: s.detail, state: 'pending' }));

  const run = (text: string) => {
    const value = text.trim();
    if (!value || busy) return;
    // 生成任务归属账号，未登录时先走统一登录入口。
    if (authState !== 'authenticated') {
      login();
      return;
    }
    create.mutate({ prompt: value }, { onSuccess: (data) => setProjectId(data.project.id) });
  };

  const errorText = create.isError
    ? apiErrorMessage(create.error, '生成任务创建失败，请稍后重试')
    : pipeline.isError && projectId !== null
      ? apiErrorMessage(pipeline.error, '任务状态读取失败')
      : '';

  const previewKind: MiniAppKind = pickKind(input || project?.prompt || '', spec?.pages ?? [], spec?.entities ?? []);
  const filtered = category === '全部' ? TEMPLATES : TEMPLATES.filter((t) => t.category === category);

  return (
    <div className="min-h-screen bg-[#0b0c0e]">
      <SiteHeader />

      {/* Hero */}
      <section id="console" className="relative overflow-hidden border-b border-[#24272d]">
        <div className="atom-grid absolute inset-0 opacity-70" aria-hidden />
        <div className="atom-glow absolute inset-0" aria-hidden />
        <div className="relative mx-auto max-w-[1200px] px-4 py-16 sm:px-6 lg:py-24">
          <div className="grid items-start gap-12 lg:grid-cols-[62fr_38fr] lg:gap-10">
            <div>
              <span className="font-mono-ui inline-flex items-center gap-2 rounded-[6px] border border-[#24272d] bg-[#141619] px-2.5 py-1 text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">
                <span className="h-1.5 w-1.5 rounded-full bg-[#c8f751]" />
                multi-agent builder
              </span>
              <h1 className="mt-5 text-[36px] font-bold leading-[1.08] tracking-[-0.02em] text-[#f2f4f5] sm:text-[52px]">
                一句话，
                <br />
                长成一个能跑的应用
              </h1>
              <p className="mt-4 max-w-[46ch] text-[16px] leading-[1.65] text-[#a0a6af]">
                描述你想要的产品，Atoms 的智能体团队会拆解需求、编写代码、构建校验、跑通测试并发布预览。全程可见，随时对话式修改。
              </p>

              <div className="mt-7 rounded-[14px] border border-[#24272d] bg-[#17191d] p-3 sm:p-4">
                <label htmlFor="prompt" className="font-mono-ui block text-[11px] uppercase tracking-[0.16em] text-[#6b727c]">
                  describe your app
                </label>
                <textarea
                  id="prompt"
                  ref={promptRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) run(input);
                  }}
                  rows={3}
                  placeholder="例如：做一个 SaaS 增长数据看板，包含核心指标卡与趋势图"
                  className="focus-ring mt-2 w-full resize-none rounded-[12px] border border-[#24272d] bg-[#0b0c0e] px-3.5 py-3 text-[15px] leading-[1.6] text-[#f2f4f5] placeholder:text-[#6b727c]"
                />
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {PROMPT_PRESETS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setInput(p.prompt)}
                      className="focus-ring rounded-full border border-[#24272d] !bg-transparent px-3 py-1.5 text-[12px] text-[#a0a6af] transition-colors hover:!bg-transparent hover:border-[#c8f751] hover:text-[#f2f4f5]"
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                <div className="mt-4 flex items-center justify-between gap-3">
                  <span className="font-mono-ui hidden text-[11px] text-[#6b727c] sm:block">⌘ + Enter 运行</span>
                  <button
                    type="button"
                    disabled={!input.trim() || busy}
                    onClick={() => run(input)}
                    className={cn(
                      'focus-ring inline-flex h-11 items-center gap-2 rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]',
                      (!input.trim() || busy) && 'pointer-events-none opacity-45',
                    )}
                  >
                    {busy ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                    {busy ? '生成中' : '生成应用'}
                  </button>
                </div>
              </div>

              <ol className="mt-6 grid gap-2 sm:grid-cols-2">
                {timeline.map((s) => (
                  <li key={s.id} className="flex items-start gap-2.5 rounded-[10px] border border-[#24272d] bg-[#141619] px-3 py-2.5">
                    <span
                      className={cn(
                        'mt-1.5 h-2 w-2 shrink-0 rounded-full',
                        s.state === 'done' && 'bg-[#4ade80]',
                        s.state === 'running' && 'animate-pulse-dot bg-[#c8f751]',
                        s.state === 'failed' && 'bg-[#f87171]',
                        s.state === 'pending' && 'bg-[#3a3f47]',
                      )}
                    />
                    <span className="min-w-0">
                      <span className={cn('block text-[13px] font-medium', s.state === 'pending' ? 'text-[#6b727c]' : 'text-[#f2f4f5]')}>
                        {s.title}
                      </span>
                      <span className="font-mono-ui block truncate text-[11px] text-[#6b727c]">{s.detail}</span>
                    </span>
                  </li>
                ))}
              </ol>

              {errorText && (
                <div className="mt-4 flex items-start gap-3 rounded-[10px] border border-[#f87171]/40 bg-[rgba(248,113,113,0.06)] px-3.5 py-3">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0 text-[#f87171]" />
                  <p className="text-[13px] leading-[1.6] text-[#f2f4f5]">{errorText}</p>
                </div>
              )}

              {project && (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3">
                  <span className="font-mono-ui text-[12px] text-[#a0a6af]">
                    项目 #{project.id} · v{project.latest_version}
                    {quota ? ` · 本周期额度 ${quota.used}/${quota.limit}` : ''}
                  </span>
                  <Link
                    to={`/projects/${project.id}`}
                    className="focus-ring inline-flex items-center gap-1.5 rounded-[6px] text-[13px] text-[#c8f751] transition-colors hover:underline"
                  >
                    查看项目详情
                    <ArrowRight size={13} />
                  </Link>
                </div>
              )}
            </div>

            {/* Preview window */}
            <div className="lg:sticky lg:top-24">
              <div className="overflow-hidden rounded-[14px] border border-[#24272d] bg-[#0f1113] shadow-[0_12px_32px_rgba(0,0,0,0.5)]">
                <div className="flex items-center gap-2 border-b border-[#24272d] bg-[#141619] px-3 py-2.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-[#3a3f47]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#3a3f47]" />
                  <span className="h-2.5 w-2.5 rounded-full bg-[#3a3f47]" />
                  <span className="font-mono-ui ml-2 truncate text-[11px] text-[#6b727c]">
                    {spec?.app_name ?? 'app'}.atoms.app
                  </span>
                  <span
                    className={cn(
                      'font-mono-ui ml-auto rounded-[6px] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]',
                      phase === 'done' && 'bg-[rgba(74,222,128,0.14)] text-[#4ade80]',
                      phase === 'failed' && 'bg-[rgba(248,113,113,0.14)] text-[#f87171]',
                      (phase === 'running' || phase === 'idle') && 'bg-[rgba(200,247,81,0.12)] text-[#c8f751]',
                    )}
                  >
                    {phase === 'running' ? 'building' : phase === 'done' ? 'live' : phase === 'failed' ? 'broken' : 'ready'}
                  </span>
                </div>
                <div className="relative min-h-[300px]">
                  {phase === 'running' ? (
                    <div className="flex min-h-[300px] flex-col items-center justify-center gap-3 px-6 text-center">
                      <Loader2 size={22} className="animate-spin text-[#c8f751]" />
                      <p className="font-mono-ui text-[12px] text-[#a0a6af]">
                        {activeStage?.stage_name ?? '等待执行'}
                        <span className="animate-caret">_</span>
                      </p>
                    </div>
                  ) : phase === 'failed' ? (
                    <div className="flex min-h-[300px] flex-col items-center justify-center gap-3 px-6 text-center">
                      <AlertTriangle size={22} className="text-[#f87171]" />
                      <p className="font-mono-ui text-[12px] text-[#a0a6af]">生成中断，可在项目详情页重试</p>
                    </div>
                  ) : (
                    <MiniApp kind={previewKind} />
                  )}
                </div>
                {phase === 'done' && testReport.length > 0 && (
                  <div className="border-t border-[#24272d] bg-[#141619] px-3 py-2.5">
                    <p className="font-mono-ui text-[10px] uppercase tracking-[0.14em] text-[#6b727c]">test report</p>
                    <ul className="mt-2 grid grid-cols-3 gap-2">
                      {testReport.map((r) => (
                        <li key={r.id} className="rounded-[8px] border border-[#24272d] bg-[#0f1113] px-2.5 py-2">
                          <p className="text-[11px] text-[#6b727c]">{r.label}</p>
                          <p className={cn('font-mono-ui mt-0.5 text-[13px] font-semibold', r.passed ? 'text-[#4ade80]' : 'text-[#f87171]')}>
                            {r.value}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2 border-t border-[#24272d] bg-[#141619] px-3 py-2.5">
                  {(spec?.stack ?? PROMPT_PRESETS[0].stack).map((s) => (
                    <span key={s} className="font-mono-ui rounded-[6px] border border-[#24272d] px-2 py-0.5 text-[10px] text-[#a0a6af]">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
              <p className="mt-3 text-[12px] leading-[1.6] text-[#6b727c]">
                预览窗中的界面由真实组件渲染，生成后可继续在对话中追加需求。
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Capabilities */}
      <section id="capabilities" className="border-b border-[#24272d]">
        <div className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6 lg:py-[112px]">
          <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">capabilities</p>
          <h2 className="mt-3 max-w-[20ch] text-[28px] font-bold leading-[1.15] text-[#f2f4f5] sm:text-[32px]">
            从需求到上线，交给一支智能体团队
          </h2>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {CAPABILITIES.map((c) => (
              <div key={c.id} className="rounded-[14px] border border-[#24272d] bg-[#17191d] p-5 transition-colors hover:border-[#3a3f47]">
                <span className="font-mono-ui text-[11px] uppercase tracking-[0.14em] text-[#6b727c]">{c.tag}</span>
                <h3 className="mt-3 text-[20px] font-semibold leading-[1.3] text-[#f2f4f5]">{c.title}</h3>
                <p className="mt-2 text-[14px] leading-[1.65] text-[#a0a6af]">{c.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Templates */}
      <section id="templates" className="border-b border-[#24272d] bg-[#0d0e11]">
        <div className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6 lg:py-[112px]">
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div>
              <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">templates</p>
              <h2 className="mt-3 text-[28px] font-bold leading-[1.15] text-[#f2f4f5] sm:text-[32px]">从模板起步，几秒完成定制</h2>
            </div>
            <div className="flex flex-wrap gap-2">
              {TEMPLATE_CATEGORIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategory(c)}
                  className={cn(
                    'focus-ring rounded-full border px-3.5 py-1.5 text-[13px] transition-colors',
                    category === c
                      ? 'border-[#c8f751] bg-[rgba(200,247,81,0.12)] text-[#f2f4f5]'
                      : 'border-[#24272d] !bg-transparent text-[#a0a6af] hover:!bg-transparent hover:text-[#f2f4f5]',
                  )}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="mt-10 rounded-[14px] border border-[#24272d] bg-[#17191d] p-10 text-center">
              <p className="font-mono-ui text-[13px] text-[#a0a6af]">该分类下暂无模板</p>
              <button
                type="button"
                onClick={() => setCategory('全部')}
                className="focus-ring mt-4 rounded-[10px] border border-[#24272d] !bg-transparent px-4 py-2 text-[14px] text-[#f2f4f5] hover:!bg-transparent"
              >
                重置筛选
              </button>
            </div>
          ) : (
            <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((t) => (
                <Link
                  key={t.id}
                  to={`/templates/${t.id}`}
                  className="focus-ring group rounded-[14px] border border-[#24272d] bg-[#17191d] p-4 transition-colors hover:border-[#c8f751]"
                >
                  <div className="transition-transform duration-200 group-hover:scale-[1.02]">
                    <Wireframe wire={t.wire} accent={t.accent} />
                  </div>
                  <div className="mt-4 flex items-center justify-between gap-3">
                    <h3 className="text-[16px] font-semibold text-[#f2f4f5]">{t.name}</h3>
                    <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-2 py-0.5 text-[10px] text-[#a0a6af]">{t.category}</span>
                  </div>
                  <p className="mt-1.5 text-[13px] leading-[1.6] text-[#a0a6af]">{t.summary}</p>
                </Link>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-b border-[#24272d]">
        <div className="mx-auto max-w-[1200px] px-4 py-16 sm:px-6 lg:py-[112px]">
          <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">pricing</p>
          <h2 className="mt-3 text-[28px] font-bold leading-[1.15] text-[#f2f4f5] sm:text-[32px]">按生成量付费，随时升级</h2>
          <div className="mt-10 grid gap-5 lg:grid-cols-3">
            {PLANS.map((p) => (
              <div
                key={p.id}
                className={cn(
                  'flex flex-col rounded-[14px] border bg-[#17191d] p-6',
                  p.highlight ? 'border-[#c8f751]' : 'border-[#24272d]',
                )}
              >
                <div className="flex items-center gap-2">
                  <h3 className="text-[20px] font-semibold text-[#f2f4f5]">{p.name}</h3>
                  {p.highlight && (
                    <span className="font-mono-ui rounded-[6px] bg-[rgba(200,247,81,0.14)] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em] text-[#c8f751]">
                      popular
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-[13px] text-[#a0a6af]">{p.desc}</p>
                <p className="font-mono-ui mt-5 text-[32px] font-semibold text-[#f2f4f5]">
                  {p.price}
                  <span className="text-[14px] font-normal text-[#6b727c]">{p.unit}</span>
                </p>
                <ul className="mt-5 flex-1 space-y-2.5">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-[14px] text-[#a0a6af]">
                      <Check size={15} className="mt-1 shrink-0 text-[#c8f751]" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Link
                  to="/billing"
                  className={cn(
                    'focus-ring mt-6 inline-flex h-11 items-center justify-center rounded-[10px] text-[15px] font-semibold transition-colors',
                    p.highlight
                      ? 'bg-[#c8f751] text-[#0b0c0e] hover:bg-[#b4e23c]'
                      : 'border border-[#24272d] !bg-transparent text-[#f2f4f5] hover:!bg-transparent hover:border-[#3a3f47]',
                  )}
                >
                  {p.id === 'team' ? '联系我们' : '选择方案'}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA + Footer */}
      <footer className="relative overflow-hidden">
        <div className="atom-grid absolute inset-0 opacity-50" aria-hidden />
        <div className="relative mx-auto max-w-[1200px] px-4 py-16 sm:px-6">
          <div className="flex flex-col items-start justify-between gap-6 rounded-[14px] border border-[#24272d] bg-[#17191d] p-8 lg:flex-row lg:items-center">
            <div>
              <h2 className="text-[26px] font-bold leading-[1.2] text-[#f2f4f5]">现在就描述你的第一个应用</h2>
              <p className="mt-2 text-[15px] text-[#a0a6af]">无需信用卡，几十秒得到可分享的预览链接。</p>
            </div>
            <a
              href="#console"
              className="focus-ring inline-flex h-12 items-center gap-2 rounded-[10px] bg-[#c8f751] px-6 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
            >
              开始生成 <ArrowRight size={16} />
            </a>
          </div>

          <div className="mt-10 flex flex-col justify-between gap-4 border-t border-[#24272d] pt-6 text-[13px] text-[#6b727c] sm:flex-row">
            <p className="font-mono-ui">© 2026 atoms — demo</p>
            <div className="flex gap-6">
              <Link to="/docs" className="transition-colors hover:text-[#f2f4f5]">
                文档
              </Link>
              <Link to="/changelog" className="transition-colors hover:text-[#f2f4f5]">
                更新日志
              </Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
