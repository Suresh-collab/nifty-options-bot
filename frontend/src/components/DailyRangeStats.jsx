import { useEffect } from 'react'
import { useStore } from '../store'

function fmt(n) {
  if (n == null) return '—'
  return n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

function StatBlock({ label, data, isDay }) {
  if (!data) {
    return (
      <div className="flex flex-col items-start px-4 py-2 border-r border-[#1e293b] last:border-r-0 min-w-[140px]">
        <div className="text-[9px] font-mono text-[#475569] uppercase tracking-widest mb-1">{label}</div>
        <div className="text-[10px] font-mono text-[#334155]">No data</div>
      </div>
    )
  }

  const { high, low, open, close, change_pts, change_pct } = data
  const isUp = change_pts != null ? change_pts >= 0 : (close ?? 0) >= (open ?? 0)
  const changeColor = isUp ? 'text-[#22c55e]' : 'text-[#ef4444]'
  const rangeColor = isUp ? '#22c55e33' : '#ef444433'

  return (
    <div className="flex flex-col items-start px-4 py-2 border-r border-[#1e293b] last:border-r-0 min-w-[155px]">
      <div className="text-[9px] font-mono text-[#475569] uppercase tracking-widest mb-1.5">{label}</div>

      <div className="flex items-center gap-2">
        <span className="text-[11px] font-mono font-semibold text-[#22c55e]">H {fmt(high)}</span>
        <span className="text-[10px] font-mono text-[#334155]">/</span>
        <span className="text-[11px] font-mono font-semibold text-[#ef4444]">L {fmt(low)}</span>
      </div>

      {isDay && change_pts != null && (
        <div className={`text-[10px] font-mono mt-0.5 ${changeColor}`}>
          {isUp ? '+' : ''}{fmt(change_pts)} ({isUp ? '+' : ''}{change_pct?.toFixed(2)}%)
        </div>
      )}

      {/* Visual range bar */}
      {high != null && low != null && high !== low && (
        <div className="mt-1.5 w-full h-1 rounded-full bg-[#1e293b] overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{ width: '100%', background: `linear-gradient(to right, #ef4444, #22c55e)` }}
          />
        </div>
      )}
    </div>
  )
}

export default function DailyRangeStats() {
  const { ticker, dailyStats, dailyStatsLoading, fetchDailyStats } = useStore()

  useEffect(() => {
    fetchDailyStats()
    const iv = setInterval(fetchDailyStats, 5 * 60 * 1000)
    return () => clearInterval(iv)
  }, [ticker])

  if (!dailyStats && !dailyStatsLoading) return null

  return (
    <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg overflow-hidden">
      <div className="flex items-stretch overflow-x-auto">

        {/* Label column */}
        <div className="flex flex-col justify-center px-3 py-2 border-r border-[#1e293b] min-w-[90px] shrink-0">
          <div className="text-[9px] font-mono text-[#475569] uppercase tracking-widest">Day Range</div>
          <div className="text-[10px] font-mono text-terminal-blue font-semibold mt-0.5">{ticker}</div>
          {dailyStats?.candle_count != null && (
            <div className="text-[9px] font-mono text-[#334155] mt-0.5">{dailyStats.candle_count} bars</div>
          )}
        </div>

        {dailyStatsLoading && !dailyStats ? (
          <div className="flex items-center px-4 py-2 text-[10px] font-mono text-[#475569]">
            Loading…
          </div>
        ) : dailyStats ? (
          <>
            <StatBlock label="Open Candle 9:15" data={dailyStats.opening_candle} />
            <StatBlock label="First 5 Min"      data={dailyStats.first_5min} />
            <StatBlock label="First 15 Min"     data={dailyStats.first_15min} />
            <StatBlock label="Day So Far"       data={dailyStats.day} isDay />
          </>
        ) : (
          <div className="flex items-center px-4 py-2 text-[10px] font-mono text-[#475569]">
            Pre-market — data available after 9:15 IST
          </div>
        )}
      </div>
    </div>
  )
}
