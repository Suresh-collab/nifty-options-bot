import { useEffect, useState } from 'react'
import { useStore } from './store'
import TickerBar from './components/TickerBar'
import MarketStatusBar from './components/MarketStatusBar'
import TickerSelector from './components/TickerSelector'
import SignalCard from './components/SignalCard'
import IndicatorGrid from './components/IndicatorGrid'
import BudgetOptimizer from './components/BudgetOptimizer'
import OptionChart from './components/OptionChart'
import TradeConfirmModal from './components/TradeConfirmModal'
import TradeHistory from './components/TradeHistory'
import LiveChart from './components/LiveChart'
import MarketNews from './components/MarketNews'

export default function App() {
  const { fetchSignal, fetchMarketStatus, fetchTradeHistory, ticker, signalData } = useStore()
  const [viewMode, setViewMode] = useState('single')

  useEffect(() => {
    fetchSignal()
    fetchMarketStatus()
    fetchTradeHistory()

    // Auto-refresh every 3 minutes during market hours (IST)
    const iv = setInterval(() => {
      const now = new Date()
      // Convert to IST regardless of browser timezone
      const istStr = now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata', hour12: false })
      const istDate = new Date(istStr)
      const h = istDate.getHours(), m = istDate.getMinutes()
      const inMarket = (h > 9 || (h === 9 && m >= 15)) && (h < 15 || (h === 15 && m <= 30))
      if (inMarket) fetchSignal()
    }, 3 * 60 * 1000)

    return () => clearInterval(iv)
  }, [])

  const expiry = signalData?.signal?.expiry

  return (
    <div className="min-h-screen bg-[#0a0e1a]">
      {/* Scrolling ticker bar (Groww-style) */}
      <TickerBar />

      {/* Top nav */}
      <header className="bg-[#0f172a] border-b border-[#1e293b]">
        <div className="max-w-[1400px] mx-auto px-4 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded bg-terminal-blue/20 border border-terminal-blue flex items-center justify-center">
              <span className="text-terminal-blue text-xs font-mono font-bold">N</span>
            </div>
            <span className="font-mono font-bold text-white tracking-wide">NIFTY OPTIONS BOT</span>
            <span className="text-[10px] font-mono text-[#475569] border border-[#334155] px-2 py-0.5 rounded">
              PAPER TRADING v2.0
            </span>
          </div>
          <div className="text-[10px] font-mono text-[#475569]">
            Powered by AI · No broker required
          </div>
        </div>
      </header>

      <MarketStatusBar />

      <main className="max-w-[1400px] mx-auto px-4 py-4 space-y-4">
        {/* Controls row */}
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <TickerSelector />
            {/* View mode toggle */}
            <div className="flex items-center bg-[#0f172a] border border-[#1e293b] rounded overflow-hidden">
              <button
                onClick={() => setViewMode('single')}
                className={`px-3 py-1.5 text-[11px] font-mono transition-all ${
                  viewMode === 'single'
                    ? 'bg-terminal-blue text-white'
                    : 'text-[#64748b] hover:text-white hover:bg-white/5'
                }`}
                title="Single chart"
              >
                ⬜ 1
              </button>
              <button
                onClick={() => setViewMode('grid')}
                className={`px-3 py-1.5 text-[11px] font-mono transition-all border-l border-[#1e293b] ${
                  viewMode === 'grid'
                    ? 'bg-terminal-blue text-white'
                    : 'text-[#64748b] hover:text-white hover:bg-white/5'
                }`}
                title="4-chart grid (1m · 5m · 15m · 1D)"
              >
                ⊞ 4
              </button>
            </div>
          </div>
          <div className="text-[10px] font-mono text-[#475569]">
            For educational purposes only — not financial advice
          </div>
        </div>

        {viewMode === 'grid' ? (
          /* ── 4-chart grid: 1m · 5m · 15m · 1D ── */
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { label: '1 MIN', interval: '1m' },
              { label: '5 MIN', interval: '5m' },
              { label: '15 MIN', interval: '15m' },
              { label: 'DAILY', interval: '1d' },
            ].map(({ label, interval }) => (
              <div key={interval}>
                <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-1 px-1">
                  {label}
                </div>
                <LiveChart defaultInterval={interval} compact={true} />
              </div>
            ))}
          </div>
        ) : (
          /* ── Single chart: original layout ── */
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Left col: chart + signal (8 cols) */}
            <div className="lg:col-span-8 space-y-4">
              <LiveChart />
              <SignalCard />
              <div>
                <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-2">
                  Technical Indicators
                </div>
                <IndicatorGrid />
              </div>
            </div>

            {/* Right col: optimizer + option chart + news (4 cols) */}
            <div className="lg:col-span-4 space-y-4">
              <BudgetOptimizer />
              <OptionChart ticker={ticker} expiry={expiry} />
              <MarketNews />
            </div>
          </div>
        )}

        {/* Trade history */}
        <TradeHistory />

        {/* Disclaimer */}
        <div className="text-[10px] font-mono text-[#334155] text-center pb-4">
          This tool is for educational and paper trading purposes only.
          Options trading involves significant risk. Always do your own research.
          Not SEBI registered. Not financial advice.
        </div>
      </main>

      <TradeConfirmModal />
    </div>
  )
}
