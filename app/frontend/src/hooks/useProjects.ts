import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createProject,
  deleteProject,
  fetchPipeline,
  fetchProjects,
  isTransientGatewayError,
  PIPELINE_RETRY_LIMIT,
  retryProject,
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
