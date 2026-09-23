import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createProject,
  deleteProject,
  fetchPipeline,
  fetchProjects,
  retryProject,
} from '@/lib/projects';

const POLL_INTERVAL_MS = 1500;

export function useProjectList(enabled: boolean) {
  return useQuery({
    queryKey: ['generation', 'projects'],
    queryFn: fetchProjects,
    enabled,
    staleTime: 5_000,
  });
}

/** 项目流水线快照；运行中自动轮询，进入终态后停止。 */
export function useProjectPipeline(projectId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ['generation', 'pipeline', projectId],
    queryFn: () => fetchPipeline(projectId as number),
    enabled: enabled && projectId !== null,
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['generation', 'projects'] });
    },
  });
}

export function useRetryProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: number) => retryProject(projectId),
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['generation', 'projects'] });
    },
  });
}
