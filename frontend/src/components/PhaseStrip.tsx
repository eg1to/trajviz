import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { ThumbsDown, Trash2 } from 'lucide-react'
import type { Step } from '@/api/client'
import { ERROR_COLOR, KINDS, fill, kindOf } from '@/theme/categories'
import { useTheme } from '@/theme/useTheme'
import { commandShort, filtersActive, flagsOf, passesFilters, type GTSets } from '@/lib/steps'
import { useUI } from '@/store/ui'
import type { LoopRange } from '@/lib/graph'

const H_TOP = 12, H_BAR = 22, H_BOT = 12, H = H_TOP + H_BAR + H_BOT

export interface PhaseStripHandle { element: HTMLDivElement | null }

/** Faixa de fases: um retângulo fino por passo (SVG; 700 passos sem custo). Hover = tooltip, clique = seleciona, arrastar = intervalo. */
export const PhaseStrip = forwardRef<PhaseStripHandle, { steps: Step[]; loops: LoopRange[]; gt: GTSets }>(function PhaseStrip({ steps, loops, gt }, ref) {
  const wrap = useRef<HTMLDivElement>(null)
  useImperativeHandle(ref, () => ({ element: wrap.current }))
  const [w, setW] = useState(1000)
  const { dark } = useTheme()
  const { selectedIdx, range, filters, showGT } = useUI()
  const select = useUI((s) => s.select)
  const setRange = useUI((s) => s.setRange)
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null)
  const [drag, setDrag] = useState<{ a: number; b: number } | null>(null)
  const n = steps.length

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(() => setW(Math.max(200, el.clientWidth)))
    ro.observe(el)
    setW(Math.max(200, el.clientWidth))
    return () => ro.disconnect()
  }, [])

  const cw = w / Math.max(n, 1)
  const idxAt = useCallback((clientX: number) => {
    const r = wrap.current!.getBoundingClientRect()
    return Math.max(0, Math.min(n - 1, Math.floor(((clientX - r.left) / r.width) * n)))
  }, [n])

  const dim = filtersActive(filters)
  const rects = useMemo(() => steps.map((s, i) => {
    const kind = kindOf(s)
    const k = KINDS[kind]
    return { i, kind, special: k.special, color: fill(kind, dark), error: flagsOf(s).includes('error'), dot: flagsOf(s).includes('repeated') || flagsOf(s).includes('no_new_info'),
      fail: flagsOf(s).includes('test_fail'), pass: flagsOf(s).includes('test_pass'), dimmed: dim && !passesFilters(s, filters) }
  }), [steps, dark, dim, filters])

  const sel = drag ? [Math.min(drag.a, drag.b), Math.max(drag.a, drag.b)] : range
  const barW = Math.max(cw - (cw > 4 ? 1 : 0), 0.6)

  return (
    <div ref={wrap} className="relative select-none" data-testid="phase-strip" style={{ height: H }}>
      <svg width={w} height={H} className="block" role="img" aria-label={`Faixa de fases com ${n} passos`}
        onMouseMove={(e) => { const i = idxAt(e.clientX); setHover({ i, x: e.clientX, y: e.clientY }); if (drag) setDrag({ ...drag, b: i }) }}
        onMouseLeave={() => { setHover(null); setDrag(null) }}
        onMouseDown={(e) => { const i = idxAt(e.clientX); setDrag({ a: i, b: i }) }}
        onMouseUp={(e) => {
          const i = idxAt(e.clientX)
          if (drag && Math.abs(i - drag.a) >= 2) { setRange([Math.min(i, drag.a), Math.max(i, drag.a)]) }
          else { setRange(null); select(i) }
          setDrag(null)
        }}>
        <defs>
          <pattern id="hatch-l" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="#E4E4E7" /><line x1="0" y1="0" x2="0" y2="5" stroke="#9ca3af" strokeWidth="1.4" /></pattern>
          <pattern id="hatch-d" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="#2b2f38" /><line x1="0" y1="0" x2="0" y2="5" stroke="#6b7280" strokeWidth="1.4" /></pattern>
        </defs>
        {/* faixa sob o intervalo de cada loop */}
        {loops.map((lp, li) => <rect key={li} data-testid="strip-loop" x={lp.range[0] * cw} y={H_TOP + H_BAR + 5} width={(lp.range[1] - lp.range[0] + 1) * cw} height={4} rx={2} fill={ERROR_COLOR}><title>{`loop ${lp.range[0]}–${lp.range[1]}: ${lp.detail}`}</title></rect>)}
        {rects.map((r) => (
          <g key={r.i} opacity={r.dimmed ? 0.18 : 1}>
            <rect x={r.i * cw} y={H_TOP} width={barW} height={H_BAR} fill={r.special ? `url(#hatch-${dark ? 'd' : 'l'})` : r.color} data-kind={r.kind} />
            {r.error && <rect x={r.i * cw} y={H_TOP + H_BAR + 1} width={Math.max(barW, 1.6)} height={3} fill={ERROR_COLOR} data-testid="strip-error" />}
            {r.dot && <circle cx={r.i * cw + barW / 2} cy={4} r={Math.max(1.6, Math.min(2.6, cw / 2))} fill="#E69F00" stroke={dark ? '#000' : '#444'} strokeWidth={0.5} />}
          </g>
        ))}
        {/* gabarito (CTB): ▼ incorreto, ▽ inútil */}
        {showGT && [...gt.incorrect].map((i) => <path key={`i${i}`} data-testid="strip-gt-incorrect" d={`M ${i * cw - 3 + barW / 2} 0 h 6 l -3 7 z`} fill="#D55E00" stroke="#fff" strokeWidth={0.6} />)}
        {showGT && [...gt.unuseful].map((i) => <path key={`u${i}`} data-testid="strip-gt-unuseful" d={`M ${i * cw - 3 + barW / 2} 0 h 6 l -3 7 z`} fill="none" stroke={dark ? '#e5e5e5' : '#222'} strokeWidth={1.4} />)}
        {rects.filter((r) => r.fail || r.pass).slice(0, 400).map((r) => <text key={`t${r.i}`} x={r.i * cw + barW / 2} y={H_TOP + H_BAR - 5} textAnchor="middle" fontSize={Math.min(11, Math.max(8, cw * 1.3))} fontWeight={800}
          fill="#fff" stroke="#000" strokeWidth={0.4} paintOrder="stroke">{r.fail ? '✕' : '✓'}</text>)}
        {sel && <rect x={sel[0] * cw} y={H_TOP - 2} width={(sel[1] - sel[0] + 1) * cw} height={H_BAR + 4} fill="rgba(0,114,178,0.18)" stroke="#0072B2" strokeWidth={1.5} pointerEvents="none" data-testid="strip-range" />}
        {selectedIdx != null && selectedIdx < n && <rect x={selectedIdx * cw - 1} y={H_TOP - 3} width={Math.max(barW, 2) + 2} height={H_BAR + 6} fill="none" stroke={dark ? '#fff' : '#111'} strokeWidth={2} pointerEvents="none" data-testid="strip-selected" />}
      </svg>
      {hover && steps[hover.i] && <StripTip step={steps[hover.i]} x={hover.x} y={hover.y} gt={gt} />}
    </div>
  )
})

