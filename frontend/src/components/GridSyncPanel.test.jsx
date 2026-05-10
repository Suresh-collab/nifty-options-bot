import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import GridSyncPanel from './GridSyncPanel'

// Mock the Zustand store so we control state without a real DOM environment
vi.mock('../store', () => ({ useStore: vi.fn() }))

import { useStore } from '../store'

const BASE_STORE = { gridSnapshot: {}, gridBookmarks: [] }

describe('GridSyncPanel — acceptance criteria', () => {
  beforeEach(() => {
    useStore.mockReturnValue(BASE_STORE)
  })

  // AC1 — renders without crash
  it('mounts without throwing', () => {
    expect(() => render(<GridSyncPanel />)).not.toThrow()
  })

  // AC2 — "hover any chart" shown when no snapshot data
  it('shows "hover any chart" when gridSnapshot is empty', () => {
    render(<GridSyncPanel />)
    expect(screen.getByText(/hover any chart/i)).toBeInTheDocument()
  })

  // AC3 — confluence strip is always present (even without data)
  it('always renders the Confluence label', () => {
    render(<GridSyncPanel />)
    expect(screen.getByText(/confluence/i)).toBeInTheDocument()
  })

  // AC4 — BUY signal when all four timeframes are UP
  it('shows BUY 100% when all four timeframes are above SuperTrend', () => {
    useStore.mockReturnValue({
      gridSnapshot: {
        '1m':  { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
        '5m':  { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
        '15m': { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
        '1d':  { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
      },
      gridBookmarks: [],
    })
    render(<GridSyncPanel />)
    const badge = screen.getByTestId('confluence-signal')
    expect(badge.textContent).toContain('BUY')
    expect(badge.textContent).toContain('100%')
  })

  // AC5 — SELL signal when all four timeframes are DOWN
  it('shows SELL 100% when all four timeframes are below SuperTrend', () => {
    useStore.mockReturnValue({
      gridSnapshot: {
        '1m':  { close: 24000, st: 24100, open: 24100, high: 24150, low: 23950, _live: true },
        '5m':  { close: 24000, st: 24100, open: 24100, high: 24150, low: 23950, _live: true },
        '15m': { close: 24000, st: 24100, open: 24100, high: 24150, low: 23950, _live: true },
        '1d':  { close: 24000, st: 24100, open: 24100, high: 24150, low: 23950, _live: true },
      },
      gridBookmarks: [],
    })
    render(<GridSyncPanel />)
    const badge = screen.getByTestId('confluence-signal')
    expect(badge.textContent).toContain('SELL')
    expect(badge.textContent).toContain('100%')
  })

  // AC6 — NEUTRAL when 2 UP / 2 DOWN
  it('shows NEUTRAL 50% on equal split', () => {
    useStore.mockReturnValue({
      gridSnapshot: {
        '1m':  { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
        '5m':  { close: 24000, st: 24100, open: 24100, high: 24150, low: 23950, _live: true },
        '15m': { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
        '1d':  { close: 24000, st: 24100, open: 24100, high: 24150, low: 23950, _live: true },
      },
      gridBookmarks: [],
    })
    render(<GridSyncPanel />)
    const badge = screen.getByTestId('confluence-signal')
    expect(badge.textContent).toContain('NEUTRAL')
    expect(badge.textContent).toContain('50%')
  })

  // AC7 — info bar hidden when all snapshots are live (_live: true)
  it('does NOT render info bar when no cursor is active (all live)', () => {
    useStore.mockReturnValue({
      gridSnapshot: {
        '1m': { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
      },
      gridBookmarks: [],
    })
    render(<GridSyncPanel />)
    expect(screen.queryByTestId('info-bar')).not.toBeInTheDocument()
  })

  // AC8 — info bar shown when at least one chart has cursor data (_live: false)
  it('renders info bar when at least one chart has cursor data', () => {
    useStore.mockReturnValue({
      gridSnapshot: {
        '1m': { close: 24176, open: 24100, high: 24250, low: 24050, st: 24100, _live: false },
        '5m': { close: 24150, open: 24050, high: 24200, low: 24010, st: 24080, _live: true },
      },
      gridBookmarks: [],
    })
    render(<GridSyncPanel />)
    expect(screen.getByTestId('info-bar')).toBeInTheDocument()
  })

  // AC9 — bookmark badge shown when bookmarks exist
  it('shows bookmark count badge when gridBookmarks is non-empty', () => {
    useStore.mockReturnValue({
      ...BASE_STORE,
      gridBookmarks: [{ time: 1700000000, id: 'bm_1' }, { time: 1700001000, id: 'bm_2' }],
    })
    render(<GridSyncPanel />)
    expect(screen.getByText(/📌 2/)).toBeInTheDocument()
  })

  // AC10 — partial data: only 2 of 4 charts active, score reflects active count
  it('shows correct score when only 2 of 4 timeframes have data', () => {
    useStore.mockReturnValue({
      gridSnapshot: {
        '1m': { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
        '5m': { close: 24200, st: 24100, open: 24100, high: 24250, low: 24050, _live: true },
      },
      gridBookmarks: [],
    })
    render(<GridSyncPanel />)
    const badge = screen.getByTestId('confluence-signal')
    expect(badge.textContent).toContain('100%')
    expect(badge.textContent).toContain('BUY')
  })
})
