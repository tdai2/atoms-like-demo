import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  PencilLine,
  Play,
  Plus,
  Power,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import {
  useCreateTestCase,
  useDeleteTestCase,
  useExecuteTestRun,
  useGenerateTestCases,
  useTestSuite,
  useUpdateTestCase,
} from '@/hooks/useProjects';
import {
  apiErrorMessage,
  CASE_TYPE_LABEL,
  formatDateTime,
  type CaseResult,
  type CaseType,
  type RunStatus,
  type TestCase,
  type TestCaseInput,
} from '@/lib/projects';
import { cn } from '@/lib/utils';

const CASE_TYPES: CaseType[] = ['structure', 'behavior', 'content'];

const EMPTY_DRAFT: TestCaseInput = {
  title: '',
  case_type: 'structure',
  assertion: '',
  preconditions: '',
  steps: '',
  expected: '',
};

const RUN_TONE: Record<RunStatus, string> = {
  passed: 'bg-[rgba(74,222,128,0.14)] text-[#4ade80]',
  failed: 'bg-[rgba(248,113,113,0.14)] text-[#f87171]',
};

const FIELD_CLASS =
  'focus-ring h-10 w-full rounded-[10px] border border-[#24272d] bg-[#141619] px-3 text-[13px] text-[#f2f4f5] placeholder:text-[#6b727c]';

