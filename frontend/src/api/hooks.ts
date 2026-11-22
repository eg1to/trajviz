import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type LibraryParams, type Metrics, type Step, type TrajectoryResponse, type UploadParams } from './client'

export const qk = {
  taxonomy: ['taxonomy'] as const,
  library: (p: LibraryParams) => ['library', p] as const,
  trajectory: (id: string) => ['trajectory', id] as const,
  metrics: (id: string) => ['metrics', id] as const,
  step: (id: string, idx: number) => ['step', id, idx] as const,
}

export const useTaxonomy = () => useQuery({ queryKey: qk.taxonomy, queryFn: api.taxonomy, staleTime: Infinity })
export const useLibrary = (p: LibraryParams) =>
  useQuery({ queryKey: qk.library(p), queryFn: () => api.library(p), placeholderData: keepPreviousData, retry: 1 })
export const useTrajectory = (id: string) => useQuery({ queryKey: qk.trajectory(id), queryFn: () => api.trajectory(id), staleTime: Infinity, retry: false })
export const useMetrics = (id: string) => useQuery({ queryKey: qk.metrics(id), queryFn: () => api.metrics(id), staleTime: Infinity, retry: false })
export const useFullStep = (id: string, idx: number | null, enabled: boolean) =>
  useQuery({ queryKey: qk.step(id, idx ?? -1), queryFn: () => api.step(id, idx as number), enabled: enabled && idx != null, staleTime: Infinity })

export const useUpload = () => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: (p: UploadParams) => api.upload(p), onSuccess: () => qc.invalidateQueries({ queryKey: ['library'] }) })
}
export const useOpenSample = () => {
  const qc = useQueryClient()
  return useMutation({ mutationFn: ({ id, useLlm }: { id: string; useLlm?: boolean }) => api.openSample(id, useLlm), onSuccess: () => qc.invalidateQueries({ queryKey: ['library'] }) })
}

/** Corrige o rótulo e atualiza grafo/faixa/dashboard sem recarregar (cache local + métricas vindas do servidor). */
export const useCorrect = (id: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ idx, category }: { idx: number; category: Step['category'] }) => api.correct(id, idx, category),
    onSuccess: (res, { idx }) => {
      qc.setQueryData<TrajectoryResponse>(qk.trajectory(id), (old) => {
        if (!old) return old
        const steps = (old.trajectory.steps ?? []).map((s) => (s.idx === idx ? { ...res.step, observation: s.observation } : s))
        return { ...old, trajectory: { ...old.trajectory, steps } }
      })
      qc.setQueryData<Metrics>(qk.metrics(id), res.metrics)
      qc.invalidateQueries({ queryKey: ['step', id, idx] })
    },
  })
}
