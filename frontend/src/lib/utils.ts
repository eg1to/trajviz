import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function truncate(s: string | null | undefined, n: number): string {
  const t = (s ?? '').replace(/\s+/g, ' ').trim()
  return t.length > n ? t.slice(0, n - 1) + '…' : t
}

export function fmtInt(n: number | null | undefined): string {
  return n == null ? '—' : n.toLocaleString('pt-BR')
}

export function fmtPct(n: number | null | undefined, digits = 1): string {
  return n == null ? '—' : `${n.toFixed(digits).replace('.', ',')}%`
}

/** Marcações do eixo em valores redondos (0, 10, 20, 30…): passo 5 se o máximo ≤ 20, senão 10. */
export function roundTicks(max: number): number[] {
  const step = max <= 20 ? 5 : 10
  const top = Math.max(step, Math.ceil(max / step) * step)
  return Array.from({ length: top / step + 1 }, (_, i) => i * step)
}
