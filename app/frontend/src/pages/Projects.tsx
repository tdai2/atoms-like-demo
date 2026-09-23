import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Loader2, Plus, RefreshCw, Trash2 } from 'lucide-react';
import SiteHeader from '@/components/SiteHeader';
import { useAuthStatus } from '@/hooks/useAuthStatus';
import { useDeleteProject, useProjectList, useRetryProject } from '@/hooks/useProjects';
import { apiErrorMessage, formatDateTime, type ProjectStatus } from '@/lib/projects';
import { cn } from '@/lib/utils';

const STATUS_META: Record<ProjectStatus, { label: string; tone: string }> = {
  queued: { label: '排队中', tone: 'bg-[rgba(200,247,81,0.12)] text-[#c8f751]' },
  running: { label: '生成中', tone: 'bg-[rgba(200,247,81,0.12)] text-[#c8f751]' },
  succeeded: { label: '已完成', tone: 'bg-[rgba(74,222,128,0.14)] text-[#4ade80]' },
  failed: { label: '已失败', tone: 'bg-[rgba(248,113,113,0.14)] text-[#f87171]' },
};

function StatusBadge({ status }: { status: ProjectStatus }) {
  const meta = STATUS_META[status] ?? STATUS_META.queued;
  return (
    <span className={cn('font-mono-ui rounded-[6px] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]', meta.tone)}>
      {meta.label}
    </span>
  );
}

