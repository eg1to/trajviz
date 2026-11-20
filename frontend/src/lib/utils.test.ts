import { describe, expect, it } from 'vitest'
import { roundTicks } from './utils'

describe('roundTicks', () => {
  it('valores redondos até cobrir o máximo', () => {
    expect(roundTicks(27.3)).toEqual([0, 10, 20, 30])
    expect(roundTicks(25.6)).toEqual([0, 10, 20, 30])
    expect(roundTicks(41)).toEqual([0, 10, 20, 30, 40, 50])
    expect(roundTicks(12)).toEqual([0, 5, 10, 15])
    expect(roundTicks(0)).toEqual([0, 5])
  })
})
