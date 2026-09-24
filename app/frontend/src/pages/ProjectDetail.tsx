import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, ExternalLink, Loader2, RefreshCw } from 'lucide-react';
import SiteHeader from '@/components/SiteHeader';
import TestSuitePanel from '@/components/TestSuitePanel';
import { useAuthStatus } from '@/hooks/useAuthStatus';
import { useProjectPipeline, useRetryProject } from '@/hooks/useProjects';
import { apiErrorMessage, formatDateTime, type ProjectStatus, type StageState } from '@/lib/projects';
import { cn } from '@/lib/utils';

const STATUS_META: Record<ProjectStatus, { label: string; tone: string }> = {
  queued: { label: '排队中', tone: 'bg-[rgba(200,247,81,0.12)] text-[#c8f751]' },
  running: { label: '生成中', tone: 'bg-[rgba(200,247,81,0.12)] text-[#c8f751]' },
  succeeded: { label: '已完成', tone: 'bg-[rgba(74,222,128,0.14)] text-[#4ade80]' },
  failed: { label: '已失败', tone: 'bg-[rgba(248,113,113,0.14)] text-[#f87171]' },
};

/** 预览地址只展示主机名，避免把带签名的长链接塞进地址栏。 */
function previewHost(url: string): string {
  if (!url) return '';
  try {
    return new URL(url).host;
  } catch {
    return url.replace(/^https?:\/\//, '').split('/')[0];
  }
}

function StageDot({ state }: { state: StageState }) {
  return (
    <span
      className={cn(
        'mt-1.5 h-2 w-2 shrink-0 rounded-full',
        state === 'done' && 'bg-[#4ade80]',
        state === 'running' && 'animate-pulse-dot bg-[#c8f751]',
        state === 'failed' && 'bg-[#f87171]',
        state === 'pending' && 'bg-[#3a3f47]',
      )}
    />
  );
}

export default function ProjectDetail() {
  const { id } = useParams();
  const projectId = Number(id);
  const valid = Number.isInteger(projectId) && projectId > 0;
  const { state, login } = useAuthStatus();
  const pipeline = useProjectPipeline(valid ? projectId : null, state === 'authenticated');
  const retry = useRetryProject();

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [projectId]);

  const project = pipeline.data?.project;
  const stages = pipeline.data?.stages ?? [];
  const spec = pipeline.data?.spec;
  const previewUrl = project?.preview_url ?? '';
  const errorMessage = pipeline.isError ? apiErrorMessage(pipeline.error, '项目加载失败') : '';

  return (
    <div className="min-h-screen bg-[#0b0c0e]">
      <SiteHeader />
      <main className="mx-auto max-w-[1200px] px-4 py-12 sm:px-6">
        <Link
          to="/projects"
          className="focus-ring inline-flex items-center gap-2 rounded-[6px] text-[13px] text-[#a0a6af] transition-colors hover:text-[#f2f4f5]"
        >
          <ArrowLeft size={14} />
          返回项目列表
        </Link>

        {!valid && (
          <div className="mt-8 rounded-[14px] border border-[#24272d] bg-[#17191d] px-5 py-6">
            <p className="text-[15px] text-[#f2f4f5]">无效的项目编号</p>
          </div>
        )}

        {valid && state === 'loading' && (
          <div className="mt-8 flex items-center gap-3 rounded-[14px] border border-[#24272d] bg-[#17191d] px-5 py-6">
            <Loader2 size={18} className="animate-spin text-[#c8f751]" />
            <span className="font-mono-ui text-[13px] text-[#a0a6af]">正在读取账号状态…</span>
          </div>
        )}

        {valid && state === 'anonymous' && (
          <div className="mt-8 rounded-[14px] border border-[#24272d] bg-[#17191d] p-8">
            <h1 className="text-[20px] font-semibold text-[#f2f4f5]">登录后查看项目</h1>
            <p className="mt-2 max-w-[56ch] text-[14px] leading-[1.65] text-[#a0a6af]">
              项目归属于账号，登录后才能查看它的流水线记录与版本信息。
            </p>
            <button
              type="button"
              onClick={login}
              className="focus-ring mt-6 inline-flex h-11 items-center rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
            >
              登录 Atoms
            </button>
          </div>
        )}

        {valid && state === 'authenticated' && pipeline.isLoading && (
          <div className="mt-8 flex items-center gap-3 rounded-[14px] border border-[#24272d] bg-[#17191d] px-5 py-6">
            <Loader2 size={18} className="animate-spin text-[#c8f751]" />
            <span className="font-mono-ui text-[13px] text-[#a0a6af]">正在加载项目…</span>
          </div>
        )}

        {valid && state === 'authenticated' && errorMessage && (
          <div className="mt-8 flex flex-col gap-3 rounded-[14px] border border-[#f87171]/40 bg-[rgba(248,113,113,0.06)] px-5 py-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle size={18} className="mt-0.5 shrink-0 text-[#f87171]" />
              <p className="text-[14px] leading-[1.6] text-[#f2f4f5]">{errorMessage}</p>
            </div>
            <button
              type="button"
              onClick={() => pipeline.refetch()}
              className="focus-ring inline-flex h-10 shrink-0 items-center gap-2 rounded-[10px] border border-[#24272d] !bg-transparent px-4 text-[13px] text-[#f2f4f5] hover:!bg-transparent hover:border-[#3a3f47]"
            >
              <RefreshCw size={14} />
              重试
            </button>
          </div>
        )}

        {valid && state === 'authenticated' && project && (
          <>
            <header className="mt-6 flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-[28px] font-bold leading-[1.15] tracking-[-0.01em] text-[#f2f4f5]">
                    {project.name}
                  </h1>
                  <span
                    className={cn(
                      'font-mono-ui rounded-[6px] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]',
                      (STATUS_META[project.status] ?? STATUS_META.queued).tone,
                    )}
                  >
                    {(STATUS_META[project.status] ?? STATUS_META.queued).label}
                  </span>
                </div>
                <p className="mt-2 max-w-[80ch] text-[14px] leading-[1.65] text-[#a0a6af]">{project.prompt}</p>
                <p className="font-mono-ui mt-2 text-[11px] text-[#6b727c]">
                  创建于 {formatDateTime(project.created_at)} · 版本 v{project.latest_version} · 第 {pipeline.data?.run_no} 次运行
                </p>
              </div>

              <div className="flex items-center gap-2">
                {previewUrl && (
                  <a
                    href={previewUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] border border-[#24272d] px-4 text-[13px] text-[#f2f4f5] transition-colors hover:border-[#3a3f47]"
                  >
                    <ExternalLink size={14} />
                    打开预览
                  </a>
                )}
                {project.status === 'failed' && (
                  <button
                    type="button"
                    onClick={() => retry.mutate(project.id)}
                    disabled={retry.isPending}
                    className={cn(
                      'focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] bg-[#c8f751] px-4 text-[13px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]',
                      retry.isPending && 'pointer-events-none opacity-45',
                    )}
                  >
                    {retry.isPending ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                    重新生成
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => pipeline.refetch()}
                  disabled={pipeline.isFetching}
                  className={cn(
                    'focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] border border-[#24272d] !bg-transparent px-3.5 text-[13px] text-[#a0a6af] transition-colors hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]',
                    pipeline.isFetching && 'pointer-events-none opacity-45',
                  )}
                >
                  <RefreshCw size={14} />
                  刷新
                </button>
              </div>
            </header>

            <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_420px]">
              <section className="rounded-[14px] border border-[#24272d] bg-[#17191d] p-5">
                <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">pipeline</p>
                <h2 className="mt-2 text-[18px] font-semibold text-[#f2f4f5]">六阶段流水线</h2>
                <ol className="mt-5 space-y-3">
                  {stages.map((stage) => (
                    <li key={stage.stage} className="rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3">
                      <div className="flex items-start gap-2.5">
                        <StageDot state={stage.stage_state} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={cn(
                                'text-[14px] font-medium',
                                stage.stage_state === 'pending' ? 'text-[#6b727c]' : 'text-[#f2f4f5]',
                              )}
                            >
                              {stage.stage_name}
                            </span>
                            <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-1.5 py-0.5 text-[10px] text-[#6b727c]">
                              {stage.stage}
                            </span>
                            {stage.stage_state === 'failed' && (
                              <span className="font-mono-ui text-[11px] text-[#f87171]">failed</span>
                            )}
                          </div>
                          {stage.stage_log && (
                            <pre className="font-mono-ui mt-2 overflow-x-auto whitespace-pre-wrap break-words text-[11px] leading-[1.7] text-[#a0a6af]">
                              {stage.stage_log}
                            </pre>
                          )}
                          {stage.error_message && (
                            <p className="mt-2 rounded-[8px] border border-[#f87171]/40 bg-[rgba(248,113,113,0.06)] px-2.5 py-2 text-[12px] leading-[1.6] text-[#f87171]">
                              {stage.error_message}
                            </p>
                          )}
                          {stage.output_summary && (
                            <p className="font-mono-ui mt-2 text-[11px] text-[#6b727c]">{stage.output_summary}</p>
                          )}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="space-y-6">
                <div className="overflow-hidden rounded-[14px] border border-[#24272d] bg-[#0f1113]">
                  <div className="flex items-center gap-2 border-b border-[#24272d] bg-[#141619] px-3 py-2.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-[#3a3f47]" />
                    <span className="h-2.5 w-2.5 rounded-full bg-[#3a3f47]" />
                    <span className="h-2.5 w-2.5 rounded-full bg-[#3a3f47]" />
                    <span className="font-mono-ui ml-2 truncate text-[11px] text-[#6b727c]">
                      {previewHost(previewUrl) || `${spec?.app_name ?? 'app'}.atoms.app`}
                    </span>
                    <span
                      className={cn(
                        'font-mono-ui ml-auto rounded-[6px] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]',
                        project.status === 'succeeded'
                          ? 'bg-[rgba(74,222,128,0.14)] text-[#4ade80]'
                          : project.status === 'failed'
                            ? 'bg-[rgba(248,113,113,0.14)] text-[#f87171]'
                            : 'bg-[rgba(200,247,81,0.12)] text-[#c8f751]',
                      )}
                    >
                      {project.status === 'succeeded' ? 'ready' : project.status === 'failed' ? 'broken' : 'building'}
                    </span>
                  </div>
                  {previewUrl ? (
                    <iframe
                      title={`${project.name} 预览`}
                      src={previewUrl}
                      className="h-[420px] w-full border-0 bg-[#0b0c0e]"
                      sandbox="allow-scripts allow-forms allow-modals allow-popups"
                    />
                  ) : (
                    <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 px-6 text-center">
                      {project.status === 'failed' ? (
                        <>
                          <AlertTriangle size={20} className="text-[#f87171]" />
                          <p className="font-mono-ui text-[12px] text-[#a0a6af]">生成未完成，重试后继续</p>
                        </>
                      ) : (
                        <>
                          <Loader2 size={20} className="animate-spin text-[#c8f751]" />
                          <p className="font-mono-ui text-[12px] text-[#a0a6af]">
                            {stages.find((s) => s.stage_state === 'running')?.stage_name ?? '等待执行'}
                            <span className="animate-caret">_</span>
                          </p>
                        </>
                      )}
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-2 border-t border-[#24272d] bg-[#141619] px-3 py-2.5">
                    {(spec?.stack ?? []).map((s) => (
                      <span
                        key={s}
                        className="font-mono-ui rounded-[6px] border border-[#24272d] px-2 py-0.5 text-[10px] text-[#a0a6af]"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>

                {spec && (
                  <div className="rounded-[14px] border border-[#24272d] bg-[#17191d] p-5">
                    <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#6b727c]">方案</p>
                    <dl className="mt-3 space-y-3">
                      <div>
                        <dt className="text-[12px] text-[#6b727c]">页面</dt>
                        <dd className="mt-1.5 flex flex-wrap gap-1.5">
                          {spec.pages.map((p) => (
                            <span
                              key={p}
                              className="rounded-[6px] border border-[#24272d] bg-[#141619] px-2 py-0.5 text-[12px] text-[#a0a6af]"
                            >
                              {p}
                            </span>
                          ))}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[12px] text-[#6b727c]">数据实体</dt>
                        <dd className="mt-1.5 flex flex-wrap gap-1.5">
                          {spec.entities.map((e) => (
                            <span
                              key={e}
                              className="rounded-[6px] border border-[#24272d] bg-[#141619] px-2 py-0.5 text-[12px] text-[#a0a6af]"
                            >
                              {e}
                            </span>
                          ))}
                        </dd>
                      </div>
                      <div className="flex justify-between border-t border-[#24272d] pt-3 text-[12px]">
                        <span className="text-[#6b727c]">产出文件</span>
                        <span className="font-mono-ui text-[#f2f4f5]">{spec.files}</span>
                      </div>
                    </dl>
                  </div>
                )}

                {project.status === 'succeeded' && (pipeline.data?.test_report.length ?? 0) > 0 && (
                  <div className="rounded-[14px] border border-[#24272d] bg-[#17191d] p-5">
                    <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#6b727c]">test report</p>
                    <ul className="mt-3 grid grid-cols-3 gap-2">
                      {pipeline.data?.test_report.map((r) => (
                        <li key={r.id} className="rounded-[8px] border border-[#24272d] bg-[#141619] px-2.5 py-2">
                          <p className="text-[11px] text-[#6b727c]">{r.label}</p>
                          <p
                            className={cn(
                              'font-mono-ui mt-0.5 text-[13px] font-semibold',
                              r.passed ? 'text-[#4ade80]' : 'text-[#f87171]',
                            )}
                          >
                            {r.value}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            </div>

            {retry.isError && (
              <p className="mt-4 text-[13px] text-[#f87171]">{apiErrorMessage(retry.error, '重试失败，请稍后再试')}</p>
            )}

            <TestSuitePanel projectId={project.id} enabled={state === 'authenticated'} />
          </>
        )}
      </main>
    </div>
  );
}
