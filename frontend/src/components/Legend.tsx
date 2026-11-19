import { CATEGORY_ORDER, ERROR_COLOR, KINDS, PHASES, PHASE_COLOR, fill, textFor, type Kind } from '@/theme/categories'
import { useTheme } from '@/theme/useTheme'
import { useUI } from '@/store/ui'
import { cn } from '@/lib/utils'

export function KindChip({ kind, count, active, onClick, compact }: { kind: Kind; count?: number; active?: boolean; onClick?: () => void; compact?: boolean }) {
  const { dark } = useTheme()
  const k = KINDS[kind]
  const Icon = k.icon
  const Tag = onClick ? 'button' : 'span'
  return (
    <Tag onClick={onClick} data-testid={`chip-${kind}`} aria-pressed={onClick ? active : undefined} title={`${k.label}${k.phase ? ` · ${k.phase}` : ''}`}
      className={cn('inline-flex items-center gap-1 rounded border px-1.5 py-px text-[11px] font-medium', onClick && 'hover:brightness-95', active === false && 'opacity-40')}
      style={{ backgroundColor: k.special ? undefined : fill(kind, dark), color: textFor(kind, dark), borderStyle: k.special ? 'dashed' : 'solid', borderColor: k.special ? '#9ca3af' : 'transparent',
        backgroundImage: k.special ? `repeating-linear-gradient(135deg, ${fill(kind, dark)} 0 5px, ${dark ? '#343944' : '#d4d4d8'} 5px 6px)` : undefined }}>
      <Icon className="size-3" />{compact ? k.code : k.label}{count != null && <span className="opacity-80">{count}</span>}
    </Tag>
  )
}

/** Legenda por fase (cor + letra + ícone) e marcadores. */
export function Legend({ showMarkers = true }: { showMarkers?: boolean }) {
  const setFilters = useUI((s) => s.setFilters)
  const cats = useUI((s) => s.filters.cats)
  const toggle = (k: Kind) => setFilters({ cats: cats.includes(k) ? cats.filter((c) => c !== k) : [...cats, k] })
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1" data-testid="legend">
      {PHASES.map((ph) => (
        <div key={ph} className="flex items-center gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: PHASE_COLOR[ph] === '#8C8C8C' ? 'var(--muted-foreground)' : PHASE_COLOR[ph] }}>{ph}</span>
          {CATEGORY_ORDER.filter((c) => KINDS[c].phase === ph).map((c) => <KindChip key={c} kind={c} onClick={() => toggle(c)} active={cats.length === 0 ? undefined : cats.includes(c)} />)}
        </div>
      ))}
      <div className="flex items-center gap-1">
        {(['other', 'message', 'keys', 'harness_protocol'] as Kind[]).map((c) => <KindChip key={c} kind={c} onClick={() => toggle(c)} active={cats.length === 0 ? undefined : cats.includes(c)} />)}
      </div>
      {showMarkers && (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <span className="inline-flex items-center gap-1"><span className="inline-block h-3 w-4 rounded-sm border-2" style={{ borderColor: ERROR_COLOR }} />erro</span>
          <span className="inline-flex items-center gap-1"><span className="font-bold text-[#D55E00]">✕</span>/<span className="font-bold text-[#009E73]">✓</span> teste</span>
          <span className="inline-flex items-center gap-1"><span className="inline-block size-2 rounded-full bg-[#E69F00] ring-1 ring-black/40" />repetido</span>
          <span className="inline-flex items-center gap-1"><span className="inline-block h-1 w-4 rounded" style={{ background: ERROR_COLOR }} />loop</span>
        </div>
      )}
    </div>
  )
}
