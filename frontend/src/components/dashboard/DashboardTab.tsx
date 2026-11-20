import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend as RLegend, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Loader2 } from 'lucide-react'
import type { Metrics, Trajectory } from '@/api/client'
import { DashCard } from './DashCard'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { CATEGORY_ORDER, ERROR_COLOR, KINDS, PHASES, PHASE_COLOR, type Kind } from '@/theme/categories'
import { outcomeOf } from '@/lib/steps'
import { fmtInt, fmtPct, cn, roundTicks } from '@/lib/utils'
import { useUI } from '@/store/ui'
import { useTheme } from '@/theme/useTheme'

const SPECIAL = ['message', 'keys', 'harness_protocol'] as const
const AXIS = { fontSize: 11, fill: 'var(--muted-foreground)' }

function useGoStep() {
  const select = useUI((s) => s.select)
  const setView = useUI((s) => s.setView)
  return (idx: number) => { select(idx); setView('graph') }
}

export function DashboardTab({ id, trajectory, metrics, loading }: { id: string; trajectory: Trajectory; metrics: Metrics | undefined; loading: boolean }) {
  if (loading || !metrics) return <div className="flex h-full items-center justify-center text-muted-foreground"><Loader2 className="mr-2 size-5 animate-spin" />Calculando métricas…</div>
  const m = metrics
  return (
    <div className="scroll-thin h-full overflow-auto p-3" data-testid="dashboard-tab">
      <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-2 2xl:grid-cols-3">
        <Kpis m={m} trajectory={trajectory} />
        <EffortCard m={m} />
        <ThirdsCard m={m} />
        <RankCard id="ferramentas" title="Ferramentas (top 10)" data={m.effort.tools_ranking} color="#0072B2" />
        <RankCard id="executaveis" title="Executáveis bash (top 10)" data={m.effort.executables_ranking} color="#56B4E9" />
        <ProblemsCard m={m} />
        <CyclesCard m={m} />
        <FilesCard m={m} />
        <ObsCard m={m} />
        {m.ground_truth && <GroundTruthCard m={m} />}
      </div>
      <p className="mt-3 text-center text-[11px] text-muted-foreground">trajetória {id} · todas as métricas vêm da API (<span className="mono">GET /api/trajectories/{id}/metrics</span>)</p>
    </div>
  )
}

// ---------------------------------------------------------------- KPIs
function Kpi({ label, value, sub, testid, title }: { label: string; value: React.ReactNode; sub?: string; testid?: string; title?: string }) {
  return <div className="min-w-0 overflow-hidden rounded border bg-muted/40 px-2.5 py-1.5" data-testid={testid} title={title}><div className="text-[11px] text-muted-foreground">{label}</div><div className="text-lg font-semibold leading-tight tabular-nums">{value}</div>{sub && <div className="break-words text-[11px] leading-tight text-muted-foreground">{sub}</div>}</div>
}

function Kpis({ m, trajectory }: { m: Metrics; trajectory: Trajectory }) {
  const o = m.outcome
  const oc = outcomeOf(trajectory)
  return (
    <DashCard id="kpis" title="Desfecho" subtitle={o.exit_status ? `exit_status: ${o.exit_status}` : undefined} className="2xl:col-span-1">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Kpi label="resultado" testid="kpi-outcome" value={<Badge tone={oc.tone} className="px-2 py-0.5 text-sm">{oc.label === 'PASS' ? '✓ PASS' : oc.label === 'FAIL' ? '✕ FAIL' : oc.label}</Badge>} sub={o.resolved_validated ? undefined : 'resolved/patch não confiáveis'} />
        <Kpi label="passos" value={fmtInt(o.n_steps)} sub={`${fmtInt(m.effort.n_core_steps)} úteis`} title="úteis = sem message, keys e harness_protocol" />
        <Kpi label="terminou em submit" value={o.ended_with_submit ? 'sim' : 'não'} />
        <Kpi label="arquivos alterados" value={fmtInt(o.patch_files)} sub={o.patch_source === 'patch' ? 'do patch' : o.patch_source === 'steps' ? 'derivado dos passos edit' : 'sem edição'} />
        <Kpi label="linhas +/−" value={<span><span className="text-ok">+{fmtInt(o.patch_lines_added)}</span> <span className="text-danger">−{fmtInt(o.patch_lines_removed)}</span></span>} />
        <Kpi label="1ª edição" testid="kpi-first-edit" value={m.dynamics.first_edit_idx != null ? `#${m.dynamics.first_edit_idx}` : '—'} sub={m.dynamics.pct_before_first_edit != null ? `${fmtPct(m.dynamics.pct_before_first_edit)} dos passos antes dela` : 'nenhuma edição'} />
      </div>
    </DashCard>
  )
}

