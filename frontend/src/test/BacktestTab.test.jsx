import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import BacktestTab from '../components/BacktestTab.jsx'

const MOCK_RESULT = {
  trades: [
    {
      entry_ts: '2024-01-02T09:15:00+00:00',
      exit_ts: '2024-01-02T10:00:00+00:00',
      symbol: 'NIFTY',
      direction: 'BUY_CE',
      entry_price: 21800,
      exit_price: 21900,
      qty: 1,
      pnl: 100,
    },
  ],
  metrics: {
    total_trades: 1,
    win_rate: 1.0,
    net_pnl: 100,
    profit_factor: 4.125,
    expectancy: 100,
    max_drawdown: 0,
    sharpe_ratio: 0,
  },
  equity_curve: [{ ts: '2024-01-02T10:00:00+00:00', equity: 100 }],
  benchmark: [{ ts: '2024-01-02T10:00:00+00:00', equity: 50 }],
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('BacktestTab', () => {
  it('renders form controls including run button', () => {
    render(<BacktestTab />)
    // CSS transforms text to uppercase visually — DOM has the actual text
    expect(screen.getByText('Backtest Configuration')).toBeInTheDocument()
    expect(screen.getByText('Run Backtest')).toBeInTheDocument()
    expect(screen.getByText('Symbol')).toBeInTheDocument()
    expect(screen.getByText('Capital (₹)')).toBeInTheDocument()
  })

  it('run button starts enabled', () => {
    render(<BacktestTab />)
    expect(screen.getByText('Run Backtest')).not.toBeDisabled()
  })

  it('disables button immediately on click', async () => {
    // Never-resolving fetch keeps the component in submitting state indefinitely
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))

    render(<BacktestTab />)
    await act(async () => {
      fireEvent.click(screen.getByText('Run Backtest'))
    })

    expect(screen.getByRole('button', { name: /Starting|Running/i })).toBeDisabled()
  })

  it('renders equity curve and metrics after polling completes', async () => {
    vi.useFakeTimers()

    vi.stubGlobal('fetch', vi.fn()
      // POST → PENDING
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'run-1', status: 'PENDING' }) })
      // GET poll → COMPLETE (first and any subsequent poll)
      .mockResolvedValue({ ok: true, json: async () => ({ id: 'run-1', status: 'COMPLETE', result: MOCK_RESULT }) })
    )

    render(<BacktestTab />)

    // Submit — flushes microtasks from the POST (fetch mock resolves immediately)
    await act(async () => {
      fireEvent.click(screen.getByText('Run Backtest'))
    })

    // runAllTimersAsync: fires the setInterval callback AND awaits its async body
    // Our callback calls fetch (resolves immediately) → clears interval → sets state COMPLETE
    await act(async () => {
      await vi.runAllTimersAsync()
    })

    // Component should now be in 'complete' state
    expect(screen.getByText('Trades')).toBeInTheDocument()
    expect(screen.getByText('Win Rate')).toBeInTheDocument()
    expect(screen.getByText('Net P&L')).toBeInTheDocument()
  }, 10_000)

  it('shows error message when POST returns error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'symbol must be NIFTY or BANKNIFTY' }),
    }))

    render(<BacktestTab />)

    await act(async () => {
      fireEvent.click(screen.getByText('Run Backtest'))
    })

    await waitFor(
      () => expect(screen.queryByText('symbol must be NIFTY or BANKNIFTY')).toBeTruthy(),
      { timeout: 2000 }
    )
  })
})
