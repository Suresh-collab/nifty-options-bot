import { useEffect, useState } from 'react'
import { useStore } from '../store'

export default function TradeHistory() {
  const { tradeHistory, tradeStats, fetchTradeHistory, exitPaperTrade } = useStore()
  const [exitId, setExitId] = useState(null)
  const [exitLtp, setExitLtp] = useState('')

  useEffect(() => {
    fetchTradeHistory()
  }, [])

  const handleExit = async (id) => {
    if (!exitLtp || isNaN(Number(exitLtp))) return
    await exitPaperTrade(id, Number(exitLtp))
    setExitId(null)
    setExitLtp('')
  }

  return (
    <div className="bg-terminal-surface border border-terminal-border rounded-lg p-5">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-mono text-terminal-dim uppercase tracking-widest">Paper Trade History</span>
        <button onClick={fetchTradeHistory}
          className="text-xs font-mono text-terminal-dim hover:text-terminal-blue transition-colors"
        >↻ Refresh</button>
      </div>

      {/* Stats bar */}
      {tradeStats && tradeStats.total_trades > 0 && (
        <div className="grid grid-cols-4 gap-2 mb-4">
          {[
            { l: 'Win Rate', v: `${tradeStats.win_rate_pct}%`, c: tradeStats.win_rate_pct >= 50 ? 'text-terminal-green' : 'text-terminal-red' },
            { l: 'Total P&L', v: `₹${tradeStats.total_pnl?.toLocaleString('en-IN')}`, c: tradeStats.total_pnl >= 0 ? 'text-terminal-green' : 'text-terminal-red' },
            { l: 'Best Trade', v: `+₹${tradeStats.best_trade?.toLocaleString('en-IN')}`, c: 'text-terminal-green' },
            { l: 'Worst Trade', v: `₹${tradeStats.worst_trade?.toLocaleString('en-IN')}`, c: 'text-terminal-red' },
          ].map(({ l, v, c }) => (
            <div key={l} className="bg-terminal-bg/60 rounded p-2.5 border border-terminal-border text-center">
              <div className="text-xs font-mono text-terminal-dim">{l}</div>
              <div className={`text-sm font-mono font-bold mt-0.5 ${c}`}>{v}</div>
            </div>
          ))}
        </div>
      )}

      {/* Trade table */}
      {tradeHistory.length === 0 ? (
        <p className="text-terminal-dim text-sm font-mono text-center py-6">
          No paper trades yet — confirm a signal above to start tracking
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim">
                {['#', 'Ticker', 'Direction', 'Strike', 'Entry', 'Exit', 'P&L', 'Status', ''].map(h => (
                  <th key={h} className="pb-2 text-left font-medium pr-3">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tradeHistory.map((t) => {
                const isBull = t.direction === 'BUY_CE'
                const isOpen = t.status === 'OPEN'
                const pnlColor = t.pnl > 0 ? 'text-terminal-green' : t.pnl < 0 ? 'text-terminal-red' : 'text-terminal-dim'

                return (
                  <tr key={t.id} className="border-b border-terminal-border/30 hover:bg-terminal-bg/40 transition-colors">
                    <td className="py-2 pr-3 text-terminal-dim">{t.id}</td>
                    <td className="py-2 pr-3 text-terminal-text">{t.ticker}</td>
                    <td className={`py-2 pr-3 font-medium ${isBull ? 'text-terminal-green' : 'text-terminal-red'}`}>
                      {isBull ? '▲ CE' : '▼ PE'}
                    </td>
                    <td className="py-2 pr-3 text-terminal-text">{t.strike?.toLocaleString('en-IN')}</td>
                    <td className="py-2 pr-3 text-terminal-text">{t.entry_ltp}</td>
                    <td className="py-2 pr-3 text-terminal-text">{t.exit_ltp ?? '—'}</td>
                    <td className={`py-2 pr-3 font-bold ${pnlColor}`}>
                      {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}₹${t.pnl?.toLocaleString('en-IN')}` : '—'}
                    </td>
                    <td className="py-2 pr-3">
                      <span className={`px-1.5 py-0.5 rounded text-xs ${isOpen ? 'bg-terminal-blue/20 text-terminal-blue' : 'bg-terminal-muted text-terminal-dim'}`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="py-2">
                      {isOpen && (
                        exitId === t.id ? (
                          <div className="flex gap-1">
                            <input
                              type="number"
                              placeholder="exit LTP"
                              value={exitLtp}
                              onChange={e => setExitLtp(e.target.value)}
                              className="w-20 bg-terminal-bg border border-terminal-border rounded px-1.5 py-0.5
                                text-terminal-text text-xs focus:outline-none focus:border-terminal-blue"
                            />
                            <button onClick={() => handleExit(t.id)}
                              className="px-2 py-0.5 rounded bg-terminal-green/20 border border-terminal-green
                                text-terminal-green hover:bg-terminal-green hover:text-terminal-bg transition-all"
                            >✓</button>
                            <button onClick={() => setExitId(null)}
                              className="px-2 py-0.5 rounded border border-terminal-border text-terminal-dim hover:text-terminal-text"
                            >✕</button>
                          </div>
                        ) : (
                          <button onClick={() => setExitId(t.id)}
                            className="px-2 py-0.5 rounded border border-terminal-amber/50 text-terminal-amber
                              text-xs hover:bg-terminal-amber/20 transition-all"
                          >Exit</button>
                        )
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
