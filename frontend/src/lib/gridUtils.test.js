import { describe, it, expect } from 'vitest'
import {
  getTrendDirection,
  computeAlignment,
  formatISTTime,
  hasCursorData,
  GRID_INTERVALS,
} from './gridUtils'

// ── getTrendDirection ────────────────────────────────────────────────────────

describe('getTrendDirection', () => {
  it('returns null when close is null', () => {
    expect(getTrendDirection(null, 24100)).toBeNull()
  })

  it('returns null when stValue is null', () => {
    expect(getTrendDirection(24200, null)).toBeNull()
  })

  it('returns null when both inputs are null', () => {
    expect(getTrendDirection(null, null)).toBeNull()
  })

  it('returns null when stValue is undefined', () => {
    expect(getTrendDirection(24200, undefined)).toBeNull()
  })

  it('returns UP when close > stValue', () => {
    expect(getTrendDirection(24200, 24100)).toBe('UP')
  })

  it('returns DOWN when close < stValue', () => {
    expect(getTrendDirection(24000, 24100)).toBe('DOWN')
  })

  it('returns DOWN when close === stValue (on-line is bearish by convention)', () => {
    expect(getTrendDirection(24100, 24100)).toBe('DOWN')
  })

  it('works with fractional prices', () => {
    expect(getTrendDirection(24100.5, 24100.2)).toBe('UP')
    expect(getTrendDirection(24100.1, 24100.2)).toBe('DOWN')
  })

  it('works with large index values (Nifty range)', () => {
    expect(getTrendDirection(24317.85, 24200.10)).toBe('UP')
    expect(getTrendDirection(24100.00, 24200.10)).toBe('DOWN')
  })
})

// ── computeAlignment ─────────────────────────────────────────────────────────

describe('computeAlignment', () => {
  it('returns null signal and zero score when snapshot is empty', () => {
    const r = computeAlignment({})
    expect(r.signal).toBeNull()
    expect(r.score).toBe(0)
    expect(r.active).toBe(0)
    expect(r.up).toBe(0)
    expect(r.down).toBe(0)
  })

  it('all four timeframes UP → BUY 100%', () => {
    const snap = Object.fromEntries(GRID_INTERVALS.map(iv => [iv, { close: 24200, st: 24100 }]))
    const r = computeAlignment(snap)
    expect(r.signal).toBe('BUY')
    expect(r.score).toBe(100)
    expect(r.up).toBe(4)
    expect(r.down).toBe(0)
    expect(r.active).toBe(4)
  })

  it('all four timeframes DOWN → SELL 100%', () => {
    const snap = Object.fromEntries(GRID_INTERVALS.map(iv => [iv, { close: 24000, st: 24100 }]))
    const r = computeAlignment(snap)
    expect(r.signal).toBe('SELL')
    expect(r.score).toBe(100)
    expect(r.up).toBe(0)
    expect(r.down).toBe(4)
  })

  it('2 UP, 2 DOWN → NEUTRAL 50%', () => {
    const snap = {
      '1m':  { close: 24200, st: 24100 },
      '5m':  { close: 24000, st: 24100 },
      '15m': { close: 24200, st: 24100 },
      '1d':  { close: 24000, st: 24100 },
    }
    const r = computeAlignment(snap)
    expect(r.signal).toBe('NEUTRAL')
    expect(r.score).toBe(50)
    expect(r.up).toBe(2)
    expect(r.down).toBe(2)
  })

  it('3 DOWN, 1 UP → SELL 75%', () => {
    const snap = {
      '1m':  { close: 24200, st: 24100 },  // UP
      '5m':  { close: 24000, st: 24100 },  // DOWN
      '15m': { close: 24000, st: 24100 },  // DOWN
      '1d':  { close: 24000, st: 24100 },  // DOWN
    }
    const r = computeAlignment(snap)
    expect(r.signal).toBe('SELL')
    expect(r.score).toBe(75)
    expect(r.down).toBe(3)
  })

  it('3 UP, 1 DOWN → BUY 75%', () => {
    const snap = {
      '1m':  { close: 24200, st: 24100 },  // UP
      '5m':  { close: 24200, st: 24100 },  // UP
      '15m': { close: 24000, st: 24100 },  // DOWN
      '1d':  { close: 24200, st: 24100 },  // UP
    }
    const r = computeAlignment(snap)
    expect(r.signal).toBe('BUY')
    expect(r.score).toBe(75)
  })

  it('partial data (2 of 4 charts active) → score based on active only', () => {
    const snap = {
      '1m': { close: 24200, st: 24100 },
      '5m': { close: 24200, st: 24100 },
    }
    const r = computeAlignment(snap)
    expect(r.signal).toBe('BUY')
    expect(r.active).toBe(2)
    expect(r.score).toBe(100)
  })

  it('null snapshot entries are treated as inactive (not counted)', () => {
    const snap = { '1m': null, '5m': { close: 24000, st: 24100 } }
    const r = computeAlignment(snap)
    expect(r.active).toBe(1)
    expect(r.signal).toBe('SELL')
    expect(r.directions['1m']).toBeNull()
  })

  it('snapshot with null st (no SuperTrend computed yet) treats chart as inactive', () => {
    const snap = { '1m': { close: 24200, st: null } }
    const r = computeAlignment(snap)
    expect(r.directions['1m']).toBeNull()
    expect(r.active).toBe(0)
    expect(r.signal).toBeNull()
  })

  it('directions object always has a key for every GRID_INTERVAL', () => {
    const r = computeAlignment({})
    for (const iv of GRID_INTERVALS) {
      expect(r.directions).toHaveProperty(iv)
    }
  })
})

// ── formatISTTime ─────────────────────────────────────────────────────────────

describe('formatISTTime', () => {
  it('returns --:-- for null', () => {
    expect(formatISTTime(null)).toBe('--:--')
  })

  it('returns --:-- for 0', () => {
    expect(formatISTTime(0)).toBe('--:--')
  })

  it('formats a UTC unix-seconds timestamp to HH:MM', () => {
    // 2024-01-15 09:15:00 UTC  (IST timestamps are pre-shifted in this app,
    // formatISTTime just reads UTC hours/minutes from the epoch)
    const ts = Date.UTC(2024, 0, 15, 9, 15, 0) / 1000
    expect(formatISTTime(ts)).toBe('09:15')
  })

  it('zero-pads single-digit hours and minutes', () => {
    const ts = Date.UTC(2024, 0, 15, 3, 5, 0) / 1000
    expect(formatISTTime(ts)).toBe('03:05')
  })
})

// ── hasCursorData ─────────────────────────────────────────────────────────────

describe('hasCursorData', () => {
  it('returns false when snapshot is empty', () => {
    expect(hasCursorData({})).toBe(false)
  })

  it('returns false when all entries are live snapshots', () => {
    const snap = { '1m': { close: 24200, st: 24100, _live: true } }
    expect(hasCursorData(snap)).toBe(false)
  })

  it('returns true when at least one entry is a cursor snapshot', () => {
    const snap = {
      '1m': { close: 24200, st: 24100, _live: false },
      '5m': { close: 24000, st: 24100, _live: true },
    }
    expect(hasCursorData(snap)).toBe(true)
  })

  it('returns false when entries are null', () => {
    expect(hasCursorData({ '1m': null })).toBe(false)
  })
})
