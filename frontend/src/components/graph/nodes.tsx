import { memo } from 'react'
import { BaseEdge, Handle, Position, type EdgeProps, type NodeProps } from '@xyflow/react'
import { Check, Flag, ThumbsDown, Trash2, X } from 'lucide-react'
import type { Step } from '@/api/client'
import { ERROR_COLOR, KINDS, fill, kindOf, textFor, type Kind } from '@/theme/categories'
import { useTheme } from '@/theme/useTheme'
import { commandShort, flagsOf } from '@/lib/steps'
import { useUI } from '@/store/ui'
import { cn } from '@/lib/utils'

const handleCls = '!h-1 !w-1 !border-0 !bg-transparent'
const Handles = () => (
  <>
    <Handle id="l" type="target" position={Position.Left} className={handleCls} />
    <Handle id="r" type="source" position={Position.Right} className={handleCls} />
    <Handle id="tt" type="target" position={Position.Top} className={handleCls} />
    <Handle id="ts" type="source" position={Position.Top} className={handleCls} />
    <Handle id="bs" type="source" position={Position.Bottom} className={handleCls} />
    <Handle id="bt" type="target" position={Position.Bottom} className={handleCls} />
  </>
)

/** Estilo de caixa por tipo: especiais são hachurados e tracejados (cinza claro). */
function boxStyle(kind: Kind, dark: boolean, error: boolean, selected: boolean, inRange: boolean): React.CSSProperties {
  const k = KINDS[kind]
  const bg = fill(kind, dark)
  return {
    background: k.special
      ? `repeating-linear-gradient(135deg, ${bg} 0 6px, ${dark ? '#343944' : '#d4d4d8'} 6px 7px)`
      : bg,
    color: textFor(kind, dark),
    border: `${error ? 2.5 : 1.5}px ${k.special ? 'dashed' : 'solid'} ${error ? ERROR_COLOR : k.special ? (dark ? '#6b7280' : '#9ca3af') : dark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.35)'}`,
    outline: selected ? `2px solid ${dark ? '#fff' : '#111'}` : inRange ? `2px solid ${dark ? '#56B4E9' : '#0072B2'}` : undefined,
    outlineOffset: selected || inRange ? 2 : undefined,
  }
}

function Marks({ step }: { step: Step }) {
  const f = flagsOf(step)
  return (
    <span className="absolute -top-2 right-1 flex items-center gap-0.5">
      {f.includes('test_fail') && <span title="teste falhou" className="rounded bg-white px-0.5 text-[10px] font-bold leading-3 text-[#D55E00] ring-1 ring-[#D55E00]">✕</span>}
      {f.includes('test_pass') && <span title="teste passou" className="rounded bg-white px-0.5 text-[10px] font-bold leading-3 text-[#007a5a] ring-1 ring-[#009E73]">✓</span>}
      {(f.includes('repeated') || f.includes('no_new_info')) && <span title="repetido / sem informação nova" className="size-2 rounded-full bg-[#E69F00] ring-1 ring-black/40" />}
    </span>
  )
}

function GTMarks({ incorrect, unuseful }: { incorrect: boolean; unuseful: boolean }) {
  if (!incorrect && !unuseful) return null
  return (
    <span className="absolute -bottom-2 left-1 flex gap-0.5">
      {incorrect && <span title="gabarito: passo incorreto" className="flex items-center gap-0.5 rounded bg-[#D55E00] px-1 text-[9px] font-bold leading-3 text-white"><ThumbsDown className="!size-2.5" />inc</span>}
      {unuseful && <span title="gabarito: passo inútil" className="flex items-center gap-0.5 rounded bg-[#444] px-1 text-[9px] font-bold leading-3 text-white"><Trash2 className="!size-2.5" />inú</span>}
    </span>
  )
}

export const StepNode = memo(function StepNode({ data }: NodeProps) {
  const { dark } = useTheme()
  const step = data.step as Step
  const idx = step.idx
  const selected = useUI((s) => s.selectedIdx === idx)
  const inRange = useUI((s) => s.range != null && idx >= s.range[0] && idx <= s.range[1])
  const kind = kindOf(step)
  const k = KINDS[kind]
  const Icon = k.icon
  const error = flagsOf(step).includes('error')
  return (
    <div data-testid="step-node" data-idx={idx} data-kind={kind} data-error={error || undefined} data-selected={selected || undefined}
      className="relative flex h-full w-full flex-col justify-between rounded-md px-1.5 py-1 text-[11px] leading-tight" style={boxStyle(kind, dark, error, selected, inRange)}>
      <Handles />
      <div className="flex items-center gap-1 font-semibold">
        <Icon className="!size-3" /><span className="mono !text-[10px]">{k.code}</span>
        <span className="ml-auto tabular-nums opacity-80">#{idx}</span>
      </div>
      <div className="mono truncate !text-[10.5px]" title={commandShort(step, 200)}>{commandShort(step, 40)}</div>
      <Marks step={step} />
      <GTMarks incorrect={!!data.gtIncorrect} unuseful={!!data.gtUnuseful} />
    </div>
  )
})

