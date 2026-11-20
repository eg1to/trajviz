import { describe, expect, it } from 'vitest'
import { displayTitle } from './steps'

describe('displayTitle', () => {
  it('usa o task_id quando existe', () => expect(displayTitle('org__repo-1', 'x.json', 'texto', 'abc')).toBe('org__repo-1'))
  it('sem task_id: nome do arquivo enviado, sem extensão', () => {
    expect(displayTitle(null, 'generic_calc.json', 'The calculator…', 'abc')).toBe('generic_calc')
    expect(displayTitle(undefined, 'run-42.tar.zst', null, 'abc')).toBe('run-42')
  })
  it('sem arquivo: início da 1ª mensagem do usuário', () => {
    expect(displayTitle(null, '', 'The  calculator\nin calc.py is wrong', 'abc')).toBe('The calculator in calc.py is wrong')
    expect(displayTitle(null, null, 'x'.repeat(200), 'abc')).toHaveLength(70)
  })
  it('último recurso: o id', () => expect(displayTitle(null, null, null, 'abc123')).toBe('abc123'))
})
