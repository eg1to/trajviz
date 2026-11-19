import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Background, BackgroundVariant, Controls, MiniMap, ReactFlow, ReactFlowProvider, useReactFlow, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Download, Maximize } from 'lucide-react'
import { toast } from 'sonner'
import type { Metrics, Step, Trajectory } from '@/api/client'
import { Legend } from '@/components/Legend'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { COMPACT_THRESHOLD, buildGraph, itemFirstIdx, itemLastIdx, buildItems } from '@/lib/graph'
import { exportGraphPng } from '@/lib/export'
import { gtSets, outcomeOf, passesFilters } from '@/lib/steps'
import { KINDS, fill, kindOf } from '@/theme/categories'
import { useTheme } from '@/theme/useTheme'
import { useUI } from '@/store/ui'
import { edgeTypes, nodeTypes } from './nodes'

export function GraphTab(props: { id: string; trajectory: Trajectory; metrics: Metrics | undefined }) {
  return <ReactFlowProvider><GraphInner {...props} /></ReactFlowProvider>
}

function GraphInner({ id, trajectory, metrics }: { id: string; trajectory: Trajectory; metrics: Metrics | undefined }) {
  const steps = trajectory.steps ?? []
  const { dark } = useTheme()
  const ui = useUI()
  const rf = useReactFlow()
  const box = useRef<HTMLDivElement>(null)
  const compact = ui.compact ?? steps.length > COMPACT_THRESHOLD
  const gt = useMemo(() => gtSets(trajectory), [trajectory])
  const hasGT = gt.incorrect.size + gt.unuseful.size > 0
  const loops = metrics?.problems.loop_ranges ?? []
  const outcome = outcomeOf(trajectory)

  const graph = useMemo(() => buildGraph({ steps, filters: ui.filters, compact, expanded: ui.expanded, loops, gt, showGT: ui.showGT, outcome }),
    [steps, ui.filters, compact, ui.expanded, loops, gt, ui.showGT, outcome.label, outcome.tone]) // eslint-disable-line react-hooks/exhaustive-deps
  const visibleCount = useMemo(() => steps.filter((s) => passesFilters(s, ui.filters)).length, [steps, ui.filters])

  // seleção vinda de fora (faixa, inspetor, URL): expande o grupo que contém o passo e centraliza
  const lastSel = useRef<number | null>(null)
  useEffect(() => {
    const sel = ui.selectedIdx
    if (sel == null) { lastSel.current = null; return }
    const hidden = graph.nodes.find((n) => n.type === 'group' && (n.data.steps as Step[]).some((s) => s.idx === sel))
    if (hidden) { ui.toggleGroup(hidden.data.key as string); return }
    if (lastSel.current === sel) return
    const node = graph.nodes.find((n) => n.type === 'step' && (n.data.step as Step).idx === sel)
    if (!node) return
    lastSel.current = sel
    const z = Math.max(rf.getZoom(), 0.85)
    rf.setCenter(node.position.x + 72, node.position.y + 29, { zoom: z, duration: 250 })
  }, [ui.selectedIdx, graph.nodes]) // eslint-disable-line react-hooks/exhaustive-deps

  // intervalo selecionado na faixa → enquadra os nós
  useEffect(() => {
    if (!ui.range) return
    const [a, b] = ui.range
    const items = buildItems(steps.filter((s) => passesFilters(s, ui.filters)), compact, ui.expanded)
    const keys = new Set(items.filter((it) => itemLastIdx(it) >= a && itemFirstIdx(it) <= b).map((it) => it.key))
    const nodes = graph.nodes.filter((n) => keys.has(n.id))
    if (nodes.length) rf.fitView({ nodes, padding: 0.25, duration: 300, maxZoom: 1.3 })
  }, [ui.range]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { const t = setTimeout(() => rf.fitView({ padding: 0.1, duration: 0 }), 50); return () => clearTimeout(t) }, [id, compact]) // eslint-disable-line react-hooks/exhaustive-deps

  const onNodeClick = useCallback((_: unknown, n: Node) => { if (n.type === 'step') ui.select((n.data.step as Step).idx) }, [ui])
  const miniColor = useCallback((n: Node) => (n.type === 'step' ? fill(kindOf(n.data.step as Step), dark) : n.type === 'group' ? fill(n.data.kind as never, dark) : 'transparent'), [dark])
  const doExport = async () => {
    if (!box.current) return
    try { await exportGraphPng(box.current, graph.nodes, `grafo-${id}.png`) } catch (e) { toast.error(`Falha ao exportar PNG: ${(e as Error).message}`) }
  }

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="graph-tab">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b px-3 py-1.5 text-xs">
        <Legend showMarkers />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b px-3 py-1.5 text-xs">
        <Toggle label="só erros" checked={ui.filters.onlyErrors} onChange={(v) => ui.setFilters({ onlyErrors: v })} testid="f-errors" />
        <Toggle label="só loops / repetições" checked={ui.filters.onlyLoops} onChange={(v) => ui.setFilters({ onlyLoops: v })} testid="f-loops" />
        <Toggle label="esconder message / keys" checked={ui.filters.hideSpecial} onChange={(v) => ui.setFilters({ hideSpecial: v })} testid="f-special" />
        {hasGT && <Toggle label="gabarito" checked={ui.showGT} onChange={ui.setShowGT} testid="f-gt" />}
        <label className="flex items-center gap-1.5">modo
          <Select value={ui.compact == null ? 'auto' : ui.compact ? 'on' : 'off'} onValueChange={(v) => ui.setCompact(v === 'auto' ? null : v === 'on')}>
            <SelectTrigger className="h-7 w-48" data-testid="compact-select"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="auto">compacto (auto &gt; 80)</SelectItem><SelectItem value="on">compacto</SelectItem><SelectItem value="off">passo a passo</SelectItem></SelectContent>
          </Select>
        </label>
        {(ui.filters.cats.length > 0 || ui.filters.onlyErrors || ui.filters.onlyLoops || ui.filters.hideSpecial) &&
          <button className="text-primary hover:underline" onClick={() => ui.setFilters({ cats: [], onlyErrors: false, onlyLoops: false, hideSpecial: false })}>limpar filtros</button>}
        <span className="ml-auto text-muted-foreground" data-testid="visible-count">{visibleCount} de {steps.length} passos · {graph.nodes.filter((n) => n.type === 'step' || n.type === 'group').length} nós</span>
        <Button size="sm" variant="outline" onClick={() => rf.fitView({ padding: 0.1, duration: 250 })}><Maximize />Enquadrar</Button>
        <Button size="sm" variant="outline" onClick={doExport} data-testid="export-graph"><Download />Exportar PNG</Button>
      </div>
      <div ref={box} className="relative min-h-0 flex-1" data-testid="graph-canvas">
        {visibleCount === 0 ? <div className="flex h-full items-center justify-center text-muted-foreground" data-testid="graph-empty">Nenhum passo com esses filtros.</div> : (
          <ReactFlow nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onNodeClick={onNodeClick}
            nodesDraggable={false} nodesConnectable={false} edgesFocusable={false} minZoom={0.04} maxZoom={2} onlyRenderVisibleElements
            fitView fitViewOptions={{ padding: 0.1 }}>
            <Background variant={BackgroundVariant.Dots} gap={18} size={1} />
            <Controls showInteractive={false} data-no-export />
            <MiniMap pannable zoomable nodeColor={miniColor} nodeStrokeWidth={1} maskColor={dark ? 'rgba(0,0,0,0.5)' : 'rgba(240,240,240,0.6)'} data-no-export />
          </ReactFlow>
        )}
      </div>
    </div>
  )
}

function Toggle({ label, checked, onChange, testid }: { label: string; checked: boolean; onChange: (v: boolean) => void; testid: string }) {
  return <label className="flex cursor-pointer items-center gap-1.5"><Switch checked={checked} onCheckedChange={onChange} data-testid={testid} aria-label={label} />{label}</label>
}
export { KINDS }
