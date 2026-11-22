import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, ChevronLeft, ChevronRight, FileEdit, FileSearch, Loader2, Play } from 'lucide-react'
import { useCorrect, useFullStep, useTaxonomy } from '@/api/hooks'
import type { Step } from '@/api/client'
import { CodeBlock, DiffBlock, type Lang } from '@/components/CodeBlock'
import { KindChip } from '@/components/Legend'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { flagsOf, type GTSets } from '@/lib/steps'
import { useUI } from '@/store/ui'
import { ERROR_COLOR, kindOf } from '@/theme/categories'
import { cn, fmtInt } from '@/lib/utils'

const THOUGHT_SRC: Record<string, string> = { content: 'mensagem do agente', think_tool: 'ferramenta think', field: 'campo thought', analysis_plan: 'analysis + plan' }
const SRC_LABEL: Record<string, [string, 'default' | 'ok' | 'warn' | 'muted']> = { rule: ['regra', 'default'], llm: ['LLM', 'ok'], user: ['usuário', 'ok'], fallback: ['palpite (baixa confiança)', 'warn'] }
const FLAG_LABEL: Record<string, string> = { error: 'erro', test_fail: 'teste falhou', test_pass: 'teste passou', repeated: 'repetido', no_new_info: 'sem informação nova', loop: 'loop', truncated: 'truncada' }
const FILE_ICON = { read: FileSearch, edit: FileEdit, run: Play }
const MODE_LABEL = { read: 'lido', edit: 'editado', run: 'executado' }

export function useResizable() {
  const width = useUI((s) => s.inspectorWidth)
  const setWidth = useUI((s) => s.setInspectorWidth)
  const dragging = useRef(false)
  const onDown = useCallback((e: React.PointerEvent) => { dragging.current = true; (e.target as HTMLElement).setPointerCapture(e.pointerId) }, [])
  const onMove = useCallback((e: React.PointerEvent) => { if (dragging.current) setWidth(Math.max(300, Math.min(760, window.innerWidth - e.clientX))) }, [setWidth])
  const onUp = useCallback(() => { dragging.current = false }, [])
  return { width, handleProps: { onPointerDown: onDown, onPointerMove: onMove, onPointerUp: onUp } }
}

function actionView(step: Step): { lang: Lang; code: string; diff?: { o: string; n: string } } {
  const a = step.action
  const args = (a.args ?? {}) as Record<string, unknown>
  if (a.tool === 'bash' || a.tool === 'keys') return { lang: 'bash', code: a.command ?? a.raw ?? '' }
  if (a.tool === 'ipython') return { lang: 'python', code: a.command ?? a.raw ?? '' }
  if (a.tool === 'editor') {
    if (a.command === 'str_replace' && typeof args.old_str === 'string') return { lang: 'diff', code: '', diff: { o: String(args.old_str), n: String(args.new_str ?? '') } }
    if (a.command === 'create' && typeof args.file_text === 'string') return { lang: String(args.path ?? '').endsWith('.py') ? 'python' : 'plain', code: args.file_text }
    if (a.command === 'insert') return { lang: 'plain', code: `insert @ linha ${String(args.insert_line ?? '?')}\n${String(args.new_str ?? '')}` }
    return { lang: 'bash', code: `${a.command ?? 'view'} ${String(args.path ?? '')}${args.view_range ? ` --view_range ${JSON.stringify(args.view_range)}` : ''}` }
  }
  return { lang: 'plain', code: a.raw || JSON.stringify(args, null, 1) }
}

export type Unrecorded = { note: string; idx: number[] }

export function Inspector({ id, steps, gt, unrecorded }: { id: string; steps: Step[]; gt: GTSets; unrecorded?: Unrecorded | null }) {
  const selected = useUI((s) => s.selectedIdx)
  const select = useUI((s) => s.select)
  const { width, handleProps } = useResizable()
  const step = selected != null ? steps[selected] : undefined
  return (
    <aside className="relative flex shrink-0 flex-col border-l bg-card" style={{ width }} data-testid="inspector" aria-label="Inspetor de passo">
      <div {...handleProps} className="absolute -left-1 top-0 z-10 h-full w-2 cursor-col-resize hover:bg-primary/30" role="separator" aria-orientation="vertical" aria-label="Redimensionar inspetor" />
      {step ? <StepDetail key={step.idx} id={id} step={step} total={steps.length} gt={gt} onNav={(d) => select(Math.max(0, Math.min(steps.length - 1, step.idx + d)))} onJump={select} steps={steps} unrecorded={unrecorded} />
        : <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-muted-foreground" data-testid="inspector-empty">
          <FileSearch className="size-6" /><p className="font-medium text-foreground">Nenhum passo selecionado</p>
          <p className="text-xs">Clique num passo da faixa de fases ou do grafo. Atalhos: <kbd className="mono rounded border px-1">j</kbd>/<kbd className="mono rounded border px-1">k</kbd> ou ← → navegam.</p></div>}
    </aside>
  )
}

