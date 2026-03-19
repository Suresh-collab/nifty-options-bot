import { useEffect } from 'react'
import { useStore } from './store'
import MarketStatusBar from './components/MarketStatusBar'
import TickerSelector from './components/TickerSelector'
import SignalCard from './components/SignalCard'
import IndicatorGrid from './components/IndicatorGrid'
import BudgetOptimizer from './components/BudgetOptimizer'
import TradeConfirmModal from './components/TradeConfirmModal'
import TradeHistory from './components/TradeHistory'
import LiveChart from './components/LiveChart'
import MarketNews from './components/MarketNews'

export default function App() {
  const { fetchSignal, fetchMarketStatus, fetchTradeHistory } = useStore()

  useEffect(() => {
    fetchSignal()
    fetchMarketStatus()
    fetchTradeHistory()

    // Auto-refresh every 3 minutes during market hours
    const iv = setInterval(() => {
      const now = new Date()
      const h = now.getHours(), m = now.getMinutes()
      const inMarket = (h > 9 || (h === 9 && m >= 15)) && (h < 15 || (h === 15 && m <= 30))
      if (inMarket) fetchSignal()
    }, 3 * 60 * 1000)

    return () => clearInterval(iv)
  }, [])

  return (
    <div className="min-h-screen bg-terminal-bg">
      {/* Top nav */}
      <header className="bg-terminal-surface border-b border-terminal-border">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded bg-terminal-blue/20 border border-terminal-blue flex items-center justify-center">
              <span className="text-terminal-blue text-xs font-mono font-bold">N</span>
            </div>
            <span className="font-mono font-bold text-terminal-text tracking-wide">NIFTY OPTIONS BOT</span>
            <span className="text-xs font-mono text-terminal-dim border border-terminal-border px-2 py-0.5 rounded">
              PAPER TRADING v1.0
            </span>
          </div>
          <div className="text-xs font-mono text-terminal-dim">
            Powered by Claude AI · No broker required
          </div>
        </div>
      </header>

      <MarketStatusBar />

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* Controls row */}
        <div className="flex items-center justify-between flex-wrap gap-4">
          <TickerSelector />
          <div className="text-xs font-mono text-terminal-dim">
            ⚠ For educational purposes only — not financial advice
          </div>
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Left col: chart + signal + indicators */}
          <div className="lg:col-span-2 space-y-4">
            <LiveChart />
            <SignalCard />
            <div>
              <div className="text-xs font-mono text-terminal-dim uppercase tracking-widest mb-3">
                Technical Indicators
              </div>
              <IndicatorGrid />
            </div>
          </div>

          {/* Right col: budget optimizer + news */}
          <div className="space-y-4">
            <BudgetOptimizer />
            <MarketNews />
          </div>
        </div>

        {/* Trade history */}
        <TradeHistory />

        {/* Disclaimer */}
        <div className="text-xs font-mono text-terminal-dim/60 text-center pb-4">
          This tool is for educational and paper trading purposes only.
          Options trading involves significant risk. Always do your own research.
          Not SEBI registered. Not financial advice.
        </div>
      </main>

      <TradeConfirmModal />
    </div>
  )
}