export default function Projects() {
  const { state, user, login } = useAuthStatus();
  const list = useProjectList(state === 'authenticated');
  const retry = useRetryProject();
  const remove = useDeleteProject();
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const anyRunning = useMemo(
    () => (list.data?.items ?? []).some((p) => p.status === 'running' || p.status === 'queued'),
    [list.data],
  );

  const quota = list.data?.quotas;
  const listError = list.isError ? apiErrorMessage(list.error, '项目列表加载失败') : '';

  return (
    <div className="min-h-screen bg-[#0b0c0e]">
      <SiteHeader />
      <main className="mx-auto max-w-[1200px] px-4 py-14 sm:px-6">
        <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">projects</p>
        <h1 className="mt-3 text-[30px] font-bold leading-[1.15] tracking-[-0.01em] text-[#f2f4f5] sm:text-[36px]">
          我的项目
        </h1>
        <p className="mt-3 max-w-[62ch] text-[15px] leading-[1.65] text-[#a0a6af]">
          这里汇总当前账号生成过的项目。点击任意项目可查看它的六阶段流水线快照，失败的项目可以直接重试。
        </p>

        {state === 'loading' && (
          <div className="mt-10 flex items-center gap-3 rounded-[14px] border border-[#24272d] bg-[#17191d] px-5 py-6">
            <Loader2 size={18} className="animate-spin text-[#c8f751]" />
            <span className="font-mono-ui text-[13px] text-[#a0a6af]">正在读取账号状态…</span>
          </div>
        )}

        {state === 'anonymous' && (
          <div className="mt-10 rounded-[14px] border border-[#24272d] bg-[#17191d] p-8">
            <h2 className="text-[20px] font-semibold text-[#f2f4f5]">登录后查看你的项目</h2>
            <p className="mt-2 max-w-[56ch] text-[14px] leading-[1.65] text-[#a0a6af]">
              项目与生成记录归属于账号，登录后可以查看历史项目、继续修改并管理版本。
            </p>
            <button
              type="button"
              onClick={login}
              className="focus-ring mt-6 inline-flex h-11 items-center gap-2 rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
            >
              登录 Atoms
            </button>
          </div>
        )}

        {state === 'authenticated' && (
          <>
            <div className="mt-8 flex flex-wrap items-center justify-between gap-4 rounded-[14px] border border-[#24272d] bg-[#17191d] px-4 py-3.5">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                <span className="text-[13px] text-[#a0a6af]">
                  账号：<span className="font-mono-ui text-[#f2f4f5]">{user?.email ?? '—'}</span>
                </span>
                <span className="text-[13px] text-[#a0a6af]">
                  本周期额度：
                  <span className="font-mono-ui ml-1 text-[#f2f4f5]">
                    {quota ? `${quota.used} / ${quota.limit}` : '—'}
                  </span>
                </span>
                <span className="text-[13px] text-[#a0a6af]">
                  项目总数：<span className="font-mono-ui ml-1 text-[#f2f4f5]">{list.data?.total ?? 0}</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => list.refetch()}
                  disabled={list.isFetching}
                  className={cn(
                    'focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] border border-[#24272d] !bg-transparent px-3.5 text-[13px] text-[#a0a6af] transition-colors hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]',
                    list.isFetching && 'pointer-events-none opacity-45',
                  )}
                >
                  {list.isFetching ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                  刷新
                </button>
                <Link
                  to="/"
                  className="focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] bg-[#c8f751] px-4 text-[13px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
                >
                  <Plus size={14} />
                  新建项目
                </Link>
              </div>
            </div>

            {anyRunning && (
              <p className="font-mono-ui mt-3 text-[12px] text-[#6b727c]">列表每 3 秒自动刷新，直到生成中的项目结束。</p>
            )}

            {list.isLoading && (
              <div className="mt-6 space-y-3">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-[86px] animate-pulse rounded-[14px] border border-[#24272d] bg-[#17191d]" />
                ))}
              </div>
            )}

            {listError && (
              <div className="mt-6 flex flex-col gap-3 rounded-[14px] border border-[#f87171]/40 bg-[rgba(248,113,113,0.06)] px-5 py-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <AlertTriangle size={18} className="mt-0.5 shrink-0 text-[#f87171]" />
                  <p className="text-[14px] leading-[1.6] text-[#f2f4f5]">{listError}</p>
                </div>
                <button
                  type="button"
                  onClick={() => list.refetch()}
                  className="focus-ring inline-flex h-10 shrink-0 items-center gap-2 rounded-[10px] border border-[#24272d] !bg-transparent px-4 text-[13px] text-[#f2f4f5] hover:!bg-transparent hover:border-[#3a3f47]"
                >
                  <RefreshCw size={14} />
                  重试
                </button>
              </div>
            )}

            {!list.isLoading && !listError && (list.data?.items.length ?? 0) === 0 && (
              <div className="mt-6 rounded-[14px] border border-[#24272d] bg-[#17191d] p-10 text-center">
                <p className="text-[16px] font-semibold text-[#f2f4f5]">还没有项目</p>
                <p className="mx-auto mt-2 max-w-[46ch] text-[14px] leading-[1.65] text-[#a0a6af]">
                  回到首页描述一句需求，生成的第一个项目就会出现在这里。
                </p>
                <Link
                  to="/"
                  className="focus-ring mt-6 inline-flex h-11 items-center gap-2 rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
                >
                  <Plus size={16} />
                  去生成第一个应用
                </Link>
              </div>
            )}

            {!list.isLoading && !listError && (list.data?.items.length ?? 0) > 0 && (
              <ul className="mt-6 space-y-3">
                {list.data?.items.map((project) => (
                  <li
                    key={project.id}
                    className="rounded-[14px] border border-[#24272d] bg-[#17191d] px-4 py-4 transition-colors hover:border-[#3a3f47]"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Link
                            to={`/projects/${project.id}`}
                            className="focus-ring truncate rounded-[6px] text-[16px] font-semibold text-[#f2f4f5] hover:text-[#c8f751]"
                          >
                            {project.name}
                          </Link>
                          <StatusBadge status={project.status} />
                          <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-2 py-0.5 text-[10px] text-[#a0a6af]">
                            v{project.latest_version}
                          </span>
                        </div>
                        <p className="mt-2 line-clamp-2 text-[13px] leading-[1.6] text-[#a0a6af]">{project.prompt}</p>
                        <p className="font-mono-ui mt-2 text-[11px] text-[#6b727c]">
                          创建于 {formatDateTime(project.created_at)} · 当前阶段 {project.current_stage || '—'}
                        </p>
                      </div>

                      <div className="flex shrink-0 items-center gap-2">
                        {project.status === 'failed' && (
                          <button
                            type="button"
                            onClick={() => retry.mutate(project.id)}
                            disabled={retry.isPending}
                            className={cn(
                              'focus-ring inline-flex h-9 items-center gap-2 rounded-[10px] border border-[#c8f751] !bg-transparent px-3 text-[13px] text-[#c8f751] transition-colors hover:!bg-[rgba(200,247,81,0.08)]',
                              retry.isPending && 'pointer-events-none opacity-45',
                            )}
                          >
                            {retry.isPending ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                            重试
                          </button>
                        )}
                        <Link
                          to={`/projects/${project.id}`}
                          className="focus-ring inline-flex h-9 items-center rounded-[10px] border border-[#24272d] !bg-transparent px-3 text-[13px] text-[#f2f4f5] transition-colors hover:!bg-transparent hover:border-[#3a3f47]"
                        >
                          查看
                        </Link>
                        {confirmId === project.id ? (
                          <span className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => {
                                remove.mutate(project.id);
                                setConfirmId(null);
                              }}
                              className="focus-ring inline-flex h-9 items-center rounded-[10px] bg-[#f87171] px-3 text-[13px] font-semibold text-[#0b0c0e] hover:bg-[#ef5f5f]"
                            >
                              确认删除
                            </button>
                            <button
                              type="button"
                              onClick={() => setConfirmId(null)}
                              className="focus-ring inline-flex h-9 items-center rounded-[10px] border border-[#24272d] !bg-transparent px-3 text-[13px] text-[#a0a6af] hover:!bg-transparent"
                            >
                              取消
                            </button>
                          </span>
                        ) : (
                          <button
                            type="button"
                            aria-label="删除项目"
                            onClick={() => setConfirmId(project.id)}
                            className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded-[10px] border border-[#24272d] !bg-transparent text-[#a0a6af] transition-colors hover:!bg-transparent hover:border-[#f87171] hover:text-[#f87171]"
                          >
                            <Trash2 size={15} />
                          </button>
                        )}
                      </div>
                    </div>

                    {(retry.isError || remove.isError) && (
                      <p className="mt-3 text-[13px] text-[#f87171]">
                        {apiErrorMessage(retry.error ?? remove.error, '操作失败，请稍后重试')}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </main>
    </div>
  );
}
