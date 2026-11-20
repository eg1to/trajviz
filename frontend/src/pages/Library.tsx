import { useCallback, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileUp, Loader2, Search, TriangleAlert, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { useLibrary, useOpenSample, useUpload } from '@/api/hooks'
import type { LibraryItem, UploadResponse } from '@/api/client'
import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/ThemeToggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn, fmtInt } from '@/lib/utils'

const ACCEPT = '.json,.jsonl,.traj,.parquet,.tar.zst,.zip'
const FORMATS = ['openhands_chat', 'sweagent_smith', 'ctb_sweagent', 'ctb_miniswe', 'ctb_openhands_swe', 'ctb_openhands_events', 'ctb_terminus2', 'generic_chat']
const DATASET_LABEL: Record<string, string> = { 'swe-rebench': 'SWE-rebench', 'swe-smith': 'SWE-smith', codetracebench: 'CodeTraceBench' }

export default function Library() {
  const nav = useNavigate()
  const [filters, setFilters] = useState({ dataset: '', agent: '', resolved: '', q: '' })
  const params = useMemo(() => ({ dataset: filters.dataset || undefined, agent: filters.agent || undefined, q: filters.q || undefined,
    resolved: filters.resolved === '' ? null : filters.resolved === 'true' }), [filters])
  const lib = useLibrary(params)
  const all = useLibrary({})
  const open = useOpenSample()

  const datasets = useMemo(() => [...new Set((all.data ?? []).map((i) => i.dataset))], [all.data])
  const agents = useMemo(() => [...new Set((all.data ?? []).map((i) => i.agent).filter(Boolean) as string[])], [all.data])

  const goTo = (r: UploadResponse) => {
    toast.success(`Formato detectado: ${r.format_detected} (${Math.round(r.confidence * 100)}% de confiança) · ${r.n_steps} passos`, { id: `fmt-${r.id}`, duration: 4000 })
    if (r.warnings.length) toast.warning(r.warnings.join(' · '), { duration: 8000, id: `warn-${r.id}` })
    nav(`/t/${r.id}`)
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex h-11 items-center justify-between border-b bg-card px-4">
        <Logo />
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="hidden sm:inline">Visualizador de trajetórias de agentes de código — sem rotulação manual</span>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1400px] flex-1 space-y-4 p-4">
        <UploadCard onDone={goTo} />
        <section>
          <div className="mb-2 flex flex-wrap items-end gap-2">
            <h2 className="mr-auto text-sm font-semibold">Biblioteca <span className="font-normal text-muted-foreground">({lib.data?.length ?? '…'} amostras)</span></h2>
            <div className="relative w-56">
              <Search className="absolute left-2 top-2.5 size-3.5 text-muted-foreground" />
              <Input className="pl-7" placeholder="Buscar tarefa, modelo…" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} data-testid="lib-search" />
            </div>
            <FilterSelect label="Dataset" value={filters.dataset} onChange={(v) => setFilters({ ...filters, dataset: v })} options={datasets.map((d) => [d, DATASET_LABEL[d] ?? d])} testid="filter-dataset" />
            <FilterSelect label="Agente" value={filters.agent} onChange={(v) => setFilters({ ...filters, agent: v })} options={agents.map((a) => [a, a])} testid="filter-agent" />
            <FilterSelect label="Resolved" value={filters.resolved} onChange={(v) => setFilters({ ...filters, resolved: v })} options={[['true', 'Resolvida'], ['false', 'Não resolvida']]} testid="filter-resolved" />
          </div>
          <LibraryTable items={lib.data} loading={lib.isLoading} openingId={open.isPending ? (open.variables?.id ?? null) : null}
            onOpen={(it) => open.mutate({ id: it.id }, { onSuccess: goTo })} />
        </section>
      </main>
    </div>
  )
}

