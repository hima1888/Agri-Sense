import { describe, expect, it } from 'vitest'
import { localDate } from './dates'

describe('localDate', () => {
  it('uses the local calendar day, not the UTC one', () => {
    const justAfterMidnight = new Date(2026, 10, 15, 0, 37) // 15 Nov, 00:37 local time
    expect(localDate(justAfterMidnight)).toBe('2026-11-15')
    expect(localDate(new Date(2026, 0, 5, 23, 59))).toBe('2026-01-05')
  })
})
