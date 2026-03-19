import { useStore } from '../store'

export default function MarketStatusBar() {
  const { marketStatus, lastUpdated } = useStore()

  const isOpen = marketStatus?.is_open ?? false
  const statusLabel = isOpen ? 'MARKET OPEN' : 'MARKET CLOSED'
  const statusColor = isOpen ? 'text-terminal-green' : 'text-terminal-red'
  const dotColor = isOpen ? 'bg-terminal-green' : 'bg-terminal-red'

  return (
    <div className="bg-terminal-surface/60 border-b border-terminal-border">
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center justify-between text-xs font-mono">
        <div className="flex items-center gap-4">
          {/* Market status indicator */}
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${dotColor} ${isOpen ? 'animate-pulse' : ''}`} />
            <span className={statusColor}>{statusLabel}</span>
          </div>

          {/* Next expiry */}
          {marketStatus?.next_expiry && (
            <span className="text-terminal-dim">
              Expiry: <span className="text-terminal-text">{marketStatus.next_expiry}</span>
            </span>
          )}

          {/* Days to expiry */}
          {marketStatus?.days_to_expiry != null && (
            <span className="text-terminal-dim">
              DTE: <span className={marketStatus.days_to_expiry <= 2 ? 'text-terminal-amber' : 'text-terminal-text'}>
                {marketStatus.days_to_expiry}
              </span>
            </span>
          )}
        </div>

        <div className="text-terminal-dim">
          {lastUpdated && (
            <span>Updated: {lastUpdated.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' })} IST</span>
          )}
        </div>
      </div>
    </div>
  )
}