// ---------------------------------------------------------------- esforço por categoria
function EffortCard({ m }: { m: Metrics }) {
  const include = useUI((s) => s.includeSpecial)
  const setInclude = useUI((s) => s.setIncludeSpecial)
  const e = m.effort
  const rows = useMemo(() => {
    const base = CATEGORY_ORDER.map((c) => ({ kind: c as Kind, count: e.by_category[c]?.count ?? 0, pct: include ? (e.by_category[c]?.pct_total ?? 0) : (e.by_category[c]?.pct_core ?? 0) }))
    const special = include ? SPECIAL.map((k) => { const s = e[k]; return { kind: k as Kind, count: s.count, pct: s.pct_total } }) : []
    return [...base, ...special].filter((r) => r.count > 0 || !KINDS[r.kind].special).map((r) => ({ ...r, name: `${KINDS[r.kind].code}  ${KINDS[r.kind].label}` }))
  }, [e, include])
  const ticks = roundTicks(Math.max(...rows.map((r) => r.pct), 0))
  return (
    <DashCard id="esforco" title="Esforço por categoria" subtitle={include ? '% sobre todos os passos (inclui message/keys/harness)' : `% sobre ${e.n_core_steps} passos (sem message/keys/harness)`}
      actions={<label className="flex items-center gap-1.5 text-[11px]"><Switch checked={include} onCheckedChange={setInclude} aria-label="Incluir message/keys" data-testid="include-special" />incluir message/keys</label>}>
      <div style={{ height: Math.max(220, rows.length * 24 + 20) }} data-testid="chart-effort">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 54, top: 2, bottom: 2 }}>
            <CartesianGrid horizontal={false} stroke="var(--border)" />
            <XAxis type="number" tick={AXIS} unit="%" domain={[0, ticks[ticks.length - 1]]} ticks={ticks} allowDecimals={false} />
            <YAxis type="category" dataKey="name" tick={AXIS} width={118} interval={0} />
            <Tooltip formatter={(v, _n, p) => [`${fmtPct(Number(v))} (${(p.payload as { count: number }).count} passos)`, 'participação']} contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', fontSize: 12 }} cursor={{ fill: 'var(--muted)' }} />
            <Bar dataKey="pct" isAnimationActive={false} label={{ position: 'right', fontSize: 11, fill: 'var(--muted-foreground)', formatter: (v: unknown) => fmtPct(Number(v)) }}>
              {rows.map((r) => <Cell key={r.kind} fill={KINDS[r.kind].special ? '#9ca3af' : KINDS[r.kind].color} stroke={KINDS[r.kind].special ? 'var(--foreground)' : undefined} strokeDasharray={KINDS[r.kind].special ? '3 2' : undefined} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </DashCard>
  )
}

