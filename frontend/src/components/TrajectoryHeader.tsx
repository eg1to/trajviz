import { Link } from 'react-router-dom'
import { ArrowLeft, Download, Info } from 'lucide-react'
import { toast } from 'sonner'
import type { Metrics, TrajectoryResponse } from '@/api/client'
import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tip } from '@/components/ui/tooltip'
import { displayTitle, outcomeOf } from '@/lib/steps'
import { fmtInt } from '@/lib/utils'

export function TrajectoryHeader({ data, metrics, onExportStrip }: { data: TrajectoryResponse; metrics?: Metrics; onExportStrip: () => Promise<void> }) {
  const t = data.trajectory
  const oc = outcomeOf(t)
  const title = displayTitle(t.task_id, data.source_filename, t.problem_statement, t.id)
  const origin = (t.meta?.origin as string | undefined) ?? undefined
  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b bg-card px-3 py-2" data-testid="traj-header">
      <Link to="/" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground" aria-label="Voltar à biblioteca"><ArrowLeft className="size-3.5" /></Link>
      <Logo />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold" title={title} data-testid="traj-title">{title}</div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          <span>{t.agent ?? 'agente ?'}</span><span>{t.model ?? 'modelo ?'}</span>
          <span>{(t.source_format ?? '').replace(/^ctb_/, 'CTB · ')}{origin ? ` · ${origin}` : ''}</span>
          <span><b className="text-foreground tabular-nums" data-testid="n-steps">{fmtInt((t.steps ?? []).length)}</b> passos</span>
          {metrics && <span>{metrics.outcome.ended_with_submit ? 'terminou em submit' : 'sem submit final'}</span>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {oc.label === 'não validado'
          ? <Tip content="O resolved e o patch do SWE-smith não batem com a trajetória (em ~83% das linhas, o patch nem cita arquivos vistos pelo agente): não use o desfecho como verdade."><Badge tone="warn" className="cursor-help px-2 py-0.5 text-xs" data-testid="outcome-badge">não validado</Badge></Tip>
          : <Badge tone={oc.tone} className="px-2 py-0.5 text-xs" data-testid="outcome-badge">{oc.label === 'PASS' ? '✓ PASS' : oc.label === 'FAIL' ? '✕ FAIL' : oc.label}</Badge>}
        <Tip content={<div>Formato detectado automaticamente: <b>{data.format_detected}</b> ({Math.round(data.confidence * 100)}% de confiança){data.llm_used ? ' · LLM usado' : ''}.{data.warnings.length > 0 && <ul className="mt-1 list-disc pl-4">{data.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}</div>}>
          <Badge tone={data.warnings.length ? 'warn' : 'muted'} className="cursor-help" data-testid="format-badge"><Info className="size-3" />{data.format_detected} · {Math.round(data.confidence * 100)}%{data.warnings.length ? ` · ${data.warnings.length} aviso${data.warnings.length > 1 ? 's' : ''}` : ''}</Badge>
        </Tip>
        <Button size="sm" variant="outline" onClick={() => onExportStrip().catch((e) => toast.error(`Falha ao exportar PNG: ${(e as Error).message}`))} data-testid="export-strip"><Download />Faixa PNG</Button>
        <ThemeToggle />
      </div>
    </header>
  )
}
