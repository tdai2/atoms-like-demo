import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createProject,
  createTestCase,
  deleteProject,
  deleteTestCase,
  executeTestRun,
  fetchPipeline,
  fetchProjects,
  fetchTestSuite,
  generateTestCases,
  isTransientGatewayError,
  PIPELINE_RETRY_LIMIT,
  retryProject,
  updateTestCase,
  type CaseState,
  type TestCaseInput,
} from '@/lib/projects';

const POLL_INTERVAL_MS = 1500;

/**
 * 网关瞬时错误（502/503/504 或连接被中断）按指数退避重试，
 * 其余错误立即暴露给用户，避免把真实的业务失败也拖成等待。
 */
const retryTransient = (failureCount: number, error: unknown) =>
  isTransientGatewayError(error) && failureCount < PIPELINE_RETRY_LIMIT;

const retryDelay = (attemptIndex: number) => Math.min(1000 * 2 ** attemptIndex, 8000);

export function useProjectList(enabled: boolean) {
  return useQuery({
    queryKey: ['generation', 'projects'],
    queryFn: fetchProjects,
    enabled,
    staleTime: 5_000,
    retry: retryTransient,
    retryDelay,
  });
}

/** 项目流水线快照；运行中自动轮询，进入终态后停止。 */
export function useProjectPipeline(projectId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ['generation', 'pipeline', projectId],
    queryFn: () => fetchPipeline(projectId as number),
    enabled: enabled && projectId !== null,
    retry: retryTransient,
    retryDelay,
    refetchInterval: (query) => {
      const status = query.state.data?.project.status;
      return !status || status === 'running' || status === 'queued' ? POLL_INTERVAL_MS : false;
    },
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ prompt, templateKey }: { prompt: string; templateKey?: string }) =>
      createProject(prompt, templateKey ?? ''),
    retry: retryTransient,
    retryDelay,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['generation', 'projects'] });
    },
  });
}

export function useRetryProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: number) => retryProject(projectId),
    retry: retryTransient,
    retryDelay,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['generation', 'projects'] });
      queryClient.setQueryData(['generation', 'pipeline', data.project.id], data);
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: number) => deleteProject(projectId),
    retry: retryTransient,
    retryDelay,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['generation', 'projects'] });
    },
  });
}

/** 阶段四：测试面板快照（用例、最近运行与运行历史）。 */
export function useTestSuite(projectId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ['testing', 'suite', projectId],
    queryFn: () => fetchTestSuite(projectId as number),
    enabled: enabled && projectId !== null,
    retry: retryTransient,
    retryDelay,
  });
}

/**
 * 用例生成与执行都会消耗真实的模型额度或对象存储读取，
 * 因此禁用自动重试：失败必须让用户看到结果并自行决定是否再来一次。
 */
export function useGenerateTestCases(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => generateTestCases(projectId),
    retry: false,
    onSuccess: (data) => {
      queryClient.setQueryData(['testing', 'suite', projectId], data);
    },
  });
}

export function useExecuteTestRun(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => executeTestRun(projectId),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['testing', 'suite', projectId] });
    },
  });
}

export function useCreateTestCase(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TestCaseInput) => createTestCase(projectId, data),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['testing', 'suite', projectId] });
    },
  });
}

export function useUpdateTestCase(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      caseId,
      data,
    }: {
      caseId: number;
      data: Partial<TestCaseInput> & { case_state?: CaseState };
    }) => updateTestCase(caseId, data),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['testing', 'suite', projectId] });
    },
  });
}

export function useDeleteTestCase(projectId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (caseId: number) => deleteTestCase(caseId),
    retry: false,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['testing', 'suite', projectId] });
    },
  });
}