function StepDetail({ id, step, total, gt, onNav, onJump, steps, unrecorded }: { id: string; step: Step; total: number; gt: GTSets; onNav: (d: number) => void; onJump: (i: number) => void; steps: Step[]; unrecorded?: Unrecorded | null }) {
  const tax = useTaxonomy()
  const correct = useCorrect(id)
  const [full, setFull] = useState(false)
  const [showAllObs, setShowAllObs] = useState(false)
  const fullQ = useFullStep(id, step.idx, full)
  const obs = (full && fullQ.data ? fullQ.data.step.observation : step.observation) ?? null
  const av = actionView(step)
  const kind = kindOf(step)
  const flags = flagsOf(step)
  const [srcLabel, srcTone] = SRC_LABEL[step.label_source] ?? [step.label_source, 'muted' as const]
  useEffect(() => { setFull(false); setShowAllObs(false) }, [step.idx])
  const content = obs?.content ?? ''
  const LIMIT = 700
  const shown = showAllObs || content.length <= LIMIT ? content : content.slice(0, LIMIT) + '…'
  const errorCls = flags.includes('error') ? { borderColor: ERROR_COLOR } : undefined

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <Button variant="ghost" size="icon" onClick={() => onNav(-1)} disabled={step.idx === 0} aria-label="Passo anterior"><ChevronLeft /></Button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5"><span className="text-sm font-semibold tabular-nums" data-testid="inspector-idx">Passo #{step.idx}</span><span className="text-xs text-muted-foreground" data-testid="inspector-ordinal">· {step.idx + 1}º de {total}</span>
            <KindChip kind={kind} /></div>
          <div className="mono truncate text-muted-foreground">{step.action.tool_native ?? step.action.tool}{step.action.command && step.action.tool === 'editor' ? ` · ${step.action.command}` : ''}{step.native_id != null ? ` · id ${String(step.native_id).slice(0, 18)}` : ''}</div>
        </div>
        <Button variant="ghost" size="icon" onClick={() => onNav(1)} disabled={step.idx >= total - 1} aria-label="Próximo passo"><ChevronRight /></Button>
      </div>
      <div className="scroll-thin flex-1 space-y-3 overflow-auto p-3">
        {/* rótulo */}
        <Section title="Rótulo">
          <div className="flex flex-wrap items-center gap-2">
            <Select value={step.category} onValueChange={(v) => correct.mutate({ idx: step.idx, category: v as Step['category'] })} disabled={correct.isPending}>
              <SelectTrigger className="h-7 w-44" data-testid="label-select" aria-label="Corrigir categoria"><SelectValue /></SelectTrigger>
              <SelectContent>{(tax.data?.categories ?? []).map((c) => <SelectItem key={c.id} value={c.id} hint={c.phase}>{c.label}</SelectItem>)}</SelectContent>
            </Select>
            {correct.isPending && <Loader2 className="size-3.5 animate-spin" />}
            <Badge tone={srcTone} data-testid="label-source">{srcLabel}</Badge>
            {step.subcategory && <Badge tone="muted" className="mono">{step.subcategory}</Badge>}
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">
            <span>confiança</span><div className="h-1.5 w-24 rounded bg-muted"><div className="h-1.5 rounded bg-primary" style={{ width: `${Math.round(step.confidence * 100)}%` }} /></div><span className="tabular-nums">{Math.round(step.confidence * 100)}%</span>
            {step.label_source === 'user' && <span className="text-ok">corrigido por você</span>}
          </div>
          {(gt.incorrect.has(step.idx) || gt.unuseful.has(step.idx)) && (
            <div className="mt-1.5 flex gap-1.5">{gt.incorrect.has(step.idx) && <Badge tone="danger">gabarito: incorreto</Badge>}{gt.unuseful.has(step.idx) && <Badge tone="muted">gabarito: inútil</Badge>}</div>)}
        </Section>

        {flags.length > 0 && (
          <Section title="Flags">
            <ul className="space-y-1" data-testid="flags">
              {flags.map((f) => {
                const ref = (step.flag_refs ?? {})[f]
                const bad = f === 'error' || f === 'test_fail' || f === 'loop'
                return (
                  <li key={f} className="flex items-start gap-1.5 text-xs">
                    <Badge tone={f === 'test_pass' ? 'ok' : bad ? 'danger' : 'warn'}>{f === 'error' ? '✕ ' : f === 'test_pass' ? '✓ ' : ''}{FLAG_LABEL[f] ?? f}</Badge>
                    <span className="text-muted-foreground">{String((step.flag_details ?? {})[f] ?? '')}</span>
                    {ref != null && steps[ref] && <button className="inline-flex items-center gap-0.5 font-medium text-primary hover:underline" onClick={() => onJump(ref)} data-testid="flag-ref">ir ao #{ref}<ArrowRight className="size-3" /></button>}
                  </li>
                )
              })}
            </ul>
          </Section>
        )}

        <Section title="Pensamento" hint={step.thought_source ? THOUGHT_SRC[step.thought_source] : undefined}>
          {step.thought ? <p className="whitespace-pre-wrap break-words text-[13px]" data-testid="thought">{step.thought}</p> : <p className="text-xs italic text-muted-foreground">sem pensamento neste passo</p>}
        </Section>

        <Section title="Ação" hint={step.action.tool_native ?? step.action.tool}>
          {av.diff ? <DiffBlock oldStr={av.diff.o} newStr={av.diff.n} /> : <CodeBlock code={av.code || '(vazio)'} language={av.lang} />}
        </Section>

        <Section title="Observação" hint={obs ? `${fmtInt(obs.chars)} chars${obs.truncated ? ' · truncada pela ferramenta' : ''}` : undefined}>
          {obs ? (
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-1.5">
                {obs.exit_code != null && <Badge tone={obs.exit_code === 0 ? 'ok' : 'danger'} data-testid="exit-code">exit code {obs.exit_code}</Badge>}
                {obs.exit_code == null && <Badge tone="muted">sem exit code</Badge>}
                {(flagsOf(step).includes('error')) && <span style={errorCls} className="rounded border px-1 text-[11px] font-semibold text-danger">erro</span>}
              </div>
              <pre className={cn('mono scroll-thin overflow-auto whitespace-pre-wrap break-words rounded border bg-code p-2')} style={{ maxHeight: showAllObs || full ? 420 : 220 }} data-testid="observation">{shown || '(vazia)'}</pre>
              <div className="flex gap-2">
                {content.length > LIMIT && !showAllObs && <Button size="sm" variant="outline" onClick={() => setShowAllObs(true)}>mostrar mais</Button>}
                {showAllObs && content.length > LIMIT && <Button size="sm" variant="ghost" onClick={() => setShowAllObs(false)}>recolher</Button>}
                {obs.content_cut && !full && <Button size="sm" variant="outline" onClick={() => setFull(true)} data-testid="see-full">ver completa ({fmtInt(obs.chars)} chars)</Button>}
                {full && fullQ.isLoading && <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><Loader2 className="size-3 animate-spin" />carregando…</span>}
              </div>
            </div>
          ) : unrecorded?.idx.includes(step.idx)
            ? <p className="text-xs italic text-muted-foreground" data-testid="observation-unrecorded">{unrecorded.note}</p>
            : <p className="text-xs italic text-muted-foreground">sem observação (ação final ou trajetória cortada)</p>}
        </Section>

        {(step.files ?? []).length > 0 && (
          <Section title="Arquivos">
            <ul className="space-y-0.5" data-testid="step-files">
              {(step.files ?? []).map((f, i) => { const Icon = FILE_ICON[f.mode]; return <li key={i} className="flex items-center gap-1.5 text-xs"><Icon className="size-3 text-muted-foreground" /><span className="mono truncate" title={f.path}>{f.path}</span><Badge tone="muted">{MODE_LABEL[f.mode]}</Badge></li> })}
            </ul>
          </Section>
        )}
      </div>
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-1 flex items-baseline gap-2"><h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>{hint && <span className="text-[11px] text-muted-foreground">· {hint}</span>}</div>
      {children}
    </section>
  )
}
