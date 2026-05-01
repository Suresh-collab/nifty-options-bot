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
})

describe('BacktestTab', () => {
  it('renders form controls including run button', () => {
    render(<BacktestTab />)
    expect(screen.getByText('Backtest Configuration')).toBeInTheDocument()
    expect(screen.getByText('Run Backtest')).toBeInTheDocument()
    expect(screen.getByText('Symbol')).toBeInTheDocument()
    expect(screen.getByText('Capital (₹)')).toBeInTheDocument()
  })

  it('run button starts enabled', () => {
    render(<BacktestTab />)
    expect(screen.getByText('Run Backtest')).not.toBeDisabled()
  })

  it('disables button while running', async () => {
    // Never-resolving fetch keeps the component in running state
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<BacktestTab />)
    await act(async () => {
      fireEvent.click(screen.getByText('Run Backtest'))
    })
    expect(screen.getByRole('button', { name: /Running/i })).toBeDisabled()
  })

  it('renders metrics and trade log after successful backtest', async () => {
    // POST returns COMPLETE result directly (synchronous API)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: 'run-1',
        status: 'COMPLETE',
        result: MOCK_RESULT,
      }),
    }))

    render(<BacktestTab />)

    await act(async () => {
      fireEvent.click(screen.getByText('Run Backtest'))
    })

    await waitFor(() => {
      expect(screen.getByText('Trades')).toBeInTheDocument()
    })

    expect(screen.getByText('Win Rate')).toBeInTheDocument()
    expect(screen.getByText('Net P&L')).toBeInTheDocument()
  })

  it('shows error message when POST fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'symbol must be NIFTY or BANKNIFTY' }),
    }))

    render(<BacktestTab />)

    await act(async () => {
      fireEvent.click(screen.getByText('Run Backtest'))
    })

    await waitFor(() => {
      expect(screen.queryByText('symbol must be NIFTY or BANKNIFTY')).toBeTruthy()
    })
  })

  it('shows row counts after Load Market Data succeeds', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: 'ok',
        summary: { 'NIFTY/5m': 1234, 'NIFTY/1d': 500 },
        errors: {},
      }),
    }))

    render(<BacktestTab />)

    await act(async () => {
      fireEvent.click(screen.getByText('Load Market Data'))
    })

    await waitFor(() => {
      expect(screen.getByText(/1234 rows/)).toBeInTheDocument()
    })
  })

  it('shows error detail when Load Market Data returns 0 rows with error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: 'ok',
        summary: { 'NIFTY/5m': 0 },
        errors: { 'NIFTY/5m': 'no data returned by yfinance or direct API' },
      }),
    }))

    render(<BacktestTab />)

    await act(async () => {
      fireEvent.click(screen.getByText('Load Market Data'))
    })

    await waitFor(() => {
      expect(screen.getByText(/no data returned/)).toBeInTheDocument()
    })
  })
})
