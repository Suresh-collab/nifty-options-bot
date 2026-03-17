import { useStore } from '../store'

const tickers = ['NIFTY', 'SENSEX']

export default function TickerSelector() {
  const { ticker, setTicker, fetchSignal, fetchMarketStatus, signalLoading } = useStore()

  const handleChange = (t) => {
    setTicker(t)
    setTimeout(() => {
      useStore.getState().fetchSignal()
      useStore.getState().fetchMarketStatus()
    }, 0)
  }

  return (
    <div className="flex items-center gap-3">
      {/* Ticker buttons */}
      <div className="flex rounded border border-terminal-border overflow-hidden">
        {tickers.map((t) => (
          <button
            key={t}
            onClick={() => handleChange(t)}
            className={`px-4 py-1.5 text-sm font-mono font-medium transition-colors
              ${ticker === t
                ? 'bg-terminal-blue/20 text-terminal-blue border-r border-terminal-border'
                : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-surface border-r border-terminal-border last:border-r-0'
              }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Refresh button */}
      <button
        onClick={fetchSignal}
        disabled={signalLoading}
        className="px-3 py-1.5 text-sm font-mono border border-terminal-border rounded
          text-terminal-dim hover:text-terminal-text hover:border-terminal-blue
          transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {signalLoading ? '...' : 'Refresh Signal'}
      </button>
    </div>
  )
}
