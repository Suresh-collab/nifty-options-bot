import { useEffect } from 'react'
import { useStore } from '../store'
import {
  ComposedChart, LineChart, AreaChart,
  Line, Area, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Legend,
} from 'recharts'

// ─── helpers ────────────────────────────────────────────────────────────────

function fmt(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
  } catch { return iso.slice(0, 10) }
}

function fmtINR(n) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : n > 0 ? '+' : ''
  return `${sign}₹${abs.toLocaleString('en-IN')}`
}

function StatCard({ label, value, sub, color }) {
  return (
    <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
      <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-1">{label}</div>
      <div className={`text-xl font-mono font-bold ${color || 'text-white'}`}>{value}</div>
      {sub && <div className="text-[10px] font-mono text-[#64748b] mt-0.5">{sub}</div>}
    </div>
  )
}

const DARK_TOOLTIP = {
  contentStyle: { background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11, fontFamily: 'monospace' },
  labelStyle: { color: '#94a3b8' },
  itemStyle: { color: '#e2e8f0' },
}

// ─── component ──────────────────────────────────────────────────────────────

export default function AnalyticsTab() {
  const { analyticsData, analyticsLoading, fetchAnalytics } = useStore()

  useEffect(() => { fetchAnalytics() }, [])

  if (analyticsLoading) {
    return (
      <div className="flex items-center justify-center h-48 text-[#64748b] font-mono text-sm">
        Loading analytics…
      </div>
    )
  }

  if (!analyticsData || analyticsData.total_trades === 0) {
    return (
      <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-8 text-center">
        <div className="text-[#475569] font-mono text-sm">No closed trades yet.</div>
        <div className="text-[#334155] font-mono text-xs mt-1">Enter and exit paper trades to see analytics.</div>
      </div>
    )
  }

  const {
    total_trades, total_pnl, win_rate, max_drawdown_pct,
    current_drawdown_pct, avg_win, avg_loss, profit_factor,
    best_streak, worst_streak, equity_curve, drawdown_series,
  } = analyticsData

  const pnlColor = total_pnl >= 0 ? 'text-green-400' : 'text-red-400'

  // Recharts needs short x-axis labels
  const curveData  = (equity_curve  || []).map(p => ({ ...p, label: fmt(p.time) }))
  const ddData     = (drawdown_series || []).map(p => ({ ...p, label: fmt(p.time) }))

  return (
    <div className="space-y-6">
      {/* ── stat strip ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
        <StatCard label="Total P&L"    value={fmtINR(total_pnl)}          color={pnlColor} />
        <StatCard label="Trades"       value={total_trades}                color="text-white" />
        <StatCard label="Win Rate"     value={`${win_rate}%`}              color={win_rate >= 50 ? 'text-green-400' : 'text-red-400'} />
        <StatCard label="Max Drawdown" value={`${max_drawdown_pct}%`}      color={max_drawdown_pct > 10 ? 'text-red-400' : 'text-yellow-400'} />
        <StatCard label="Cur. Drawdown" value={`${current_drawdown_pct}%`} color={current_drawdown_pct > 5 ? 'text-red-400' : 'text-green-400'} />
        <StatCard label="Profit Factor" value={profit_factor > 0 ? profit_factor : '—'} color={profit_factor >= 1.5 ? 'text-green-400' : 'text-[#94a3b8]'} />
        <StatCard label="Best Streak"  value={`${best_streak}W`}          color="text-green-400" />
        <StatCard label="Worst Streak" value={`${worst_streak}L`}          color="text-red-400" />
      </div>

      {/* ── equity curve ─────────────────────────────────────────────────── */}
      <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
        <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-4">
          Equity Curve — Cumulative P&L (₹)
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={curveData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="label" tick={{ fill: '#475569', fontSize: 10, fontFamily: 'monospace' }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: '#475569', fontSize: 10, fontFamily: 'monospace' }} tickFormatter={v => `₹${(v/1000).toFixed(1)}k`} />
            <Tooltip {...DARK_TOOLTIP} formatter={(v, n) => [fmtINR(v), n === 'cumulative_pnl' ? 'Cumulative' : 'Trade P&L']} />
            <ReferenceLine y={0} stroke="#334155" strokeDasharray="4 2" />
            <Bar dataKey="pnl" name="Trade P&L" fill="#22c55e" opacity={0.5}
              label={false}
              // negative bars in red — Recharts doesn't support conditional fill via prop here
            />
            <Line type="monotone" dataKey="cumulative_pnl" name="Cumulative" stroke="#3b82f6" strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="text-[9px] font-mono text-[#334155] mt-2 text-right">
          avg win {fmtINR(avg_win)} · avg loss {fmtINR(avg_loss)}
        </div>
      </div>

      {/* ── drawdown chart ───────────────────────────────────────────────── */}
      <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
        <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-4">
          Drawdown from Peak (%)
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <AreaChart data={ddData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="label" tick={{ fill: '#475569', fontSize: 10, fontFamily: 'monospace' }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: '#475569', fontSize: 10, fontFamily: 'monospace' }} tickFormatter={v => `${v}%`} domain={[0, 'auto']} reversed />
            <Tooltip {...DARK_TOOLTIP} formatter={v => [`${v}%`, 'Drawdown']} />
            <Area type="monotone" dataKey="drawdown_pct" stroke="#ef4444" fill="#ef444420" strokeWidth={1.5} />
          </AreaChart>
        </ResponsiveContainer>
        <div className="text-[9px] font-mono text-[#334155] mt-2 text-right">
          max drawdown {max_drawdown_pct}% · current {current_drawdown_pct}%
        </div>
      </div>
    </div>
  )
}
