// Constrói nós/arestas do grafo a partir dos passos já rotulados pela API (sem lógica de rotulação aqui: só layout e agrupamento visual).
import type { Edge, Node } from '@xyflow/react'
import type { Step } from '@/api/client'
import { kindOf, type Kind } from '@/theme/categories'
import type { Filters } from '@/store/ui'
import { flagRef, flagsOf, passesFilters, type GTSets } from './steps'

export const NODE_W = 144
export const NODE_H = 58
export const GAP_X = 26
export const GAP_Y = 96
export const ROW = 12
export const COMPACT_THRESHOLD = 80

export interface LoopRange { kind: string; range: number[]; detail: string }

export type Item =
  | { type: 'step'; key: string; step: Step }
  | { type: 'group'; key: string; kind: Kind; steps: Step[] }

/** Agrupa passos consecutivos da mesma categoria (modo compacto); grupos expandidos viram passos soltos. */
export function buildItems(steps: Step[], compact: boolean, expanded: string[]): Item[] {
  if (!compact) return steps.map((s) => ({ type: 'step', key: `s${s.idx}`, step: s }))
  const out: Item[] = []
  let run: Step[] = []
  const flush = () => {
    if (!run.length) return
    const key = `g${run[0].idx}`
    if (run.length === 1 || expanded.includes(key)) run.forEach((s) => out.push({ type: 'step', key: `s${s.idx}`, step: s }))
    else out.push({ type: 'group', key, kind: kindOf(run[0]), steps: run })
    run = []
  }
  for (const s of steps) {
    if (run.length && kindOf(run[0]) !== kindOf(s)) flush()
    run.push(s)
  }
  flush()
  return out
}

export const itemFirstIdx = (it: Item) => (it.type === 'step' ? it.step.idx : it.steps[0].idx)
export const itemLastIdx = (it: Item) => (it.type === 'step' ? it.step.idx : it.steps[it.steps.length - 1].idx)

export interface GraphModel { nodes: Node[]; edges: Edge[]; width: number; height: number }

export function buildGraph(opts: {
  steps: Step[]; filters: Filters; compact: boolean; expanded: string[]; loops: LoopRange[]; gt: GTSets; showGT: boolean;
  outcome: { label: string; tone: string }
}): GraphModel {
  const visible = opts.steps.filter((s) => passesFilters(s, opts.filters))
  const items = buildItems(visible, opts.compact, opts.expanded)
  const nodes: Node[] = []
  const edges: Edge[] = []
  const pos = (i: number) => ({ x: (i % ROW) * (NODE_W + GAP_X), y: Math.floor(i / ROW) * (NODE_H + GAP_Y) })
  const nodeOfIdx = new Map<number, string>() // idx do passo → id do nó que o contém
  items.forEach((it, i) => {
    const p = pos(i)
    if (it.type === 'step') {
      nodes.push({ id: it.key, type: 'step', position: p, data: { step: it.step, gtIncorrect: opts.showGT && opts.gt.incorrect.has(it.step.idx), gtUnuseful: opts.showGT && opts.gt.unuseful.has(it.step.idx) }, draggable: false, width: NODE_W, height: NODE_H })
      nodeOfIdx.set(it.step.idx, it.key)
    } else {
      nodes.push({ id: it.key, type: 'group', position: p, data: { kind: it.kind, steps: it.steps, key: it.key,
        gtIncorrect: opts.showGT && it.steps.some((s) => opts.gt.incorrect.has(s.idx)), gtUnuseful: opts.showGT && it.steps.some((s) => opts.gt.unuseful.has(s.idx)) }, draggable: false, width: NODE_W, height: NODE_H })
      it.steps.forEach((s) => nodeOfIdx.set(s.idx, it.key))
    }
  })
  // nó final (PASS / FAIL / não validado)
  const endI = items.length
  nodes.push({ id: 'end', type: 'outcome', position: pos(endI), data: { label: opts.outcome.label, tone: opts.outcome.tone }, draggable: false, selectable: false, width: NODE_W, height: NODE_H })
  // arestas cronológicas
  const ids = [...items.map((i) => i.key), 'end']
  for (let i = 0; i + 1 < ids.length; i++) {
    const wrap = Math.floor(i / ROW) !== Math.floor((i + 1) / ROW)
    edges.push(wrap
      ? { id: `c${i}`, source: ids[i], target: ids[i + 1], sourceHandle: 'bs', targetHandle: 'tt', type: 'smoothstep', className: 'chrono', style: { strokeWidth: 1, opacity: 0.45 }, selectable: false }
      : { id: `c${i}`, source: ids[i], target: ids[i + 1], sourceHandle: 'r', targetHandle: 'l', type: 'straight', className: 'chrono', style: { strokeWidth: 1, opacity: 0.45 }, selectable: false })
  }
  // arestas de retorno: repeated / no_new_info → passo original
  for (const s of visible) {
    for (const f of ['repeated', 'no_new_info'] as const) {
      const ref = flagRef(s, f)
      if (!flagsOf(s).includes(f) || ref == null) continue
      const a = nodeOfIdx.get(s.idx), b = nodeOfIdx.get(ref)
      if (!a || !b || a === b) continue
      edges.push({ id: `r${s.idx}-${f}`, source: a, target: b, sourceHandle: 'ts', targetHandle: 'tt', type: 'return', data: { flag: f }, selectable: false })
    }
  }
  // arcos de loop: um por trecho de linha coberto pelo intervalo
  opts.loops.forEach((lp, li) => {
    const [a, b] = lp.range
    const idxs = items.map((it, i) => ({ i, first: itemFirstIdx(it), last: itemLastIdx(it) })).filter((x) => x.last >= a && x.first <= b)
    const byRow = new Map<number, number[]>()
    idxs.forEach((x) => { const r = Math.floor(x.i / ROW); byRow.set(r, [...(byRow.get(r) ?? []), x.i]) })
    byRow.forEach((is, row) => {
      const c0 = Math.min(...is) % ROW, c1 = Math.max(...is) % ROW
      nodes.push({ id: `loop-${li}-${row}`, type: 'loopArc', position: { x: c0 * (NODE_W + GAP_X) - 6, y: row * (NODE_H + GAP_Y) - 30 },
        data: { label: lp.kind === 'ngram' ? 'loop' : 'loop edit→test', detail: lp.detail, w: (c1 - c0 + 1) * (NODE_W + GAP_X) - GAP_X + 12 },
        draggable: false, selectable: false, focusable: false, zIndex: -1, style: { pointerEvents: 'none' }, width: (c1 - c0 + 1) * (NODE_W + GAP_X) - GAP_X + 12, height: 26 })
    })
  })
  const rows = Math.ceil((items.length + 1) / ROW)
  return { nodes, edges, width: Math.min(items.length + 1, ROW) * (NODE_W + GAP_X), height: rows * (NODE_H + GAP_Y) }
}
