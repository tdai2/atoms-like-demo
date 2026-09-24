import { client } from '@/lib/api';

export type StageState = 'pending' | 'running' | 'done' | 'failed';
export type ProjectStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface StageItem {
  stage: string;
  stage_name: string;
  stage_order: number;
  stage_state: StageState;
  stage_log: string;
  error_message: string;
  output_summary: string;
}

export interface ProjectSpec {
  app_name: string;
  display_name: string;
  pages: string[];
  entities: string[];
  stack: string[];
  files: number;
  component_tree: string[];
  notes: string;
  entry: string;
}

export interface TestMetric {
  id: string;
  label: string;
  value: string;
  passed: boolean;
}

export interface Quota {
  plan: string;
  used: number;
  limit: number;
  period: string;
}

export interface ProjectSummary {
  id: number;
  name: string;
  prompt: string;
  status: ProjectStatus;
  current_stage: string;
  template_key: string;
  preview_url: string;
  latest_version: number;
  artifact_key: string;
  created_at: string | null;
}

export interface ProjectList {
  quotas: Quota;
  items: ProjectSummary[];
  total: number;
}

export interface Pipeline {
  run_no: number;
  spec: ProjectSpec;
  stages: StageItem[];
  test_report: TestMetric[];
  quota: Quota;
  project: ProjectSummary;
}

export interface VersionItem {
  version: number;
  diff_summary: string;
  files_key: string;
  created_at: string | null;
}

/**
 * 生成接口只做数据库读写与预览地址解析，阶段执行在服务端后台进行，
 * 因此不需要为请求放宽超时；这里给足网络抖动余量即可。
 */
export const PIPELINE_TIMEOUT_MS = 60_000;

/**
 * 网关或上游瞬时故障（502/503/504 与网络层错误）不是业务失败：
 * 例如预览服务重启的几秒内，请求会被网关直接拒绝。这类错误应当自动重试，
 * 而不是立刻弹给用户一个"生成任务创建失败"。
 */
export function isTransientGatewayError(error: unknown): boolean {
  const candidate = error as
    | { status?: number; code?: number; response?: { status?: number } }
    | undefined;
  const status = candidate?.status ?? candidate?.code ?? candidate?.response?.status;
  if (typeof status === 'number') {
    return status === 408 || status === 429 || status === 502 || status === 503 || status === 504;
  }
  // 没有响应状态码通常意味着请求根本没到达服务端（连接被中断或超时）。
  const message = (error as { message?: string } | undefined)?.message ?? '';
  return /network error|timeout|failed to fetch|econnreset|socket hang up/i.test(message);
}

/** 轮询遇到瞬时故障时连续重试的次数上限，避免把网关抖动变成用户的失败态。 */
export const PIPELINE_RETRY_LIMIT = 4;

/** 从 web-sdk / axios 抛出的错误中提取可展示的信息。 */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const candidate = error as
    | { data?: { detail?: string }; response?: { data?: { detail?: string } }; message?: string }
    | undefined;
  return candidate?.data?.detail || candidate?.response?.data?.detail || candidate?.message || fallback;
}

export async function fetchProjects(): Promise<ProjectList> {
  const response = await client.apiCall.invoke({
    url: '/api/v1/generation/projects',
    method: 'GET',
    data: {},
  });
  return response.data as ProjectList;
}

export async function createProject(prompt: string, templateKey = ''): Promise<Pipeline> {
  const response = await client.apiCall.invoke({
    url: '/api/v1/generation/projects',
    method: 'POST',
    data: { prompt, template_key: templateKey },
    options: { timeout: PIPELINE_TIMEOUT_MS },
  });
  return response.data as Pipeline;
}

export async function fetchPipeline(projectId: number): Promise<Pipeline> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/generation/projects/${projectId}`,
    method: 'GET',
    data: {},
    options: { timeout: PIPELINE_TIMEOUT_MS },
  });
  return response.data as Pipeline;
}

export async function retryProject(projectId: number): Promise<Pipeline> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/generation/projects/${projectId}/retry`,
    method: 'POST',
    data: {},
    options: { timeout: PIPELINE_TIMEOUT_MS },
  });
  return response.data as Pipeline;
}

export async function fetchVersions(projectId: number): Promise<VersionItem[]> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/generation/projects/${projectId}/versions`,
    method: 'GET',
    data: {},
  });
  return response.data as VersionItem[];
}

export async function deleteProject(projectId: number): Promise<void> {
  await client.apiCall.invoke({
    url: `/api/v1/generation/projects/${projectId}`,
    method: 'DELETE',
    data: {},
  });
}

export type CaseType = 'structure' | 'behavior' | 'content';
export type CaseState = 'active' | 'disabled';
export type RunStatus = 'passed' | 'failed';

/** 阶段四：一条可自动执行的测试用例。 */
export interface TestCase {
  id: number;
  project_id: number;
  title: string;
  case_type: CaseType;
  preconditions: string;
  steps: string;
  expected: string;
  assertion: string;
  source: 'auto' | 'manual';
  case_state: CaseState;
}

/** 阶段四：单条用例在某次运行中的真实结果。 */
export interface CaseResult {
  case_id: number;
  title: string;
  case_type: CaseType;
  passed: boolean;
  detail: string;
}

/** 阶段四：一次执行记录，含统计与逐用例结果。 */
export interface TestRun {
  id: number;
  project_id: number;
  status: RunStatus;
  triggered_by: string;
  total: number;
  passed: number;
  failed: number;
  duration_ms: number;
  results: CaseResult[];
  created_at: string | null;
}

export interface TestSuite {
  project_id: number;
  artifact_ready: boolean;
  cases: TestCase[];
  latest_run: TestRun | null;
  runs: TestRun[];
}

export interface TestCaseInput {
  title: string;
  case_type: CaseType;
  preconditions?: string;
  steps?: string;
  expected?: string;
  assertion: string;
}

/** 测试用例生成与执行会调用模型或回读对象存储，给足超时余量。 */
export const TEST_TIMEOUT_MS = 120_000;

export async function fetchTestSuite(projectId: number): Promise<TestSuite> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/testing/projects/${projectId}/suite`,
    method: 'GET',
    data: {},
  });
  return response.data as TestSuite;
}

