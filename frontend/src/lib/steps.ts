import type { Step, Trajectory } from '@/api/client'
import { kindOf, type Kind } from '@/theme/categories'
import { truncate } from './utils'
import type { Filters } from '@/store/ui'

export const stepsOf = (t: Trajectory | undefined): Step[] => t?.steps ?? []
export const flagsOf = (s: Step) => s.flags ?? []
export const hasFlag = (s: Step, f: string) => flagsOf(s).some((x) => x === f)

/** Texto curto da ação (para nós, tooltips e listas). */
export function commandShort(s: Step, n = 40): string {
  const a = s.action
  if (a.tool === 'editor') {
    const p = typeof a.args?.path === 'string' ? a.args.path.split('/').slice(-2).join('/') : ''
    return truncate(`${a.command ?? 'editor'} ${p}`, n)
  }
  if (a.tool === 'think') return 'think'
  if (a.tool === 'message') return truncate(s.thought ?? 'mensagem', n)
  if (a.tool === 'submit') return truncate(a.tool_native ?? 'submit', n)
  if (a.tool === 'task_tracker') return 'task_tracker'
  return truncate(s.summary ?? a.command ?? a.raw ?? a.tool, n) // summary = segmento que definiu a categoria (sem cd/env/caminhos do repo)
}

export function kindLabelOfStep(s: Step): Kind {
  return kindOf(s)
}

/** Passo passa nos filtros? (cats usa o "tipo" visual: categorias + message/keys/harness) */
export function passesFilters(s: Step, f: Filters): boolean {
  const k = kindOf(s)
  if (f.hideSpecial && (k === 'message' || k === 'keys' || k === 'harness_protocol')) return false
  if (f.cats.length && !f.cats.includes(k)) return false
  if (f.onlyErrors || f.onlyLoops) {
    const e = f.onlyErrors && hasFlag(s, 'error')
    const l = f.onlyLoops && (hasFlag(s, 'loop') || hasFlag(s, 'repeated') || hasFlag(s, 'no_new_info'))
    if (!e && !l) return false
  }
  return true
}

export const filtersActive = (f: Filters) => f.cats.length > 0 || f.onlyErrors || f.onlyLoops || f.hideSpecial

export interface GTSets { incorrect: Set<number>; unuseful: Set<number> }
export function gtSets(t: Trajectory | undefined): GTSets {
  const out: GTSets = { incorrect: new Set(), unuseful: new Set() }
  for (const a of t?.ground_truth?.annotations ?? [])
    for (const s of a.steps ?? []) {
      if (s.resolved_idx == null) continue
      if ((s.labels ?? []).includes('incorrect')) out.incorrect.add(s.resolved_idx)
      if ((s.labels ?? []).includes('unuseful')) out.unuseful.add(s.resolved_idx)
    }
  return out
}

export function outcomeOf(t: Trajectory | undefined): { label: 'PASS' | 'FAIL' | 'não validado' | 'sem dado'; tone: 'ok' | 'danger' | 'warn' | 'muted' } {
  if (!t) return { label: 'sem dado', tone: 'muted' }
  if (t.resolved == null) return { label: 'sem dado', tone: 'muted' }
  if (t.resolved_validated === false) return { label: 'não validado', tone: 'warn' }
  return t.resolved ? { label: 'PASS', tone: 'ok' } : { label: 'FAIL', tone: 'danger' }
}

/** Número do passo relacionado a uma flag (repeated/no_new_info → passo original). */
export const flagRef = (s: Step, f: string): number | undefined => (s.flag_refs ?? {})[f]