function StripTip({ step, x, y, gt }: { step: Step; x: number; y: number; gt: GTSets }) {
  const kind = kindOf(step)
  const k = KINDS[kind]
  const Icon = k.icon
  const f = flagsOf(step)
  return (
    <div className="pointer-events-none fixed z-50 max-w-sm rounded border bg-card px-2 py-1.5 text-xs shadow-sm" style={{ left: Math.min(x + 12, window.innerWidth - 340), top: y + 16 }} data-testid="strip-tooltip">
      <div className="flex items-center gap-1.5 font-semibold"><Icon className="size-3" />#{step.idx} · {k.label}{step.subcategory ? <span className="font-normal text-muted-foreground">/{step.subcategory}</span> : null}</div>
      <div className="mono mt-0.5 truncate text-muted-foreground">{commandShort(step, 80)}</div>
      {f.length > 0 && <div className="mt-0.5 text-[11px]">{f.join(' · ')}</div>}
      {gt.incorrect.has(step.idx) && <div className="flex items-center gap-1 text-[11px] text-[#D55E00]"><ThumbsDown className="size-3" />gabarito: incorreto</div>}
      {gt.unuseful.has(step.idx) && <div className="flex items-center gap-1 text-[11px]"><Trash2 className="size-3" />gabarito: inútil</div>}
    </div>
  )
}
