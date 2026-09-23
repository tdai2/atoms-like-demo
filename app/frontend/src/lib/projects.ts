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

/** 单阶段可能包含模型调用与对象存储读写，轮询请求需要放宽超时。 */
export const PIPELINE_TIMEOUT_MS = 600_000;

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
