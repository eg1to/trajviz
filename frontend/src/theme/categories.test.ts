import { describe, expect, it } from 'vitest'
import { CATEGORY_ORDER, KINDS, contrast, fill, textFor } from './categories'

const DARK_BG = '#0f1115'

describe('paleta das categorias', () => {
  it('texto sobre cada cor tem contraste ≥ 4,5:1 nos dois temas', () => {
    for (const dark of [false, true]) {
      for (const k of Object.keys(KINDS) as (keyof typeof KINDS)[]) {
        expect(contrast(fill(k, dark), textFor(k, dark)), `${k} ${dark ? 'dark' : 'light'}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  })
  it('as cores base são as do Okabe-Ito pedido', () => {
    expect(KINDS.explore.color).toBe('#56B4E9'); expect(KINDS.edit.color).toBe('#E69F00'); expect(KINDS.test.color).toBe('#009E73')
    expect(CATEGORY_ORDER).toHaveLength(11)
  })
  it('toda categoria tem letra e ícone distintos', () => {
    const codes = Object.values(KINDS).map((k) => k.code)
    expect(new Set(codes).size).toBe(codes.length)
    expect(Object.values(KINDS).every((k) => !!k.icon)).toBe(true)
  })
  it('submit (#222) tem variante clara no tema escuro e continua legível', () => {
    expect(fill('submit', false)).toBe('#222222')
    expect(fill('submit', true)).not.toBe('#222222')
    expect(contrast(fill('submit', true), DARK_BG)).toBeGreaterThanOrEqual(7)  // visível sobre o fundo escuro
    expect(contrast(fill('submit', true), textFor('submit', true))).toBeGreaterThanOrEqual(4.5)
    expect(contrast(fill('submit', false), '#fafafa')).toBeGreaterThanOrEqual(7)
  })
  it('cores distintas dentro da fase Entendimento', () => {
    expect(new Set([KINDS.explore.color, KINDS.search.color, KINDS.read.color]).size).toBe(3)
  })
})
