import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Bug,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  PencilLine,
  Plus,
  RefreshCw,
  Trash2,
  Wrench,
  X,
  XCircle,
} from 'lucide-react';
import {
  useBugFixes,
  useBugPanel,
  useCreateBug,
  useDeleteBug,
  useFixBug,
  useUpdateBug,
} from '@/hooks/useProjects';
import {
  apiErrorMessage,
  BUG_STATUS_LABEL,
  formatDateTime,
  SEVERITY_LABEL,
  type BugInput,
  type BugItem,
  type BugSeverity,
  type BugStatus,
  type TestCase,
} from '@/lib/projects';
import { cn } from '@/lib/utils';

const SEVERITIES: BugSeverity[] = ['low', 'medium', 'high', 'critical'];

const SEVERITY_TONE: Record<BugSeverity, string> = {
  low: 'bg-[rgba(107,114,124,0.18)] text-[#a0a6af]',
  medium: 'bg-[rgba(200,247,81,0.12)] text-[#c8f751]',
  high: 'bg-[rgba(250,204,21,0.14)] text-[#facc15]',
  critical: 'bg-[rgba(248,113,113,0.14)] text-[#f87171]',
};

const STATUS_TONE: Record<BugStatus, string> = {
  open: 'bg-[rgba(250,204,21,0.14)] text-[#facc15]',
  fixing: 'bg-[rgba(200,247,81,0.12)] text-[#c8f751]',
  fixed: 'bg-[rgba(74,222,128,0.14)] text-[#4ade80]',
  fix_failed: 'bg-[rgba(248,113,113,0.14)] text-[#f87171]',
  closed: 'bg-[rgba(107,114,124,0.18)] text-[#a0a6af]',
};

const EMPTY_DRAFT: BugInput = {
  title: '',
  description: '',
  severity: 'medium',
  reproduction: '',
  related_case_id: null,
};

const FIELD_CLASS =
  'focus-ring h-10 w-full rounded-[10px] border border-[#24272d] bg-[#141619] px-3 text-[13px] text-[#f2f4f5] placeholder:text-[#6b727c]';

