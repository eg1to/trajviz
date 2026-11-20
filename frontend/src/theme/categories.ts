// Cores FIXAS das categorias (base Okabe-Ito, seguras para daltonismo). Toda cor vem com letra + ícone (nunca só cor).
import {
  Brain, CircleHelp, FileText, FlaskConical, FolderTree, GitBranch, Keyboard, Flag, MessageSquare, Pencil, Play, Search,
  Settings2, ShieldCheck, type LucideIcon,
} from 'lucide-react'
import type { components } from '@/api/schema'

export type Category = components['schemas']['Step']['category']
export type Kind = Category | 'message' | 'keys' | 'harness_protocol'
export type Phase = 'Entendimento' | 'Modificação' | 'Verificação' | 'Controle'

export interface KindStyle { label: string; code: string; color: string; phase: Phase | null; icon: LucideIcon; special: boolean }

export const KINDS: Record<Kind, KindStyle> = {
  explore: { label: 'Explorar', code: 'Ex', color: '#56B4E9', phase: 'Entendimento', icon: FolderTree, special: false },
  search: { label: 'Buscar', code: 'Bu', color: '#0072B2', phase: 'Entendimento', icon: Search, special: false },
  read: { label: 'Ler', code: 'Le', color: '#1F4E79', phase: 'Entendimento', icon: FileText, special: false },
  edit: { label: 'Editar', code: 'Ed', color: '#E69F00', phase: 'Modificação', icon: Pencil, special: false },
  reproduce: { label: 'Reproduzir', code: 'Rp', color: '#CC79A7', phase: 'Verificação', icon: Play, special: false },
  test: { label: 'Testar', code: 'Te', color: '#009E73', phase: 'Verificação', icon: FlaskConical, special: false },
  vcs: { label: 'Versionar', code: 'Vc', color: '#7A5195', phase: 'Verificação', icon: GitBranch, special: false },
  setup: { label: 'Preparar', code: 'Pr', color: '#8C8C8C', phase: 'Controle', icon: Settings2, special: false },
  think: { label: 'Pensar', code: 'Pn', color: '#BDBDBD', phase: 'Controle', icon: Brain, special: false },
  submit: { label: 'Entregar', code: 'En', color: '#222222', phase: 'Controle', icon: Flag, special: false },
  other: { label: 'Outro', code: '··', color: '#E4E4E7', phase: null, icon: CircleHelp, special: true },
  message: { label: 'Mensagem', code: 'Ms', color: '#E4E4E7', phase: null, icon: MessageSquare, special: true },
  keys: { label: 'Teclas', code: 'Ky', color: '#E4E4E7', phase: null, icon: Keyboard, special: true },
  harness_protocol: { label: 'Protocolo do harness', code: 'Hp', color: '#E4E4E7', phase: null, icon: ShieldCheck, special: true },
}

export const CATEGORY_ORDER: Category[] = ['explore', 'search', 'read', 'edit', 'reproduce', 'test', 'vcs', 'setup', 'think', 'submit', 'other']
export const SPECIAL_KINDS: Kind[] = ['message', 'keys', 'harness_protocol']
export const PHASES: Phase[] = ['Entendimento', 'Modificação', 'Verificação', 'Controle']
export const PHASE_COLOR: Record<Phase, string> = { Entendimento: '#0072B2', Modificação: '#E69F00', Verificação: '#009E73', Controle: '#8C8C8C' }
export const ERROR_COLOR = '#D55E00'

/** Preenchimento por tema: as categorias especiais são cinza claro (claro) / cinza escuro (escuro), hachuradas e tracejadas. */
export function fill(kind: Kind, dark: boolean): string {
  const k = KINDS[kind]
  if (k.special) return dark ? '#2b2f38' : '#E4E4E7'
  if (dark && kind === 'submit') return DARK_SUBMIT // #222 some no fundo escuro: variante clara só no tema escuro
  return k.color
}
export const DARK_SUBMIT = '#E8E8E8'

function lum(hex: string): number {
  const n = parseInt(hex.slice(1), 16)
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}

export function contrast(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

/** Cor de texto (preto/branco) com maior contraste sobre o fundo. */
export function textOn(bg: string): string {
  return contrast(bg, '#FFFFFF') >= contrast(bg, '#111111') ? '#FFFFFF' : '#111111'
}

export function textFor(kind: Kind, dark: boolean): string {
  const k = KINDS[kind]
  if (k.special) return dark ? '#d4d4d8' : '#3f3f46'
  return textOn(fill(kind, dark))
}

/** Passo → tipo visual (message/keys/harness têm prioridade sobre a categoria). */
export function kindOf(s: { category: Category; subcategory?: string | null; action: { tool: string } }): Kind {
  if (s.subcategory === 'harness_protocol') return 'harness_protocol'
  if (s.subcategory === 'keys') return 'keys'
  if (s.action.tool === 'message') return 'message'
  return s.category
}
