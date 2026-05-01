import { useState, useRef } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

const DEFAULT_FORM = {
  symbol: 'NIFTY',
  start_date: (() => {
    const d = new Date()
    d.setDate(d.getDate() - 30)
    return d.toISOString().slice(0, 10)
  })(),
  end_date: new Date().toISOString().slice(0, 10),
  capital: '100000',
  sl_pct: '0.01',
  tp_pct: '0.02',
}

function MetricBadge({ label, value, color = '#64748b' }) {
  return (
    <div className="bg-[#0f172a] border border-[#1e293b] rounded p-3 flex flex-col gap-1">
      <span className="text-[10px] font-mono text-[#475569] uppercase tracking-widest">{label}</span>
      <span className="text-sm font-mono font-bold" style={{ color }}>{value}</span>
    </div>
  )
}

function EquityCurve({ equityCurve, benchmark }) {
  if (!equityCurve?.length) return null

  const combined = equityCurve.map((pt, i) => ({
    i,
    ts: pt.ts.slice(0, 10),
    strategy: pt.equity,
    benchmark: benchmark?.[i]?.equity ?? null,
  }))

  return (
    <div className="bg-[#0f172a] border border-[#1e293b] rounded p-4">
      <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-3">
        Equity Curve vs Benchmark
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={combined} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="ts"
            tick={{ fill: '#475569', fontSize: 10, fontFamily: 'monospace' }}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#475569', fontSize: 10, fontFamily: 'monospace' }}
            tickFormatter={v => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v}
          />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', fontFamily: 'monospace', fontSize: 11 }}
            formatter={(v, name) => [`₹${v?.toLocaleString('en-IN')}`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 10, fontFamily: 'monospace' }} />
          <ReferenceLine y={0} stroke="#334155" strokeDasharray="4 4" />
          <Line type="monotone" dataKey="strategy" stroke="#3b82f6" dot={false} strokeWidth={2} name="Strategy" />
          {benchmark?.length > 0 && (
            <Line type="monotone" dataKey="benchmark" stroke="#f59e0b" dot={false} strokeWidth={1.5} strokeDasharray="5 5" name="Buy & Hold" />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function TradeTable({ trades }) {
  if (!trades?.length) return null
  return (
    <div className="bg-[#0f172a] border border-[#1e293b] rounded p-4">
      <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-3">
        Trade Log ({trades.length})
      </div>
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="w-full text-[11px] font-mono border-collapse">
          <thead>
            <tr className="border-b border-[#1e293b]">
              {['Entry', 'Exit', 'Dir', 'Entry ₹', 'Exit ₹', 'P&L'].map(h => (
                <th key={h} className="text-left py-1 px-2 text-[#475569]">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-b border-[#0f172a] hover:bg-[#1e293b]/30">
                <td className="py-1 px-2 text-[#64748b]">{t.entry_ts?.slice(0, 16).replace('T', ' ')}</td>
                <td className="py-1 px-2 text-[#64748b]">{t.exit_ts?.slice(0, 16).replace('T', ' ')}</td>
                <td className={`py-1 px-2 font-bold ${t.direction === 'BUY_CE' ? 'text-green-400' : 'text-red-400'}`}>
                  {t.direction}
                </td>
                <td className="py-1 px-2 text-[#94a3b8]">{t.entry_price?.toLocaleString('en-IN')}</td>
                <td className="py-1 px-2 text-[#94a3b8]">{t.exit_price?.toLocaleString('en-IN')}</td>
                <td className={`py-1 px-2 font-bold ${t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {t.pnl >= 0 ? '+' : ''}₹{t.pnl?.toLocaleString('en-IN')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function BacktestTab() {
  const [form, setForm] = useState(DEFAULT_FORM)
  const [status, setStatus] = useState(null)  // null | 'submitting' | 'polling' | 'complete' | 'error'
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const pollRef = useRef(null)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const handleRun = async () => {
    stopPolling()
    setStatus('submitting')
    setError(null)
    setResult(null)

    try {
      const res = await fetch('/api/backtest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: form.symbol,
          start_date: form.start_date,
          end_date: form.end_date,
          capital: Number(form.capital),
          sl_pct: Number(form.sl_pct),
          tp_pct: Number(form.tp_pct),
        }),
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || `HTTP ${res.status}`)
      }
      const { id } = await res.json()
      setStatus('polling')

      // Poll until complete or error
      pollRef.current = setInterval(async () => {
        try {
          const pr = await fetch(`/api/backtest/${id}`)
          const data = await pr.json()
          if (data.status === 'COMPLETE') {
            stopPolling()
            setResult(data.result)
            setStatus('complete')
          } else if (data.status === 'ERROR') {
            stopPolling()
            setError(data.error || 'Backtest failed')
            setStatus('error')
          }
        } catch {
          stopPolling()
          setError('Polling failed')
          setStatus('error')
        }
      }, 1000)
    } catch (e) {
      setError(e.message)
      setStatus('error')
    }
  }

  const metrics = result?.metrics
  const fmt = (n, decimals = 2) => n == null ? '—' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: decimals })

  return (
    <div className="space-y-4">
      {/* Form */}
      <div className="bg-[#0f172a] border border-[#1e293b] rounded p-4">
        <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-4">
          Backtest Configuration
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Symbol */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono text-[#64748b]">Symbol</label>
            <select
              value={form.symbol}
              onChange={e => set('symbol', e.target.value)}
              className="bg-[#1e293b] border border-[#334155] rounded px-2 py-1.5 text-[11px] font-mono text-white focus:outline-none focus:border-terminal-blue"
            >
              <option value="NIFTY">NIFTY</option>
              <option value="BANKNIFTY">BANKNIFTY</option>
            </select>
          </div>

          {/* Start date */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono text-[#64748b]">Start Date</label>
            <input
              type="date"
              value={form.start_date}
              onChange={e => set('start_date', e.target.value)}
              className="bg-[#1e293b] border border-[#334155] rounded px-2 py-1.5 text-[11px] font-mono text-white focus:outline-none focus:border-terminal-blue"
            />
          </div>

          {/* End date */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono text-[#64748b]">End Date</label>
            <input
              type="date"
              value={form.end_date}
              onChange={e => set('end_date', e.target.value)}
              className="bg-[#1e293b] border border-[#334155] rounded px-2 py-1.5 text-[11px] font-mono text-white focus:outline-none focus:border-terminal-blue"
            />
          </div>

          {/* Capital */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono text-[#64748b]">Capital (₹)</label>
            <input
              type="number"
              value={form.capital}
              onChange={e => set('capital', e.target.value)}
              className="bg-[#1e293b] border border-[#334155] rounded px-2 py-1.5 text-[11px] font-mono text-white focus:outline-none focus:border-terminal-blue"
            />
          </div>

          {/* SL % */}
          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-mono text-[#64748b]">Stop Loss %</label>
            <input
              type="number"
              step="0.005"
              value={form.sl_pct}
              onChange={e => set('sl_pct', e.target.value)}
              className="bg-[#1e293b] border border-[#334155] rounded px-2 py-1.5 text-[11px] font-mono text-white focus:outline-none focus:border-terminal-blue"
            />
          </div>

          {/* Run button */}
          <div className="flex flex-col justify-end">
            <button
              onClick={handleRun}
              disabled={status === 'submitting' || status === 'polling'}
              className="px-4 py-1.5 bg-terminal-blue text-white text-[11px] font-mono font-bold rounded hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {status === 'submitting' ? 'Starting...' : status === 'polling' ? 'Running...' : 'Run Backtest'}
            </button>
          </div>
        </div>
      </div>

      {/* Error */}
      {status === 'error' && error && (
        <div className="bg-red-900/20 border border-red-800 rounded p-3 text-[11px] font-mono text-red-400">
          {error}
        </div>
      )}

      {/* Loading indicator */}
      {(status === 'submitting' || status === 'polling') && (
        <div className="text-[11px] font-mono text-[#475569] text-center py-8 animate-pulse">
          {status === 'submitting' ? 'Submitting backtest...' : 'Running backtest...'}
        </div>
      )}

      {/* Results */}
      {status === 'complete' && metrics && (
        <>
          {/* Metrics grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            <MetricBadge label="Trades" value={metrics.total_trades} color="#94a3b8" />
            <MetricBadge
              label="Win Rate"
              value={`${(metrics.win_rate * 100).toFixed(1)}%`}
              color={metrics.win_rate >= 0.5 ? '#4ade80' : '#f87171'}
            />
            <MetricBadge
              label="Net P&L"
              value={`₹${fmt(metrics.net_pnl)}`}
              color={metrics.net_pnl >= 0 ? '#4ade80' : '#f87171'}
            />
            <MetricBadge
              label="Max Drawdown"
              value={`₹${fmt(metrics.max_drawdown)}`}
              color="#f87171"
            />
            <MetricBadge
              label="Sharpe"
              value={fmt(metrics.sharpe_ratio)}
              color={metrics.sharpe_ratio >= 1 ? '#4ade80' : metrics.sharpe_ratio >= 0 ? '#f59e0b' : '#f87171'}
            />
            <MetricBadge
              label="Profit Factor"
              value={metrics.profit_factor === Infinity ? '∞' : fmt(metrics.profit_factor)}
              color={metrics.profit_factor >= 1.5 ? '#4ade80' : metrics.profit_factor >= 1 ? '#f59e0b' : '#f87171'}
            />
            <MetricBadge
              label="Expectancy"
              value={`₹${fmt(metrics.expectancy)}`}
              color={metrics.expectancy >= 0 ? '#4ade80' : '#f87171'}
            />
          </div>

          <EquityCurve equityCurve={result.equity_curve} benchmark={result.benchmark} />
          <TradeTable trades={result.trades} />
        </>
      )}
    </div>
  )
}