/** 一条缺陷的完整信息：状态、自动修复入口与最近一次修复的复测结果。 */
function BugRow({
  bug,
  cases,
  busy,
  onFix,
  onEdit,
  onToggleStatus,
  onDelete,
}: {
  bug: BugItem;
  cases: TestCase[];
  busy: boolean;
  onFix: (bug: BugItem) => void;
  onEdit: (bug: BugItem) => void;
  onToggleStatus: (bug: BugItem) => void;
  onDelete: (bug: BugItem) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const fixes = useBugFixes(bug.id, expanded);
  const relatedCase = cases.find((item) => item.id === bug.related_case_id);
  const latest = bug.latest_fix;
  const retest = latest?.retest ?? null;
  const fixing = bug.status === 'fixing';

  return (
    <li className="rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2.5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                'font-mono-ui rounded-[6px] px-1.5 py-0.5 text-[10px]',
                STATUS_TONE[bug.status],
              )}
            >
              {BUG_STATUS_LABEL[bug.status]}
            </span>
            <span
              className={cn(
                'font-mono-ui rounded-[6px] px-1.5 py-0.5 text-[10px]',
                SEVERITY_TONE[bug.severity],
              )}
            >
              {SEVERITY_LABEL[bug.severity]}
            </span>
            <span className="text-[14px] font-medium text-[#f2f4f5]">{bug.title}</span>
            {bug.fix_attempts > 0 && (
              <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-1.5 py-0.5 text-[10px] text-[#6b727c]">
                已尝试 {bug.fix_attempts} 次
              </span>
            )}
          </div>

          {bug.description && (
            <p className="mt-1.5 text-[12px] leading-[1.6] text-[#a0a6af]">{bug.description}</p>
          )}
          {bug.reproduction && (
            <p className="mt-1 text-[12px] leading-[1.6] text-[#6b727c]">复现：{bug.reproduction}</p>
          )}
          {relatedCase && (
            <p className="font-mono-ui mt-1 break-all text-[11px] text-[#6b727c]">
              关联用例：{relatedCase.title}（断言 {relatedCase.assertion}）
            </p>
          )}

          {latest && (
            <div className="mt-2 rounded-[8px] border border-[#24272d] bg-[#17191d] px-2.5 py-2">
              <div className="flex flex-wrap items-center gap-2">
                {latest.status === 'fixed' ? (
                  <CheckCircle2 size={13} className="shrink-0 text-[#4ade80]" />
                ) : (
                  <XCircle size={13} className="shrink-0 text-[#f87171]" />
                )}
                <span className="font-mono-ui text-[11px] text-[#f2f4f5]">
                  v{latest.source_version} → v{latest.target_version}
                </span>
                <span className="font-mono-ui text-[11px] text-[#6b727c]">
                  {latest.model} · {(latest.duration_ms / 1000).toFixed(2)}s
                </span>
                <span className="font-mono-ui ml-auto text-[11px] text-[#6b727c]">
                  {formatDateTime(latest.created_at)}
                </span>
              </div>
              <p className="mt-1 text-[12px] leading-[1.6] text-[#a0a6af]">
                {latest.error_message || latest.diff_summary}
              </p>
              {retest?.executed && (
                <p
                  className={cn(
                    'font-mono-ui mt-1 text-[11px]',
                    retest.status === 'passed' ? 'text-[#4ade80]' : 'text-[#f87171]',
                  )}
                >
                  复测：通过 {retest.passed} / {retest.total} · 运行 #{retest.run_id}
                </p>
              )}
              {retest && !retest.executed && (
                <p className="font-mono-ui mt-1 text-[11px] text-[#6b727c]">未执行复测</p>
              )}
            </div>
          )}

          {bug.resolution && (
            <p className="mt-1.5 text-[12px] leading-[1.6] text-[#a0a6af]">结论：{bug.resolution}</p>
          )}

          <button
            type="button"
            onClick={() => setExpanded((prev) => !prev)}
            className="focus-ring mt-2 inline-flex items-center gap-1 rounded-[6px] text-[11px] text-[#6b727c] transition-colors hover:text-[#f2f4f5]"
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            修复历史 {expanded ? '收起' : '展开'}
          </button>

          {expanded && (
            <div className="mt-2 space-y-1.5">
              {fixes.isLoading && (
                <p className="font-mono-ui text-[11px] text-[#6b727c]">正在加载修复历史…</p>
              )}
              {fixes.isError && (
                <p className="text-[11px] text-[#f87171]">
                  {apiErrorMessage(fixes.error, '修复历史加载失败')}
                </p>
              )}
              {!fixes.isLoading && !fixes.isError && (fixes.data?.length ?? 0) === 0 && (
                <p className="font-mono-ui text-[11px] text-[#6b727c]">该缺陷还没有修复记录</p>
              )}
              {(fixes.data ?? []).map((item) => (
                <div
                  key={item.id}
                  className="rounded-[8px] border border-[#24272d] bg-[#17191d] px-2.5 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        'font-mono-ui rounded-[6px] px-1.5 py-0.5 text-[10px]',
                        item.status === 'fixed'
                          ? 'bg-[rgba(74,222,128,0.14)] text-[#4ade80]'
                          : 'bg-[rgba(248,113,113,0.14)] text-[#f87171]',
                      )}
                    >
                      第 {item.attempt_no} 次 · {item.status === 'fixed' ? '成功' : '失败'}
                    </span>
                    <span className="font-mono-ui text-[11px] text-[#6b727c]">
                      v{item.source_version} → v{item.target_version} · {formatDateTime(item.created_at)}
                    </span>
                  </div>
                  {item.error_message && (
                    <p className="mt-1 text-[12px] leading-[1.6] text-[#f87171]">{item.error_message}</p>
                  )}
                  {item.changes.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {item.changes.map((change) => (
                        <li key={change} className="text-[12px] leading-[1.6] text-[#a0a6af]">
                          · {change}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {!fixing && bug.status !== 'closed' && (
            <button
              type="button"
              onClick={() => onFix(bug)}
              disabled={busy}
              className={cn(
                'focus-ring inline-flex h-8 items-center gap-1.5 rounded-[8px] bg-[#c8f751] px-2.5 text-[12px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]',
                busy && 'pointer-events-none opacity-45',
              )}
            >
              {busy ? <Loader2 size={12} className="animate-spin" /> : <Wrench size={12} />}
              {busy ? '修复中…' : '自动修复'}
            </button>
          )}
          {fixing && (
            <span className="font-mono-ui inline-flex h-8 items-center gap-1.5 rounded-[8px] border border-[#24272d] px-2.5 text-[12px] text-[#c8f751]">
              <Loader2 size={12} className="animate-spin" />
              修复中
            </span>
          )}
          <button
            type="button"
            onClick={() => onToggleStatus(bug)}
            disabled={busy || fixing}
            className={cn(
              'focus-ring inline-flex h-8 items-center rounded-[8px] border border-[#24272d] !bg-transparent px-2.5 text-[12px] text-[#a0a6af] hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]',
              (busy || fixing) && 'pointer-events-none opacity-45',
            )}
          >
            {bug.status === 'closed' ? '重新打开' : '关闭缺陷'}
          </button>
          <button
            type="button"
            onClick={() => onEdit(bug)}
            title="编辑该缺陷"
            aria-label="编辑该缺陷"
            className="focus-ring inline-flex h-8 w-8 items-center justify-center rounded-[8px] border border-[#24272d] !bg-transparent text-[#a0a6af] hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]"
          >
            <PencilLine size={13} />
          </button>
          <button
            type="button"
            onClick={() => onDelete(bug)}
            title="删除该缺陷"
            aria-label="删除该缺陷"
            className="focus-ring inline-flex h-8 w-8 items-center justify-center rounded-[8px] border border-[#24272d] !bg-transparent text-[#a0a6af] hover:!bg-transparent hover:border-[#f87171]/50 hover:text-[#f87171]"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </li>
  );
}

/** 缺陷表单同时承担提交与编辑，字段与后端 `/api/v1/bugs` 契约一一对应。 */
function BugForm({
  editing,
  draft,
  cases,
  pending,
  onChange,
  onSubmit,
  onCancel,
}: {
  editing: BugItem | null;
  draft: BugInput;
  cases: TestCase[];
  pending: boolean;
  onChange: (patch: Partial<BugInput>) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  return (
    <form
      className="mt-4 rounded-[10px] border border-[#24272d] bg-[#141619] p-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-[14px] font-medium text-[#f2f4f5]">{editing ? '编辑缺陷' : '提交缺陷'}</p>
        <button
          type="button"
          onClick={onCancel}
          className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-[8px] border border-[#24272d] !bg-transparent px-2.5 text-[12px] text-[#a0a6af] hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]"
        >
          <X size={12} />
          收起
        </button>
      </div>

      <div className="mt-3 grid gap-3">
        <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
          <label className="block">
            <span className="text-[12px] text-[#6b727c]">缺陷标题</span>
            <input
              className={cn(FIELD_CLASS, 'mt-1.5')}
              value={draft.title}
              onChange={(event) => onChange({ title: event.target.value })}
              placeholder="例如：点击新增按钮无响应"
              maxLength={120}
            />
          </label>
          <label className="block">
            <span className="text-[12px] text-[#6b727c]">严重级别</span>
            <select
              className={cn(FIELD_CLASS, 'mt-1.5')}
              value={draft.severity}
              onChange={(event) => onChange({ severity: event.target.value as BugSeverity })}
            >
              {SEVERITIES.map((severity) => (
                <option key={severity} value={severity}>
                  {SEVERITY_LABEL[severity]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="block">
          <span className="text-[12px] text-[#6b727c]">缺陷表现</span>
          <textarea
            className={cn(FIELD_CLASS, 'mt-1.5 h-[72px] resize-y py-2 leading-[1.6]')}
            value={draft.description ?? ''}
            onChange={(event) => onChange({ description: event.target.value })}
            placeholder="描述实际表现与期望表现的差异"
            maxLength={2000}
          />
        </label>

        <label className="block">
          <span className="text-[12px] text-[#6b727c]">复现步骤</span>
          <textarea
            className={cn(FIELD_CLASS, 'mt-1.5 h-[72px] resize-y py-2 leading-[1.6]')}
            value={draft.reproduction ?? ''}
            onChange={(event) => onChange({ reproduction: event.target.value })}
            placeholder="打开应用后依次执行的操作"
            maxLength={1200}
          />
        </label>

        <label className="block">
          <span className="text-[12px] text-[#6b727c]">关联测试用例（可省略，关联后复测以该用例结论为准）</span>
          <select
            className={cn(FIELD_CLASS, 'mt-1.5')}
            value={draft.related_case_id ?? 0}
            onChange={(event) =>
              onChange({ related_case_id: Number(event.target.value) || null })
            }
          >
            <option value={0}>不关联</option>
            {cases.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="submit"
          disabled={pending}
          className={cn(
            'focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] bg-[#c8f751] px-4 text-[13px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]',
            pending && 'pointer-events-none opacity-45',
          )}
        >
          {pending ? <Loader2 size={14} className="animate-spin" /> : <Bug size={14} />}
          {editing ? '保存修改' : '提交缺陷'}
        </button>
        {editing && (
          <span className="font-mono-ui text-[11px] text-[#6b727c]">
            当前状态：{BUG_STATUS_LABEL[editing.status]}
          </span>
        )}
      </div>
    </form>
  );
}

export default function BugPanel({
  projectId,
  enabled,
  cases,
}: {
  projectId: number;
  enabled: boolean;
  cases: TestCase[];
}) {
  const panel = useBugPanel(projectId, enabled);
  const createBugMutation = useCreateBug(projectId);
  const updateBugMutation = useUpdateBug(projectId);
  const deleteBugMutation = useDeleteBug(projectId);
  const fixBugMutation = useFixBug(projectId);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<BugItem | null>(null);
  const [draft, setDraft] = useState<BugInput>(EMPTY_DRAFT);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [fixingId, setFixingId] = useState<number | null>(null);

  useEffect(() => {
    setFormOpen(false);
    setEditing(null);
    setDraft(EMPTY_DRAFT);
    setConfirmId(null);
    setFixingId(null);
  }, [projectId]);

  const bugs = panel.data?.bugs ?? [];
  const stats = panel.data?.stats;
  const artifactReady = panel.data?.artifact_ready ?? false;
  const actionError =
    createBugMutation.error ??
    updateBugMutation.error ??
    deleteBugMutation.error ??
    fixBugMutation.error;
  const panelError = panel.isError ? apiErrorMessage(panel.error, '缺陷数据加载失败') : '';
  const formPending = createBugMutation.isPending || updateBugMutation.isPending;

  const openCreate = () => {
    setEditing(null);
    setDraft(EMPTY_DRAFT);
    setFormOpen(true);
  };

  const openEdit = (bug: BugItem) => {
    setEditing(bug);
    setDraft({
      title: bug.title,
      description: bug.description,
      severity: bug.severity,
      reproduction: bug.reproduction,
      related_case_id: bug.related_case_id,
    });
    setFormOpen(true);
  };

  const submitForm = () => {
    if (editing) {
      updateBugMutation.mutate(
        { bugId: editing.id, data: draft },
        { onSuccess: () => setFormOpen(false) },
      );
      return;
    }
    createBugMutation.mutate(draft, { onSuccess: () => setFormOpen(false) });
  };

  const handleFix = (bug: BugItem) => {
    setFixingId(bug.id);
    fixBugMutation.mutate(bug.id, { onSettled: () => setFixingId(null) });
  };

  const handleToggleStatus = (bug: BugItem) => {
    updateBugMutation.mutate({
      bugId: bug.id,
      data: { status: bug.status === 'closed' ? 'open' : 'closed' },
    });
  };

  return (
    <section className="mt-6 rounded-[14px] border border-[#24272d] bg-[#17191d] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">
            bug fixing
          </p>
          <h2 className="mt-2 text-[18px] font-semibold text-[#f2f4f5]">缺陷记录与自动修复</h2>
          <p className="mt-1.5 max-w-[70ch] text-[13px] leading-[1.6] text-[#a0a6af]">
            提交缺陷后由模型改写产物并发布为新版本，随后在新产物上重跑启用用例复测；是否修好由真实产物决定，不由模型自述。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => panel.refetch()}
            disabled={panel.isFetching}
            className={cn(
              'focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] border border-[#24272d] !bg-transparent px-3.5 text-[13px] text-[#a0a6af] transition-colors hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]',
              panel.isFetching && 'pointer-events-none opacity-45',
            )}
          >
            <RefreshCw size={14} />
            刷新
          </button>
          {!formOpen && artifactReady && (
            <button
              type="button"
              onClick={openCreate}
              className="focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] bg-[#c8f751] px-4 text-[13px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
            >
              <Plus size={14} />
              提交缺陷
            </button>
          )}
        </div>
      </div>

      {stats && stats.total > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-2 py-0.5 text-[11px] text-[#a0a6af]">
            共 {stats.total}
          </span>
          <span className="font-mono-ui rounded-[6px] px-2 py-0.5 text-[11px] bg-[rgba(250,204,21,0.14)] text-[#facc15]">
            待修复 {stats.open}
          </span>
          {stats.fixing > 0 && (
            <span className="font-mono-ui rounded-[6px] px-2 py-0.5 text-[11px] bg-[rgba(200,247,81,0.12)] text-[#c8f751]">
              修复中 {stats.fixing}
            </span>
          )}
          <span className="font-mono-ui rounded-[6px] px-2 py-0.5 text-[11px] bg-[rgba(74,222,128,0.14)] text-[#4ade80]">
            已修复 {stats.fixed}
          </span>
          {stats.fix_failed > 0 && (
            <span className="font-mono-ui rounded-[6px] px-2 py-0.5 text-[11px] bg-[rgba(248,113,113,0.14)] text-[#f87171]">
              修复失败 {stats.fix_failed}
            </span>
          )}
          <span className="font-mono-ui rounded-[6px] px-2 py-0.5 text-[11px] bg-[rgba(107,114,124,0.18)] text-[#a0a6af]">
            已关闭 {stats.closed}
          </span>
        </div>
      )}

      {!artifactReady && (
        <p className="mt-4 rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3 text-[13px] text-[#a0a6af]">
          项目尚未产出可访问的产物，完成生成后才能提交缺陷并自动修复。
        </p>
      )}

      {panelError && (
        <div className="mt-4 flex flex-col gap-3 rounded-[10px] border border-[#f87171]/40 bg-[rgba(248,113,113,0.06)] px-3.5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-[#f87171]" />
            <p className="text-[13px] leading-[1.6] text-[#f2f4f5]">{panelError}</p>
          </div>
          <button
            type="button"
            onClick={() => panel.refetch()}
            className="focus-ring inline-flex h-9 shrink-0 items-center gap-2 rounded-[8px] border border-[#24272d] !bg-transparent px-3 text-[12px] text-[#f2f4f5] hover:!bg-transparent hover:border-[#3a3f47]"
          >
            <RefreshCw size={12} />
            重试
          </button>
        </div>
      )}

      {actionError && (
        <p className="mt-4 rounded-[10px] border border-[#f87171]/40 bg-[rgba(248,113,113,0.06)] px-3.5 py-3 text-[13px] leading-[1.6] text-[#f87171]">
          {apiErrorMessage(actionError, '操作失败，请稍后再试')}
        </p>
      )}

      {panel.isLoading && (
        <div className="mt-4 flex items-center gap-3 rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3">
          <Loader2 size={16} className="animate-spin text-[#c8f751]" />
          <span className="font-mono-ui text-[12px] text-[#a0a6af]">正在加载缺陷数据…</span>
        </div>
      )}

      {!panel.isLoading && !panelError && bugs.length === 0 && (
        <div className="mt-4 rounded-[10px] border border-dashed border-[#24272d] bg-[#141619] px-4 py-6 text-center">
          <p className="text-[14px] text-[#f2f4f5]">暂无缺陷记录</p>
          <p className="mt-1 text-[13px] leading-[1.6] text-[#a0a6af]">
            提交一条缺陷后可以触发自动修复，修复结果会在新版本上复测并留下记录。
          </p>
        </div>
      )}

      {bugs.length > 0 && (
        <ul className="mt-4 space-y-2.5">
          {bugs.map((bug) => (
            <div key={bug.id}>
              {confirmId === bug.id ? (
                <div className="flex flex-wrap items-center justify-between gap-2.5 rounded-[10px] border border-[#f87171]/40 bg-[rgba(248,113,113,0.06)] px-3.5 py-3">
                  <p className="text-[13px] text-[#f2f4f5]">
                    确认删除「{bug.title}」及其全部修复记录？
                  </p>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() =>
                        deleteBugMutation.mutate(bug.id, { onSuccess: () => setConfirmId(null) })
                      }
                      disabled={deleteBugMutation.isPending}
                      className={cn(
                        'focus-ring inline-flex h-8 items-center rounded-[8px] bg-[#f87171] px-2.5 text-[12px] font-semibold text-[#0b0c0e] hover:bg-[#ef5f5f]',
                        deleteBugMutation.isPending && 'pointer-events-none opacity-45',
                      )}
                    >
                      确认删除
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmId(null)}
                      className="focus-ring inline-flex h-8 items-center rounded-[8px] border border-[#24272d] !bg-transparent px-2.5 text-[12px] text-[#a0a6af] hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]"
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                <BugRow
                  bug={bug}
                  cases={cases}
                  busy={fixingId === bug.id}
                  onFix={handleFix}
                  onEdit={openEdit}
                  onToggleStatus={handleToggleStatus}
                  onDelete={(item) => setConfirmId(item.id)}
                />
              )}
            </div>
          ))}
        </ul>
      )}

      {formOpen && (
        <BugForm
          editing={editing}
          draft={draft}
          cases={cases}
          pending={formPending}
          onChange={(patch) => setDraft((prev) => ({ ...prev, ...patch }))}
          onSubmit={submitForm}
          onCancel={() => setFormOpen(false)}
        />
      )}
    </section>
  );
}
