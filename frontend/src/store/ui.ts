import { create } from 'zustand'

export type View = 'graph' | 'dashboard'
export interface Filters { cats: string[]; onlyErrors: boolean; onlyLoops: boolean; hideSpecial: boolean }

export interface UIState {
  selectedIdx: number | null
  range: [number, number] | null
  view: View
  filters: Filters
  compact: boolean | null // null = automático (compacto acima de 80 passos)
  expanded: string[] // grupos expandidos no modo compacto
  showGT: boolean
  inspectorWidth: number
  includeSpecial: boolean // dashboard: incluir message/keys
  select: (idx: number | null) => void
  setRange: (r: [number, number] | null) => void
  setView: (v: View) => void
  setFilters: (f: Partial<Filters>) => void
  setCompact: (c: boolean | null) => void
  toggleGroup: (key: string) => void
  setShowGT: (v: boolean) => void
  setInspectorWidth: (w: number) => void
  setIncludeSpecial: (v: boolean) => void
  reset: () => void
}

export const DEFAULT_FILTERS: Filters = { cats: [], onlyErrors: false, onlyLoops: false, hideSpecial: false }
const savedWidth = (() => { try { return Number(localStorage.getItem('trajviz-inspector-w')) || 400 } catch { return 400 } })()

export const useUI = create<UIState>((set) => ({
  selectedIdx: null,
  range: null,
  view: 'graph',
  filters: DEFAULT_FILTERS,
  compact: null,
  expanded: [],
  showGT: true,
  inspectorWidth: savedWidth,
  includeSpecial: false,
  select: (idx) => set({ selectedIdx: idx }),
  setRange: (range) => set({ range }),
  setView: (view) => set({ view }),
  setFilters: (f) => set((s) => ({ filters: { ...s.filters, ...f } })),
  setCompact: (compact) => set({ compact }),
  toggleGroup: (key) => set((s) => ({ expanded: s.expanded.includes(key) ? s.expanded.filter((k) => k !== key) : [...s.expanded, key] })),
  setShowGT: (showGT) => set({ showGT }),
  setInspectorWidth: (inspectorWidth) => {
    try { localStorage.setItem('trajviz-inspector-w', String(inspectorWidth)) } catch { /* sem storage */ }
    set({ inspectorWidth })
  },
  setIncludeSpecial: (includeSpecial) => set({ includeSpecial }),
  reset: () => set({ selectedIdx: null, range: null, view: 'graph', filters: DEFAULT_FILTERS, compact: null, expanded: [], showGT: true }),
}))

// ---- URL ⇄ store: /t/:id?step=42&view=graph&filter=error,cat:edit&range=10-30&compact=0&gt=0
export function toParams(s: Pick<UIState, 'selectedIdx' | 'range' | 'view' | 'filters' | 'compact' | 'showGT'>): URLSearchParams {
  const p = new URLSearchParams()
  if (s.selectedIdx != null) p.set('step', String(s.selectedIdx))
  if (s.view !== 'graph') p.set('view', s.view)
  const f: string[] = []
  if (s.filters.onlyErrors) f.push('error')
  if (s.filters.onlyLoops) f.push('loop')
  if (s.filters.hideSpecial) f.push('nospecial')
  s.filters.cats.forEach((c) => f.push(`cat:${c}`))
  if (f.length) p.set('filter', f.join(','))
  if (s.range) p.set('range', `${s.range[0]}-${s.range[1]}`)
  if (s.compact != null) p.set('compact', s.compact ? '1' : '0')
  if (!s.showGT) p.set('gt', '0')
  return p
}

export function fromParams(p: URLSearchParams): Partial<UIState> {
  const step = p.get('step')
  const range = p.get('range')?.match(/^(\d+)-(\d+)$/)
  const f = (p.get('filter') ?? '').split(',').filter(Boolean)
  const compact = p.get('compact')
  return {
    selectedIdx: step != null && /^\d+$/.test(step) ? Number(step) : null,
    range: range ? [Number(range[1]), Number(range[2])] : null,
    view: p.get('view') === 'dashboard' ? 'dashboard' : 'graph',
    filters: { onlyErrors: f.includes('error'), onlyLoops: f.includes('loop'), hideSpecial: f.includes('nospecial'),
      cats: f.filter((x) => x.startsWith('cat:')).map((x) => x.slice(4)) },
    compact: compact === '1' ? true : compact === '0' ? false : null,
    showGT: p.get('gt') !== '0',
  }
}