function FilterSelect({ label, value, onChange, options, testid }: { label: string; value: string; onChange: (v: string) => void; options: string[][]; testid: string }) {
  return (
    <Select value={value || 'all'} onValueChange={(v) => onChange(v === 'all' ? '' : v)}>
      <SelectTrigger className="w-40" data-testid={testid} aria-label={label}><SelectValue placeholder={label} /></SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{label}: todos</SelectItem>
        {options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
      </SelectContent>
    </Select>
  )
}

function UploadCard({ onDone }: { onDone: (r: UploadResponse) => void }) {
  const upload = useUpload()
  const [over, setOver] = useState(false)
  const [row, setRow] = useState('')
  const [format, setFormat] = useState('')
  const [useLlm, setUseLlm] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const send = useCallback((file: File) => {
    upload.mutate({ file, format: format || undefined, row: row === '' ? undefined : Number(row), useLlm }, { onSuccess: onDone })
  }, [upload, format, row, useLlm, onDone])

  return (
    <section className="grid gap-3 rounded-md border bg-card p-3 md:grid-cols-[1fr_320px]">
      <div
        data-testid="dropzone"
        onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files?.[0]; if (f) send(f) }}
        onClick={() => inputRef.current?.click()}
        className={cn('flex h-32 cursor-pointer flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed text-muted-foreground transition-colors', over ? 'border-primary bg-accent text-primary' : 'border-input hover:bg-muted')}
        role="button" tabIndex={0} aria-label="Enviar arquivo de trajetória" onKeyDown={(e) => { if (e.key === 'Enter') inputRef.current?.click() }}
      >
        {upload.isPending ? <><Loader2 className="size-5 animate-spin" /><span>Processando… (detecção → rótulos → métricas)</span></>
          : <><Upload className="size-5" /><span className="font-medium text-foreground">Arraste um log de agente ou clique para escolher</span>
            <span className="text-xs">.json · .jsonl · .traj · .parquet · .tar.zst · .zip — até 200 MB. Vai direto para a visualização, sem rotulação manual.</span></>}
        <input ref={inputRef} type="file" accept={ACCEPT} hidden data-testid="file-input" onChange={(e) => { const f = e.target.files?.[0]; if (f) send(f); e.target.value = '' }} />
      </div>
      <div className="space-y-2.5 text-xs">
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1"><Label htmlFor="row">Linha do Parquet</Label><Input id="row" type="number" min={0} placeholder="0" value={row} onChange={(e) => setRow(e.target.value)} /></div>
          <div className="space-y-1"><Label>Forçar formato</Label>
            <Select value={format || 'auto'} onValueChange={(v) => setFormat(v === 'auto' ? '' : v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="auto">detectar</SelectItem>{FORMATS.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <label className="flex cursor-pointer items-start gap-2">
          <Checkbox checked={useLlm} onCheckedChange={(v) => setUseLlm(v === true)} className="mt-0.5" aria-label="Usar LLM nos casos ambíguos" />
          <span><span className="font-medium text-foreground">Usar LLM nos casos ambíguos</span>
            <span className="mt-0.5 flex items-start gap-1 text-muted-foreground"><TriangleAlert className="mt-0.5 size-3 shrink-0 text-[#E69F00]" />Gasta créditos da API (≈ US$ 0,001 por trajetória típica). Desligado = só regras, de graça.</span></span>
        </label>
        <Button variant="outline" size="sm" onClick={() => inputRef.current?.click()}><FileUp /> Escolher arquivo</Button>
      </div>
    </section>
  )
}

function ResolvedBadge({ item }: { item: LibraryItem }) {
  const unvalidated = item.dataset === 'swe-smith'
  if (item.resolved == null) return <Badge tone="muted">sem dado</Badge>
  return <span className="inline-flex items-center gap-1">
    <Badge tone={item.resolved ? 'ok' : 'danger'}>{item.resolved ? '✓ PASS' : '✕ FAIL'}</Badge>
    {unvalidated && <Badge tone="warn" title="resolved/patch do SWE-smith não são confiáveis">não validado</Badge>}
  </span>
}

function LibraryTable({ items, loading, onOpen, openingId }: { items?: LibraryItem[]; loading: boolean; onOpen: (i: LibraryItem) => void; openingId: string | null }) {
  if (loading) return <div className="rounded-md border bg-card p-8 text-center text-muted-foreground"><Loader2 className="mx-auto mb-2 size-5 animate-spin" />Carregando biblioteca…</div>
  if (!items?.length) return <div className="rounded-md border bg-card p-8 text-center text-muted-foreground" data-testid="lib-empty">Nenhuma amostra com esses filtros.</div>
  return (
    <div className="overflow-auto rounded-md border bg-card scroll-thin" style={{ maxHeight: 'calc(100vh - 360px)', minHeight: 240 }}>
      <table className="w-full border-collapse text-[13px]" data-testid="lib-table">
        <thead className="sticky top-0 z-10 bg-muted text-left text-xs text-muted-foreground">
          <tr>{['Dataset', 'Agente', 'Modelo', 'Tarefa', 'Passos', 'Resolved'].map((h, i) => <th key={h} className={cn('px-3 py-1.5 font-medium', i === 4 && 'text-right')}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.id} onClick={() => onOpen(it)} data-testid="lib-row" data-sample-id={it.id} data-dataset={it.dataset}
              className={cn('cursor-pointer border-t hover:bg-accent', openingId === it.id && 'opacity-60')}>
              <td className="px-3 py-1.5"><span className="font-medium">{DATASET_LABEL[it.dataset] ?? it.dataset}</span>{it.split && <span className="ml-1 text-xs text-muted-foreground">/{it.split}</span>}
                {it.processed && <span className="ml-1 text-[10px] text-ok" title="já processada (em cache)">●</span>}</td>
              <td className="px-3 py-1.5">{it.agent ?? '—'}</td>
              <td className="max-w-[220px] truncate px-3 py-1.5 text-muted-foreground" title={it.model ?? ''}>{it.model ?? '—'}</td>
              <td className="max-w-[360px] truncate px-3 py-1.5 mono" title={it.task ?? ''}>{it.task ?? it.id}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">{fmtInt(it.n_steps)}</td>
              <td className="px-3 py-1.5"><ResolvedBadge item={it} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