export const GroupNode = memo(function GroupNode({ data }: NodeProps) {
  const { dark } = useTheme()
  const steps = data.steps as Step[]
  const kind = data.kind as Kind
  const k = KINDS[kind]
  const Icon = k.icon
  const toggle = useUI((s) => s.toggleGroup)
  const selected = useUI((s) => s.selectedIdx != null && steps.some((x) => x.idx === s.selectedIdx))
  const errors = steps.filter((s) => flagsOf(s).includes('error')).length
  return (
    <div data-testid="group-node" data-kind={kind} data-count={steps.length} onClick={(e) => { e.stopPropagation(); toggle(data.key as string) }}
      title="Clique para expandir" className="relative flex h-full w-full flex-col justify-between rounded-md px-1.5 py-1 text-[11px] leading-tight"
      style={{ ...boxStyle(kind, dark, errors > 0, selected, false), boxShadow: `3px 3px 0 -1px ${dark ? '#0f1115' : '#fff'}, 3px 3px 0 0 ${k.special ? '#9ca3af' : k.color}` }}>
      <Handles />
      <div className="flex items-center gap-1 font-semibold"><Icon className="!size-3" /><span className="mono !text-[10px]">{k.code}</span>
        <span className="ml-auto tabular-nums opacity-80">#{steps[0].idx}–{steps[steps.length - 1].idx}</span></div>
      <div className="font-semibold">{k.label.toLowerCase()} × {steps.length}{errors > 0 && <span className="ml-1 inline-flex items-center"><X className="!size-3" />{errors}</span>}</div>
      <GTMarks incorrect={!!data.gtIncorrect} unuseful={!!data.gtUnuseful} />
    </div>
  )
})

export const OutcomeNode = memo(function OutcomeNode({ data }: NodeProps) {
  const tone = data.tone as string
  const Icon = tone === 'ok' ? Check : tone === 'danger' ? X : Flag
  const color = tone === 'ok' ? '#009E73' : tone === 'danger' ? '#D55E00' : tone === 'warn' ? '#E69F00' : '#8C8C8C'
  return (
    <div data-testid="outcome-node" className="flex h-full w-full items-center justify-center gap-1.5 rounded-full border-2 text-xs font-bold" style={{ borderColor: color, color }}>
      <Handles /><Icon className="size-4" />{data.label as string}
    </div>
  )
})

export const LoopArcNode = memo(function LoopArcNode({ data }: NodeProps) {
  const w = data.w as number
  return (
    <svg width={w} height={26} style={{ overflow: 'visible' }} data-testid="loop-arc">
      <title>{data.detail as string}</title>
      <path d={`M 2 24 Q ${w / 2} -10 ${w - 2} 24`} fill="none" stroke={ERROR_COLOR} strokeWidth={2} strokeDasharray="5 3" />
      <text x={w / 2} y={6} textAnchor="middle" fontSize={10} fontWeight={700} fill={ERROR_COLOR}>↻ {data.label as string}</text>
    </svg>
  )
})

export function ReturnEdge({ id, sourceX, sourceY, targetX, targetY, markerEnd, data }: EdgeProps) {
  const dx = Math.abs(targetX - sourceX)
  const lift = 36 + Math.min(dx * 0.12, 90) + (Math.abs(targetY - sourceY) > 5 ? 10 : 0)
  const path = `M ${sourceX} ${sourceY} C ${sourceX} ${sourceY - lift}, ${targetX} ${targetY - lift}, ${targetX} ${targetY}`
  const color = data?.flag === 'repeated' ? '#E69F00' : '#CC79A7'
  return <BaseEdge id={id} path={path} markerEnd={markerEnd} style={{ stroke: color, strokeWidth: 1.4, strokeDasharray: '4 3', opacity: 0.85 }} />
}

export const nodeTypes = { step: StepNode, group: GroupNode, outcome: OutcomeNode, loopArc: LoopArcNode }
export const edgeTypes = { return: ReturnEdge }
export { cn }