function ResultChip({ result }: { result: CaseResult | undefined }) {
  if (!result) {
    return (
      <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-1.5 py-0.5 text-[10px] text-[#6b727c]">
        未执行
      </span>
    );
  }
  return (
    <span
      className={cn(
        'font-mono-ui inline-flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 text-[10px]',
        result.passed ? RUN_TONE.passed : RUN_TONE.failed,
      )}
    >
      {result.passed ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
      {result.passed ? 'passed' : 'failed'}
    </span>
  );
}

/** 用例表单同时承担新增与编辑，字段与后端 `assertion` 契约一一对应。 */
function CaseForm({
  editing,
  draft,
  pending,
  onChange,
  onSubmit,
  onCancel,
}: {
  editing: TestCase | null;
  draft: TestCaseInput;
  pending: boolean;
  onChange: (patch: Partial<TestCaseInput>) => void;
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
        <p className="text-[14px] font-medium text-[#f2f4f5]">{editing ? '编辑用例' : '新增用例'}</p>
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
            <span className="text-[12px] text-[#6b727c]">标题</span>
            <input
              className={cn(FIELD_CLASS, 'mt-1.5')}
              value={draft.title}
              onChange={(event) => onChange({ title: event.target.value })}
              placeholder="例如：页面存在主标题"
              maxLength={120}
            />
          </label>
          <label className="block">
            <span className="text-[12px] text-[#6b727c]">类型</span>
            <select
              className={cn(FIELD_CLASS, 'mt-1.5')}
              value={draft.case_type}
              onChange={(event) => onChange({ case_type: event.target.value as CaseType })}
            >
              {CASE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {CASE_TYPE_LABEL[type]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="block">
          <span className="text-[12px] text-[#6b727c]">断言片段（必须能在产物源码中匹配到）</span>
          <input
            className={cn(FIELD_CLASS, 'font-mono-ui mt-1.5')}
            value={draft.assertion}
            onChange={(event) => onChange({ assertion: event.target.value })}
            placeholder="<h1"
            maxLength={200}
          />
        </label>

        <label className="block">
          <span className="text-[12px] text-[#6b727c]">复核步骤</span>
          <textarea
            className={cn(FIELD_CLASS, 'mt-1.5 h-[72px] resize-y py-2 leading-[1.6]')}
            value={draft.steps ?? ''}
            onChange={(event) => onChange({ steps: event.target.value })}
            placeholder="打开应用后依次执行的操作"
            maxLength={600}
          />
        </label>

        <label className="block">
          <span className="text-[12px] text-[#6b727c]">预期结果</span>
          <input
            className={cn(FIELD_CLASS, 'mt-1.5')}
            value={draft.expected ?? ''}
            onChange={(event) => onChange({ expected: event.target.value })}
            placeholder="例如：标题展示应用名称"
            maxLength={300}
          />
        </label>
      </div>

      <button
        type="submit"
        disabled={pending}
        className={cn(
          'focus-ring mt-4 inline-flex h-10 items-center gap-2 rounded-[10px] bg-[#c8f751] px-4 text-[13px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]',
          pending && 'pointer-events-none opacity-45',
        )}
      >
        {pending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
        {editing ? '保存修改' : '添加用例'}
      </button>
    </form>
  );
}

export default function TestSuitePanel({ projectId, enabled }: { projectId: number; enabled: boolean }) {
  const suite = useTestSuite(projectId, enabled);
  const generate = useGenerateTestCases(projectId);
  const run = useExecuteTestRun(projectId);
  const createCase = useCreateTestCase(projectId);
  const updateCase = useUpdateTestCase(projectId);
  const removeCase = useDeleteTestCase(projectId);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TestCase | null>(null);
  const [draft, setDraft] = useState<TestCaseInput>(EMPTY_DRAFT);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  useEffect(() => {
    setFormOpen(false);
    setEditing(null);
    setDraft(EMPTY_DRAFT);
    setSelectedRunId(null);
    setConfirmId(null);
  }, [projectId]);

  const cases = suite.data?.cases ?? [];
  const runs = suite.data?.runs ?? [];
  const activeRun = runs.find((item) => item.id === selectedRunId) ?? runs[0] ?? null;
  const resultByCase = new Map((activeRun?.results ?? []).map((item) => [item.case_id, item]));
  const artifactReady = suite.data?.artifact_ready ?? false;
  const busy = generate.isPending || run.isPending;
  const actionError = generate.error ?? run.error ?? createCase.error ?? updateCase.error ?? removeCase.error;
  const suiteError = suite.isError ? apiErrorMessage(suite.error, '测试数据加载失败') : '';

  const openCreate = () => {
    setEditing(null);
    setDraft(EMPTY_DRAFT);
    setFormOpen(true);
  };

  const openEdit = (item: TestCase) => {
    setEditing(item);
    setDraft({
      title: item.title,
      case_type: item.case_type,
      assertion: item.assertion,
      preconditions: item.preconditions,
      steps: item.steps,
      expected: item.expected,
    });
    setFormOpen(true);
  };

  const submitForm = () => {
    if (editing) {
      updateCase.mutate({ caseId: editing.id, data: draft }, { onSuccess: () => setFormOpen(false) });
      return;
    }
    createCase.mutate(draft, { onSuccess: () => setFormOpen(false) });
  };

  return (
    <section className="mt-6 rounded-[14px] border border-[#24272d] bg-[#17191d] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono-ui text-[11px] uppercase tracking-[0.16em] text-[#c8f751]">test suite</p>
          <h2 className="mt-2 text-[18px] font-semibold text-[#f2f4f5]">测试用例与执行</h2>
          <p className="mt-1.5 max-w-[70ch] text-[13px] leading-[1.6] text-[#a0a6af]">
            用例基于项目方案与真实产物生成，断言直接在产物源码上匹配；通过与否由产物决定，不由模型判定。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => generate.mutate()}
            disabled={!artifactReady || generate.isPending || run.isPending}
            className={cn(
              'focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] border border-[#24272d] !bg-transparent px-4 text-[13px] text-[#f2f4f5] transition-colors hover:!bg-transparent hover:border-[#3a3f47]',
              (!artifactReady || busy) && 'pointer-events-none opacity-45',
            )}
          >
            {generate.isPending ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {generate.isPending ? '正在生成用例…' : '生成用例'}
          </button>
          <button
            type="button"
            onClick={() => run.mutate()}
            disabled={!artifactReady || cases.length === 0 || busy}
            className={cn(
              'focus-ring inline-flex h-10 items-center gap-2 rounded-[10px] bg-[#c8f751] px-4 text-[13px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]',
              (!artifactReady || cases.length === 0 || busy) && 'pointer-events-none opacity-45',
            )}
          >
            {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {run.isPending ? '正在执行…' : '执行测试'}
          </button>
        </div>
      </div>

      {!artifactReady && (
        <p className="mt-4 rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3 text-[13px] text-[#a0a6af]">
          项目尚未产出可访问的产物，完成生成后才能生成并执行用例。
        </p>
      )}

      {suiteError && (
        <div className="mt-4 flex flex-col gap-3 rounded-[10px] border border-[#f87171]/40 bg-[rgba(248,113,113,0.06)] px-3.5 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2.5">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-[#f87171]" />
            <p className="text-[13px] leading-[1.6] text-[#f2f4f5]">{suiteError}</p>
          </div>
          <button
            type="button"
            onClick={() => suite.refetch()}
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

      {suite.isLoading && (
        <div className="mt-4 flex items-center gap-3 rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3">
          <Loader2 size={16} className="animate-spin text-[#c8f751]" />
          <span className="font-mono-ui text-[12px] text-[#a0a6af]">正在加载测试数据…</span>
        </div>
      )}

      {!suite.isLoading && !suiteError && cases.length === 0 && (
        <div className="mt-4 rounded-[10px] border border-dashed border-[#24272d] bg-[#141619] px-4 py-6 text-center">
          <p className="text-[14px] text-[#f2f4f5]">暂无测试用例</p>
          <p className="mt-1 text-[13px] leading-[1.6] text-[#a0a6af]">
            点击「生成用例」由模型基于方案与产物产出，也可以手动添加需要固定验证的断言。
          </p>
        </div>
      )}

      {activeRun && (
        <div className="mt-5 rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <span
              className={cn(
                'font-mono-ui rounded-[6px] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]',
                RUN_TONE[activeRun.status],
              )}
            >
              {activeRun.status === 'passed' ? '全部通过' : '存在失败'}
            </span>
            <span className="font-mono-ui text-[12px] text-[#f2f4f5]">
              通过 {activeRun.passed} / {activeRun.total}
            </span>
            <span className="font-mono-ui text-[11px] text-[#6b727c]">
              失败 {activeRun.failed} · 耗时 {(activeRun.duration_ms / 1000).toFixed(2)}s ·{' '}
              {activeRun.triggered_by === 'auto'
                ? '自动触发'
                : activeRun.triggered_by === 'fix'
                  ? '修复后复测'
                  : '手动触发'}
            </span>
            <span className="font-mono-ui ml-auto text-[11px] text-[#6b727c]">
              {formatDateTime(activeRun.created_at)}
            </span>
          </div>

          {runs.length > 1 && (
            <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[#24272d] pt-3">
              {runs.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedRunId(item.id)}
                  className={cn(
                    'focus-ring font-mono-ui rounded-[6px] border px-2 py-1 text-[11px] transition-colors',
                    item.id === activeRun.id
                      ? 'border-[#c8f751] bg-[rgba(200,247,81,0.12)] text-[#c8f751]'
                      : 'border-[#24272d] bg-transparent text-[#a0a6af] hover:border-[#3a3f47] hover:text-[#f2f4f5]',
                  )}
                >
                  #{item.id} · {item.passed}/{item.total}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {cases.length > 0 && (
        <ul className="mt-4 space-y-2.5">
          {cases.map((item) => {
            const result = resultByCase.get(item.id);
            const disabled = item.case_state === 'disabled';
            return (
              <li
                key={item.id}
                className={cn(
                  'rounded-[10px] border border-[#24272d] bg-[#141619] px-3.5 py-3',
                  disabled && 'opacity-70',
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-1.5 py-0.5 text-[10px] text-[#a0a6af]">
                        {CASE_TYPE_LABEL[item.case_type]}
                      </span>
                      <span className="text-[14px] font-medium text-[#f2f4f5]">{item.title}</span>
                      <span className="font-mono-ui rounded-[6px] border border-[#24272d] px-1.5 py-0.5 text-[10px] text-[#6b727c]">
                        {item.source === 'auto' ? '自动' : '手动'}
                      </span>
                      {disabled && (
                        <span className="font-mono-ui rounded-[6px] bg-[rgba(107,114,124,0.18)] px-1.5 py-0.5 text-[10px] text-[#a0a6af]">
                          已停用
                        </span>
                      )}
                      <ResultChip result={result} />
                    </div>
                    <p className="font-mono-ui mt-1.5 break-all text-[11px] text-[#6b727c]">
                      断言：{item.assertion}
                    </p>
                    {item.expected && (
                      <p className="mt-1 text-[12px] leading-[1.6] text-[#a0a6af]">预期：{item.expected}</p>
                    )}
                    {item.steps && (
                      <p className="mt-0.5 text-[12px] leading-[1.6] text-[#6b727c]">步骤：{item.steps}</p>
                    )}
                    {result && !result.passed && (
                      <p className="mt-1.5 text-[12px] leading-[1.6] text-[#f87171]">{result.detail}</p>
                    )}
                  </div>

                  <div className="flex shrink-0 items-center gap-1.5">
                    {confirmId === item.id ? (
                      <>
                        <button
                          type="button"
                          onClick={() => removeCase.mutate(item.id, { onSuccess: () => setConfirmId(null) })}
                          disabled={removeCase.isPending}
                          className={cn(
                            'focus-ring inline-flex h-8 items-center gap-1.5 rounded-[8px] bg-[#f87171] px-2.5 text-[12px] font-semibold text-[#0b0c0e] hover:bg-[#ef5f5f]',
                            removeCase.isPending && 'pointer-events-none opacity-45',
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
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() =>
                            updateCase.mutate({
                              caseId: item.id,
                              data: { case_state: disabled ? 'active' : 'disabled' },
                            })
                          }
                          title={disabled ? '启用该用例' : '停用该用例'}
                          aria-label={disabled ? '启用该用例' : '停用该用例'}
                          className="focus-ring inline-flex h-8 w-8 items-center justify-center rounded-[8px] border border-[#24272d] !bg-transparent text-[#a0a6af] hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]"
                        >
                          <Power size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={() => openEdit(item)}
                          title="编辑该用例"
                          aria-label="编辑该用例"
                          className="focus-ring inline-flex h-8 w-8 items-center justify-center rounded-[8px] border border-[#24272d] !bg-transparent text-[#a0a6af] hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]"
                        >
                          <PencilLine size={13} />
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmId(item.id)}
                          title="删除该用例"
                          aria-label="删除该用例"
                          className="focus-ring inline-flex h-8 w-8 items-center justify-center rounded-[8px] border border-[#24272d] !bg-transparent text-[#a0a6af] hover:!bg-transparent hover:border-[#f87171]/50 hover:text-[#f87171]"
                        >
                          <Trash2 size={13} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {!formOpen && artifactReady && (
        <button
          type="button"
          onClick={openCreate}
          className="focus-ring mt-4 inline-flex h-10 items-center gap-2 rounded-[10px] border border-dashed border-[#24272d] !bg-transparent px-4 text-[13px] text-[#a0a6af] transition-colors hover:!bg-transparent hover:border-[#3a3f47] hover:text-[#f2f4f5]"
        >
          <Plus size={14} />
          手动新增用例
        </button>
      )}

      {formOpen && (
        <CaseForm
          editing={editing}
          draft={draft}
          pending={createCase.isPending || updateCase.isPending}
          onChange={(patch) => setDraft((prev) => ({ ...prev, ...patch }))}
          onSubmit={submitForm}
          onCancel={() => setFormOpen(false)}
        />
      )}
    </section>
  );
}