export async function generateTestCases(projectId: number): Promise<TestSuite> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/testing/projects/${projectId}/cases/generate`,
    method: 'POST',
    data: {},
    options: { timeout: TEST_TIMEOUT_MS },
  });
  return response.data as TestSuite;
}

export async function createTestCase(projectId: number, data: TestCaseInput): Promise<TestCase> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/testing/projects/${projectId}/cases`,
    method: 'POST',
    data,
  });
  return response.data as TestCase;
}

export async function updateTestCase(
  caseId: number,
  data: Partial<TestCaseInput> & { case_state?: CaseState },
): Promise<TestCase> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/testing/cases/${caseId}`,
    method: 'PUT',
    data,
  });
  return response.data as TestCase;
}

export async function deleteTestCase(caseId: number): Promise<void> {
  await client.apiCall.invoke({
    url: `/api/v1/testing/cases/${caseId}`,
    method: 'DELETE',
    data: {},
  });
}

export async function executeTestRun(projectId: number): Promise<TestRun> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/testing/projects/${projectId}/runs`,
    method: 'POST',
    data: {},
    options: { timeout: TEST_TIMEOUT_MS },
  });
  return response.data as TestRun;
}

export const CASE_TYPE_LABEL: Record<CaseType, string> = {
  structure: '结构',
  behavior: '交互',
  content: '内容',
};

export type BugSeverity = 'low' | 'medium' | 'high' | 'critical';
export type BugStatus = 'open' | 'fixing' | 'fixed' | 'fix_failed' | 'closed';
export type FixStatus = 'fixed' | 'fix_failed';

/** 阶段五：修复后在新产物上重跑用例的复测摘要。 */
export interface RetestSummary {
  executed: boolean;
  run_id?: number;
  status?: RunStatus;
  total?: number;
  passed?: number;
  failed?: number;
  duration_ms?: number;
  related_case_id?: number | null;
  related_case?: CaseResult | null;
  reason?: string;
  results?: CaseResult[];
}

/** 阶段五：一次自动修复的记录，含模型、源/目标版本、变更清单与复测结果。 */
export interface BugFixLog {
  id: number;
  bug_id: number;
  status: FixStatus;
  attempt_no: number;
  model: string;
  source_version: number;
  target_version: number;
  artifact_key: string;
  diff_summary: string;
  changes: string[];
  retest: RetestSummary | null;
  error_message: string;
  duration_ms: number;
  created_at: string | null;
}

/** 阶段五：一条缺陷记录。 */
export interface BugItem {
  id: number;
  project_id: number;
  title: string;
  description: string;
  severity: BugSeverity;
  reproduction: string;
  related_case_id: number | null;
  status: BugStatus;
  fix_attempts: number;
  latest_fix_id: number | null;
  resolution: string;
  target_version: number | null;
  created_at: string | null;
  updated_at: string | null;
  latest_fix: BugFixLog | null;
}

export interface BugStats {
  total: number;
  open: number;
  fixing: number;
  fixed: number;
  fix_failed: number;
  closed: number;
}

export interface BugPanel {
  project_id: number;
  artifact_ready: boolean;
  latest_version: number;
  stats: BugStats;
  bugs: BugItem[];
  fixes: BugFixLog[];
}

export interface BugInput {
  title: string;
  description?: string;
  severity?: BugSeverity;
  reproduction?: string;
  related_case_id?: number | null;
}

/** 自动修复会调用模型改写产物并上传新版本，给足超时余量。 */
export const BUG_TIMEOUT_MS = 240_000;

export const SEVERITY_LABEL: Record<BugSeverity, string> = {
  low: '轻微',
  medium: '一般',
  high: '严重',
  critical: '致命',
};

export const BUG_STATUS_LABEL: Record<BugStatus, string> = {
  open: '待修复',
  fixing: '修复中',
  fixed: '已修复',
  fix_failed: '修复失败',
  closed: '已关闭',
};

export async function fetchBugPanel(projectId: number): Promise<BugPanel> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/bugs/projects/${projectId}`,
    method: 'GET',
    data: {},
  });
  return response.data as BugPanel;
}

export async function createBug(projectId: number, data: BugInput): Promise<BugItem> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/bugs/projects/${projectId}`,
    method: 'POST',
    data,
  });
  return response.data as BugItem;
}

export async function updateBug(
  bugId: number,
  data: Partial<BugInput> & { status?: BugStatus },
): Promise<BugItem> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/bugs/${bugId}`,
    method: 'PUT',
    data,
  });
  return response.data as BugItem;
}

export async function deleteBug(bugId: number): Promise<void> {
  await client.apiCall.invoke({
    url: `/api/v1/bugs/${bugId}`,
    method: 'DELETE',
    data: {},
  });
}

export async function fixBug(bugId: number): Promise<BugItem> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/bugs/${bugId}/fix`,
    method: 'POST',
    data: {},
    options: { timeout: BUG_TIMEOUT_MS },
  });
  return response.data as BugItem;
}

export async function fetchBugFixes(bugId: number): Promise<BugFixLog[]> {
  const response = await client.apiCall.invoke({
    url: `/api/v1/bugs/${bugId}/fixes`,
    method: 'GET',
    data: {},
  });
  return response.data as BugFixLog[];
}

export function formatDateTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
