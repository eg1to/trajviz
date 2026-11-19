import type { components } from './schema'

export type S = components['schemas']
export type Step = S['Step']
export type Trajectory = S['Trajectory']
export type TrajectoryResponse = S['TrajectoryResponse']
export type Metrics = S['Metrics']
export type LibraryItem = S['LibraryItem']
export type UploadResponse = S['UploadResponse']
export type TaxonomyResponse = S['TaxonomyResponse']
export type CorrectionResponse = S['CorrectionResponse']

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  code: string
  topKeys?: string[]
  constructor(status: number, code: string, message: string, topKeys?: string[]) {
    super(message)
    this.status = status
    this.code = code
    this.topKeys = topKeys
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = `Erro ${res.status} (${res.statusText})`
  let topKeys: string[] | undefined
  try {
    const body = await res.json()
    const d = body?.detail
    if (d && typeof d === 'object' && !Array.isArray(d) && d.message) {
      code = d.code ?? code
      message = d.message
      topKeys = d.top_keys
    } else if (Array.isArray(d)) {
      code = 'validation'
      message = d.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join('.')}: ${e.msg}`).join('; ')
    } else if (typeof d === 'string') message = d
  } catch { /* corpo não-JSON */ }
  return new ApiError(res.status, code, message, topKeys)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, init)
  } catch {
    throw new ApiError(0, 'network', `Não foi possível falar com a API em ${BASE}. O backend está rodando?`)
  }
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as T
}

const json = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export interface LibraryParams { dataset?: string; agent?: string; resolved?: boolean | null; q?: string }
export interface UploadParams { file: File; format?: string; row?: number; useLlm?: boolean }

export const api = {
  health: () => request<S['Health']>('/api/health'),
  taxonomy: () => request<TaxonomyResponse>('/api/taxonomy'),
  library: (p: LibraryParams = {}) => {
    const qs = new URLSearchParams()
    if (p.dataset) qs.set('dataset', p.dataset)
    if (p.agent) qs.set('agent', p.agent)
    if (p.resolved != null) qs.set('resolved', String(p.resolved))
    if (p.q) qs.set('q', p.q)
    return request<LibraryItem[]>(`/api/library?${qs}`)
  },
  openSample: (id: string, useLlm = false) => request<UploadResponse>(`/api/library/${id}/open?use_llm=${useLlm}`, { method: 'POST' }),
  upload: ({ file, format, row, useLlm }: UploadParams) => {
    const fd = new FormData()
    fd.append('file', file)
    if (format) fd.append('format', format)
    if (row != null && !Number.isNaN(row)) fd.append('row', String(row))
    fd.append('use_llm', String(!!useLlm))
    return request<UploadResponse>('/api/trajectories', { method: 'POST', body: fd })
  },
  trajectory: (id: string) => request<TrajectoryResponse>(`/api/trajectories/${id}`),
  step: (id: string, idx: number) => request<S['StepResponse']>(`/api/trajectories/${id}/steps/${idx}`),
  metrics: (id: string) => request<Metrics>(`/api/trajectories/${id}/metrics`),
  correct: (id: string, idx: number, category: Step['category'], note?: string) =>
    request<CorrectionResponse>(`/api/trajectories/${id}/steps/${idx}`, json('PATCH', { category, note })),
}