// ---------------------------------------------------------------- terços
function ThirdsCard({ m }: { m: Metrics }) {
  const data = m.dynamics.dominant_phase_by_third.map((t) => {
    const total = t.n_steps || 1
    const row: Record<string, number | string> = { name: `${t.third}º terço` }
    PHASES.forEach((p) => { row[p] = Math.round(((t.counts?.[p] ?? 0) / total) * 1000) / 10 })
    return row
  })
  const dom = m.dynamics.dominant_phase_by_third
  return (
    <DashCard id="tercos" title="Esforço por terço da trajetória" subtitle={dom.length ? `dominante: ${dom.map((d) => d.phase ?? '—').join(' → ')}` : undefined}>
      <div style={{ height: 230 }} data-testid="chart-thirds">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="name" tick={AXIS} /><YAxis tick={AXIS} unit="%" domain={[0, 100]} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', fontSize: 12 }} cursor={{ fill: 'var(--muted)' }} />
            <RLegend wrapperStyle={{ fontSize: 11 }} />
            {PHASES.map((p) => <Bar key={p} dataKey={p} stackId="a" fill={PHASE_COLOR[p]} isAnimationActive={false} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </DashCard>
  )
}

function RankCard({ id, title, data, color }: { id: string; title: string; data: { name: string; count: number }[]; color: string }) {
  return (
    <DashCard id={id} title={title}>
      {data.length === 0 ? <Empty>sem dados</Empty> : (
        <div style={{ height: Math.max(160, data.length * 24 + 16) }} data-testid={`chart-${id}`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 4, right: 34, top: 2, bottom: 2 }}>
              <CartesianGrid horizontal={false} stroke="var(--border)" />
              <XAxis type="number" tick={AXIS} allowDecimals={false} /><YAxis type="category" dataKey="name" tick={AXIS} width={110} interval={0} />
              <Tooltip contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', fontSize: 12 }} cursor={{ fill: 'var(--muted)' }} />
              <Bar dataKey="count" fill={color} isAnimationActive={false} label={{ position: 'right', fontSize: 11, fill: 'var(--muted-foreground)' }} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </DashCard>
  )
}

// ---------------------------------------------------------------- problemas
function IdxChips({ idx, max = 14, tone = 'default' }: { idx: number[]; max?: number; tone?: 'default' | 'danger' }) {
  const go = useGoStep()
  return (
    <div className="flex flex-wrap gap-1">
      {idx.slice(0, max).map((i) => <button key={i} onClick={() => go(i)} data-testid="problem-chip" data-idx={i}
        className={cn('mono rounded border px-1 py-px text-[11px] hover:bg-accent', tone === 'danger' && 'border-danger/50 text-danger')}>#{i}</button>)}
      {idx.length > max && <span className="text-[11px] text-muted-foreground" title={idx.slice(max).join(', ')}>+{idx.length - max}</span>}
    </div>
  )
}

function ProblemsCard({ m }: { m: Metrics }) {
  const p = m.problems
  const go = useGoStep()
  const n = (x: { count: number; rate: number; idx?: number[] }) => ({ count: x.count, rate: x.rate, idx: x.idx ?? [] })
  const rows: { key: string; label: string; item: { count: number; rate: number; idx: number[] }; danger?: boolean }[] = [
    { key: 'error', label: '✕ erro', item: n(p.error), danger: true }, { key: 'repeated', label: 'repetido', item: n(p.repeated) },
    { key: 'no_new_info', label: 'sem informação nova', item: n(p.no_new_info) }, { key: 'loop', label: '↻ loop', item: n(p.loop), danger: true },
    { key: 'test_fail', label: '✕ teste falhou', item: n(p.test_fail), danger: true }, { key: 'truncated', label: 'obs. truncada', item: n(p.truncated) },
  ]
  return (
    <DashCard id="problemas" title="Problemas" subtitle="clique num passo para vê-lo no grafo" className="xl:col-span-2 2xl:col-span-1">
      <table className="w-full text-[12px]" data-testid="problems-table">
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t first:border-t-0 align-top" data-testid={`problem-${r.key}`}>
              <td className="w-36 py-1.5 pr-2 font-medium">{r.label}</td>
              <td className="w-20 py-1.5 pr-2 tabular-nums text-muted-foreground">{r.item.count} <span className="text-[11px]">({fmtPct(r.item.rate)})</span></td>
              <td className="py-1.5">{r.item.count ? <IdxChips idx={r.item.idx} tone={r.danger ? 'danger' : 'default'} /> : <span className="text-muted-foreground">—</span>}</td>
            </tr>
          ))}
          <tr className="border-t align-top"><td className="py-1.5 pr-2 font-medium">maior sequência de erros</td>
            <td className="py-1.5 pr-2 tabular-nums">{p.longest_error_streak.length}</td>
            <td className="py-1.5">{p.longest_error_streak.length > 0 && p.longest_error_streak.start_idx != null
              ? <button className="mono rounded border border-danger/50 px-1 py-px text-[11px] text-danger hover:bg-accent" onClick={() => go(p.longest_error_streak.start_idx as number)}>#{p.longest_error_streak.start_idx}–{p.longest_error_streak.end_idx}</button> : <span className="text-muted-foreground">—</span>}</td></tr>
          {p.loop_ranges.length > 0 && <tr className="border-t align-top"><td className="py-1.5 pr-2 font-medium">intervalos de loop</td><td className="py-1.5 pr-2 tabular-nums">{p.loop_ranges.length}</td>
            <td className="py-1.5"><div className="flex flex-wrap gap-1">{p.loop_ranges.map((lp, i) => <button key={i} title={lp.detail} onClick={() => go(lp.range[0])} data-testid="loop-chip" className="mono rounded border border-danger/50 px-1 py-px text-[11px] text-danger hover:bg-accent">↻ #{lp.range[0]}–{lp.range[1]}</button>)}</div></td></tr>}
        </tbody>
      </table>
    </DashCard>
  )
}

function CyclesCard({ m }: { m: Metrics }) {
  const d = m.dynamics
  return (
    <DashCard id="ciclos" title="Ciclos edit → test" subtitle="uma edição seguida de um teste">
      <div className="grid grid-cols-3 gap-2" data-testid="cycles">
        <Kpi label="ciclos" value={d.edit_test_cycles} />
        <Kpi label="terminaram em ✓ test_pass" value={<span className="text-ok">{d.cycles_passed}</span>} />
        <Kpi label="terminaram em ✕ test_fail" value={<span className="text-danger">{d.cycles_failed}</span>} />
      </div>
      {d.edit_test_cycles === 0 && <p className="mt-2 text-xs text-muted-foreground">Nenhuma edição foi verificada por um teste (nenhum passo <i>test</i> depois de uma edição).</p>}
      {d.edit_test_cycles > 0 && <div className="mt-2 h-2 overflow-hidden rounded bg-muted"><div className="h-full bg-ok" style={{ width: `${(d.cycles_passed / d.edit_test_cycles) * 100}%` }} /></div>}
    </DashCard>
  )
}

function FilesCard({ m }: { m: Metrics }) {
  const f = m.files
  const never = new Set(f.edited_never_read)
  const reread = new Set(f.read_3plus_no_edit)
  const created = new Set(f.created_by_agent)
  const go = useGoStep()
  return (
    <DashCard id="arquivos" title="Arquivos" subtitle={`${f.table.length} arquivos tocados`} className="xl:col-span-2">
      {f.table.length === 0 ? <Empty>nenhum arquivo identificado</Empty> : (
        <div className="scroll-thin max-h-72 overflow-auto" data-testid="files-table">
          <table className="w-full border-collapse text-[12px]">
            <thead className="sticky top-0 bg-card text-left text-[11px] text-muted-foreground"><tr><th className="py-1 pr-2 font-medium">arquivo</th><th className="px-2 text-right font-medium">lido</th><th className="px-2 text-right font-medium">editado</th><th className="px-2 text-right font-medium">exec.</th><th className="px-2 text-right font-medium">1º</th><th className="px-2 text-right font-medium">último</th><th className="pl-2 font-medium">alerta</th></tr></thead>
            <tbody>
              {f.table.slice(0, 60).map((r) => (
                <tr key={r.path} className="border-t">
                  <td className="mono max-w-[340px] truncate py-1 pr-2" title={r.path}>{r.path}</td>
                  <td className="px-2 text-right tabular-nums">{r.reads}</td><td className="px-2 text-right tabular-nums">{r.edits}</td><td className="px-2 text-right tabular-nums">{r.runs}</td>
                  <td className="px-2 text-right"><button className="mono text-primary hover:underline" onClick={() => go(r.first_idx)}>#{r.first_idx}</button></td>
                  <td className="px-2 text-right"><button className="mono text-primary hover:underline" onClick={() => go(r.last_idx)}>#{r.last_idx}</button></td>
                  <td className="pl-2">{created.has(r.path) && <Badge tone="muted" data-testid="badge-created" title="o 1º evento deste arquivo foi uma criação (editor create ou redirecionamento)">criado pelo agente</Badge>}{never.has(r.path) && <Badge tone="warn" data-testid="warn-never-read">editado sem ler</Badge>}{reread.has(r.path) && <Badge tone="muted" className="ml-1" data-testid="warn-reread">lido ≥ 3× sem editar</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </DashCard>
  )
}

function ObsCard({ m }: { m: Metrics }) {
  const go = useGoStep()
  const { dark } = useTheme()
  const trunc = new Set(m.problems.truncated.idx)
  const data = m.context.obs_chars.map((v, i) => ({ idx: i, chars: v }))
  return (
    <DashCard id="observacoes" title="Tamanho das observações por passo" subtitle={`total ${fmtInt(m.context.total_obs_chars)} chars · máx ${fmtInt(m.context.max_obs_chars)} · ${m.context.n_truncated} truncadas`} className="xl:col-span-2">
      <div style={{ height: 200 }} data-testid="chart-obs">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ left: 0, right: 8, top: 6, bottom: 0 }} onClick={(e) => { const i = (e as unknown as { activeLabel?: number }).activeLabel; if (typeof i === 'number') go(i) }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="idx" tick={AXIS} /><YAxis tick={AXIS} tickFormatter={(v) => (v >= 1000 ? `${v / 1000}k` : String(v))} />
            <Tooltip formatter={(v) => [`${fmtInt(Number(v))} chars`, 'observação']} labelFormatter={(l) => `passo #${l}`} contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', fontSize: 12 }} />
            <Line type="monotone" dataKey="chars" stroke={dark ? '#56B4E9' : '#0072B2'} dot={false} strokeWidth={1.4} isAnimationActive={false} />
            {[...trunc].map((i) => <ReferenceDot key={i} x={i} y={data[i]?.chars ?? 0} r={4} fill={ERROR_COLOR} stroke="#fff" ifOverflow="visible" />)}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground"><span className="inline-block size-2 rounded-full" style={{ background: ERROR_COLOR }} />observação truncada pela ferramenta · clique na linha para abrir o passo</p>
    </DashCard>
  )
}

function GroundTruthCard({ m }: { m: Metrics }) {
  const g = m.ground_truth!
  const rows = [
    { name: 'incorretos anotados', value: g.n_incorrect, color: '#D55E00' }, { name: '… também com erro/test_fail', value: g.incorrect_vs_error_or_test_fail.flagged, color: '#E69F00' },
    { name: 'inúteis anotados', value: g.n_unuseful, color: '#666666' }, { name: '… também repeated/no_new_info', value: g.unuseful_vs_repeated_or_no_new_info.flagged, color: '#9ca3af' },
  ]
  return (
    <DashCard id="gabarito" title="Gabarito (CodeTraceBench)" subtitle="passos anotados × flags automáticas (sobreposição simples; refinada na Fase 6)" className="xl:col-span-2 2xl:col-span-1">
      <div style={{ height: 170 }} data-testid="chart-gt">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 30, top: 2, bottom: 2 }}>
            <CartesianGrid horizontal={false} stroke="var(--border)" /><XAxis type="number" tick={AXIS} allowDecimals={false} /><YAxis type="category" dataKey="name" tick={AXIS} width={170} interval={0} />
            <Tooltip contentStyle={{ background: 'var(--card)', border: '1px solid var(--border)', fontSize: 12 }} cursor={{ fill: 'var(--muted)' }} />
            <Bar dataKey="value" isAnimationActive={false} label={{ position: 'right', fontSize: 11, fill: 'var(--muted-foreground)' }}>{rows.map((r) => <Cell key={r.name} fill={r.color} />)}</Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 space-y-1 text-xs">
        <div className="flex items-center gap-2"><span className="w-20 text-muted-foreground">incorretos</span><IdxChips idx={g.incorrect_idx} tone="danger" /></div>
        <div className="flex items-center gap-2"><span className="w-20 text-muted-foreground">inúteis</span><IdxChips idx={g.unuseful_idx} /></div>
        <div className="text-[11px] text-muted-foreground">alinhamento: {Object.entries(g.resolved_via).map(([k, v]) => `${k} ${v}`).join(' · ') || '—'}{g.unresolved ? ` · ${g.unresolved} sem alinhamento` : ''}</div>
      </div>
    </DashCard>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">{children}</div>
}
