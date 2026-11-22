import { useEffect, useMemo, useRef } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { BarChart3, GitFork, Loader2, SearchX, ServerCrash } from 'lucide-react'
import { useMetrics, useTrajectory } from '@/api/hooks'
import { ApiError } from '@/api/client'
import { Inspector } from '@/components/Inspector'
import { PhaseStrip, type PhaseStripHandle } from '@/components/PhaseStrip'
import { TrajectoryHeader } from '@/components/TrajectoryHeader'
import { GraphTab } from '@/components/graph/GraphTab'
import { DashboardTab } from '@/components/dashboard/DashboardTab'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { exportElementPng } from '@/lib/export'
import { gtSets, stepsOf } from '@/lib/steps'
import { fromParams, toParams, useUI } from '@/store/ui'
import { Link } from 'react-router-dom'

/** Estado (passo, aba, filtros, intervalo) ⇄ URL: /t/:id?step=42&view=graph&filter=error */
function useUrlSync(ready: boolean) {
  const [params, setParams] = useSearchParams()
  const ui = useUI()
  const hydrated = useRef(false)
  const last = useRef('')
  useEffect(() => { // URL → store (montagem e navegação externa)
    if (params.toString() === last.current && hydrated.current) return
    useUI.setState({ ...fromParams(params) })
    last.current = params.toString()
    hydrated.current = true
  }, [params])
  useEffect(() => { // store → URL
    if (!hydrated.current || !ready) return
    const next = toParams(ui).toString()
    if (next !== params.toString()) { last.current = next; setParams(new URLSearchParams(next), { replace: true }) }
  }, [ui.selectedIdx, ui.range, ui.view, ui.filters, ui.compact, ui.showGT, ready]) // eslint-disable-line react-hooks/exhaustive-deps
}

function useKeys(n: number) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t && (['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName) || t.isContentEditable || t.closest('[role=listbox]'))) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const { selectedIdx, select } = useUI.getState()
      const go = (d: number) => { e.preventDefault(); select(Math.max(0, Math.min(n - 1, (selectedIdx ?? (d > 0 ? -1 : n)) + d))) }
      if (e.key === 'j' || e.key === 'ArrowRight') go(1)
      else if (e.key === 'k' || e.key === 'ArrowLeft') go(-1)
      else if (e.key === 'Escape') select(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [n])
}

export default function TrajectoryPage() {
  const { id = '' } = useParams()
  const traj = useTrajectory(id)
  const metrics = useMetrics(id)
  const view = useUI((s) => s.view)
  const setView = useUI((s) => s.setView)
  const strip = useRef<PhaseStripHandle>(null)
  const steps = useMemo(() => stepsOf(traj.data?.trajectory), [traj.data])
  const gt = useMemo(() => gtSets(traj.data?.trajectory), [traj.data])
  useUrlSync(!!traj.data)
  useKeys(steps.length)
  useEffect(() => { if (document.title && traj.data) document.title = `${traj.data.trajectory.task_id ?? id} — trajviz` }, [traj.data, id])

  if (traj.isLoading) return <Centered><Loader2 className="size-6 animate-spin" /><p>Carregando trajetória…</p></Centered>
  if (traj.error || !traj.data) {
    const err = traj.error instanceof ApiError ? traj.error : null
    const notFound = err?.status === 404
    const network = err?.status === 0
    return <Centered data-testid={notFound ? 'not-found' : network ? 'network-error' : 'load-error'}>
      {network ? <ServerCrash className="size-7" /> : <SearchX className="size-7" />}
      <p className="font-medium text-foreground">{notFound ? 'Trajetória não encontrada — reabra pela biblioteca' : network ? 'API indisponível' : 'Não foi possível carregar a trajetória'}</p>
      <p className="max-w-md text-center text-xs">{notFound ? 'O link aponta para uma trajetória que não está mais processada (cache limpo ou regras atualizadas). Abra a amostra de novo pela biblioteca ou reenvie o arquivo; o id continua o mesmo.' : err?.message ?? (traj.error as Error | null)?.message}</p>
      <div className="flex gap-2">{network && <Button variant="outline" onClick={() => traj.refetch()}>Tentar de novo</Button>}<Button asChild variant="outline"><Link to="/">Voltar à biblioteca</Link></Button></div></Centered>
  }
  const loops = metrics.data?.problems.loop_ranges ?? []
  const ark = traj.data.trajectory.meta?.ark as { unrecorded_note?: string; unrecorded?: number[] } | undefined  // aviso do backend (Ark não registra a saída de leituras)
  const unrecorded = ark?.unrecorded_note && ark.unrecorded ? { note: ark.unrecorded_note, idx: ark.unrecorded } : null

  return (
    <div className="flex h-full flex-col">
      <TrajectoryHeader data={traj.data} metrics={metrics.data} onExportStrip={async () => { if (strip.current?.element) await exportElementPng(strip.current.element, `faixa-${id}.png`) }} />
      <div className="border-b bg-card px-3 py-2">
        <PhaseStrip ref={strip} steps={steps} loops={loops} gt={gt} />
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <Tabs value={view} onValueChange={(v) => setView(v as 'graph' | 'dashboard')} className="border-b bg-card px-3 py-1.5">
            <TabsList><TabsTrigger value="graph" data-testid="tab-graph"><GitFork className="size-3.5" />Grafo</TabsTrigger><TabsTrigger value="dashboard" data-testid="tab-dashboard"><BarChart3 className="size-3.5" />Dashboard</TabsTrigger></TabsList>
          </Tabs>
          <div className="min-h-0 flex-1">
            {view === 'graph' ? <GraphTab id={id} trajectory={traj.data.trajectory} metrics={metrics.data} />
              : <DashboardTab id={id} trajectory={traj.data.trajectory} metrics={metrics.data} loading={metrics.isLoading} />}
          </div>
        </div>
        <Inspector id={id} steps={steps} gt={gt} unrecorded={unrecorded} />
      </div>
    </div>
  )
}

function Centered({ children, ...p }: { children: React.ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground" {...p}>{children}</div>
}
