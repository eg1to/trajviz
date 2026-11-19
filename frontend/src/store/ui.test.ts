import { describe, expect, it } from 'vitest'
import { DEFAULT_FILTERS, fromParams, toParams } from './ui'

describe('URL ⇄ estado', () => {
  it('ida e volta', () => {
    const st = { selectedIdx: 42, range: [10, 30] as [number, number], view: 'dashboard' as const,
      filters: { cats: ['edit', 'test'], onlyErrors: true, onlyLoops: false, hideSpecial: true }, compact: false, showGT: false }
    const p = toParams(st)
    expect(p.toString()).toContain('step=42')
    expect(fromParams(p)).toMatchObject(st)
  })
  it('padrão = URL vazia', () => {
    expect(toParams({ selectedIdx: null, range: null, view: 'graph', filters: DEFAULT_FILTERS, compact: null, showGT: true }).toString()).toBe('')
    expect(fromParams(new URLSearchParams('?step=abc')).selectedIdx).toBeNull()
  })
  it('exemplo da especificação', () => {
    const s = fromParams(new URLSearchParams('?step=42&view=graph&filter=error'))
    expect(s.selectedIdx).toBe(42); expect(s.view).toBe('graph'); expect(s.filters?.onlyErrors).toBe(true)
  })
})
