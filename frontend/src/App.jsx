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
import BacktestTab from './components/BacktestTab'
import AnalyticsTab from './components/AnalyticsTab'
import ScannerTab from './components/ScannerTab'
import AdminPanel from './components/AdminPanel'
import DailyRangeStats from './components/DailyRangeStats'
import GridSyncPanel from './components/GridSyncPanel'

const GRID_CONFIGS = [
  { label: '1 MIN',  interval: '1m',  candleType: 'candle', signals: true,  volume: true  },
  { label: '5 MIN',  interval: '5m',  candleType: 'ha',     signals: true,  volume: true  },
  { label: '15 MIN', interval: '15m', candleType: 'ha',     signals: true,  volume: false },
  { label: 'DAILY',  interval: '1d',  candleType: 'ha',     signals: false, volume: false },
]

export default function App() {
  const { fetchSignal, fetchMarketStatus, fetchTradeHistory, ticker, signalData } = useStore()
  const [viewMode, setViewMode] = useState(() => {
    try { return localStorage.getItem('nob_viewMode') || 'single' } catch { return 'single' }
  })
  const [activeTab, setActiveTab] = useState(() => {
    try { return localStorage.getItem('nob_activeTab') || 'live' } catch { return 'live' }
  })
  const [expandedInterval, setExpandedInterval] = useState(null)

  const handleViewMode = (m) => {
    try { localStorage.setItem('nob_viewMode', m) } catch {}
    setViewMode(m)
    setExpandedInterval(null)
  }
  const handleActiveTab = (id) => {
    try { localStorage.setItem('nob_activeTab', id) } catch {}
    setActiveTab(id)
  }

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
        <div className="max-w-[1600px] mx-auto px-4 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded bg-terminal-blue/20 border border-terminal-blue flex items-center justify-center">
              <span className="text-terminal-blue text-xs font-mono font-bold">N</span>
            </div>
            <span className="font-mono font-bold text-white tracking-wide">NIFTY OPTIONS BOT</span>
            <span className="text-[10px] font-mono text-[#475569] border border-[#334155] px-2 py-0.5 rounded">
              PAPER TRADING v2.0
            </span>
          </div>
          <div className="flex items-center gap-1">
            {[['live', 'LIVE'], ['backtest', 'BACKTEST'], ['analytics', 'ANALYTICS'], ['scanner', 'SCANNER'], ['admin', 'ADMIN']].map(([id, label]) => (
              <button
                key={id}
                onClick={() => handleActiveTab(id)}
                className={`px-3 py-1.5 text-[10px] font-mono rounded transition-all ${
                  activeTab === id
                    ? 'bg-terminal-blue text-white'
                    : 'text-[#64748b] hover:text-white hover:bg-white/5'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="text-[10px] font-mono text-[#475569]">
            Powered by AI · No broker required
          </div>
        </div>
      </header>

      <MarketStatusBar />

      <main className="max-w-[1600px] mx-auto px-4 py-4 space-y-4">
        {/* Phase 6 tabs */}
        {activeTab === 'analytics' && <AnalyticsTab />}
        {activeTab === 'scanner'   && <ScannerTab />}
        {activeTab === 'admin'     && <AdminPanel />}

        {/* Backtest tab */}
        {activeTab === 'backtest' && <BacktestTab />}

        {/* Live trading tab */}
        {activeTab === 'live' && <>
        {/* Controls row */}
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <TickerSelector />
            {/* View mode toggle */}
            <div className="flex items-center bg-[#0f172a] border border-[#1e293b] rounded overflow-hidden">
              <button
                onClick={() => handleViewMode('single')}
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
                onClick={() => handleViewMode('grid')}
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

        <DailyRangeStats />

        {viewMode === 'grid' ? (
          /* ── 4-chart grid: 1m · 5m · 15m · 1D ── */
          expandedInterval ? (() => {
            /* ── Expanded single chart (click-to-expand from grid) ── */
            const cfg = GRID_CONFIGS.find(c => c.interval === expandedInterval)
            return (
              <div className="space-y-3">
                {/* Back bar */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setExpandedInterval(null)}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-mono text-[#94a3b8] bg-[#0f172a] border border-[#1e293b] rounded hover:text-white hover:border-[#334155] transition-all"
                  >
                    ← Grid
                  </button>
                  <span className="text-[11px] font-mono text-[#475569] uppercase tracking-widest">
                    {cfg.label}
                  </span>
                  <span className="text-[10px] font-mono text-[#334155]">— expanded view · click ← Grid to return</span>
                </div>
                {/* Expanded layout: chart + signal card */}
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                  <div className="lg:col-span-9">
                    <LiveChart
                      key={expandedInterval}
                      defaultInterval={cfg.interval}
                      compact={false}
                      defaultCandleType={cfg.candleType}
                      defaultShowSignals={cfg.signals}
                      defaultShowVolume={cfg.volume}
                      defaultShowRSI={true}
                      defaultShowMACD={true}
                    />
                  </div>
                  <div className="lg:col-span-3 space-y-4">
                    <SignalCard />
                  </div>
                </div>
              </div>
            )
          })() : (
          <>
          <GridSyncPanel />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {GRID_CONFIGS.map(({ label, interval, candleType, signals, volume }) => (
              <div key={interval} className="group">
                {/* Clickable label row — expands on click */}
                <div
                  className="flex items-center justify-between text-[10px] font-mono uppercase tracking-widest mb-1 px-1 cursor-pointer text-[#475569] hover:text-[#94a3b8] transition-colors select-none"
                  onClick={() => setExpandedInterval(interval)}
                  title={`Expand ${label} chart`}
                >
                  <span>{label}</span>
                  <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[11px]" title="Expand">⤢</span>
                </div>
                <LiveChart
                  defaultInterval={interval}
                  compact={true}
                  defaultCandleType={candleType}
                  defaultShowSignals={signals}
                  defaultShowVolume={volume}
                />
              </div>
            ))}
          </div>
          </>
          )
        ) : (
          /* ── Single chart: original layout ── */
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Left col: chart + signal (9 cols) */}
            <div className="lg:col-span-9 space-y-4">
              <LiveChart />
              <SignalCard />
              <div>
                <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest mb-2">
                  Technical Indicators
                </div>
                <IndicatorGrid />
              </div>
            </div>

            {/* Right col: news → optimizer → option chart (3 cols) */}
            <div className="lg:col-span-3 space-y-4 lg:sticky lg:top-4 lg:self-start">
              <MarketNews />
              <BudgetOptimizer />
              <OptionChart ticker={ticker} expiry={expiry} />
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
        </>}
      </main>

      <TradeConfirmModal />
    </div>
  )
}
