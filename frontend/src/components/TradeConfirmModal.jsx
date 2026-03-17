import { useState } from 'react'
import { useStore } from '../store'

export default function TradeConfirmModal() {
  const { confirmTrade, setConfirmTrade, enterPaperTrade } = useStore()
  const [entering, setEntering] = useState(false)
  const [done, setDone] = useState(null)

  if (!confirmTrade) return null

  const t = confirmTrade
  const isBull = t.direction === 'BUY_CE'

  const handleConfirm = async () => {
    setEntering(true)
    const result = await enterPaperTrade(t)
    setEntering(false)
    setDone(result)
  }

  const handleClose = () => {
    setConfirmTrade(null)
    setDone(null)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(10,13,18,0.85)', backdropFilter: 'blur(4px)' }}
    >
      <div className="w-full max-w-md bg-terminal-surface border border-terminal-border rounded-xl
        shadow-2xl animate-slide-up"
      >
        {/* Header */}
        <div className={`flex items-center justify-between p-4 border-b border-terminal-border rounded-t-xl
          ${isBull ? 'bg-terminal-green/10' : 'bg-terminal-red/10'}`}
        >
          <div className="flex items-center gap-3">
            <span className={`text-2xl ${isBull ? 'text-terminal-green' : 'text-terminal-red'}`}>
              {isBull ? '▲' : '▼'}
            </span>
            <div>
              <div className={`font-mono font-bold text-base ${isBull ? 'text-terminal-green' : 'text-terminal-red'}`}>
                PAPER TRADE — {isBull ? 'BUY CALL' : 'BUY PUT'}
              </div>
              <div className="text-terminal-dim text-xs font-mono">{t.ticker} · Confidence: {t.confidence}</div>
            </div>
          </div>
          <button onClick={handleClose} className="text-terminal-dim hover:text-terminal-text text-xl">×</button>
        </div>

        {done ? (
          <div className="p-6 text-center">
            <div className="text-terminal-green text-4xl mb-3">✓</div>
            <div className="text-terminal-green font-mono font-bold text-lg mb-1">Paper Trade Entered</div>
            <div className="text-terminal-dim font-mono text-sm">Trade ID: #{done.trade_id}</div>
            <div className="text-terminal-dim text-sm mt-2">Track in Trade History below</div>
            <button onClick={handleClose}
              className="mt-4 px-6 py-2 rounded border border-terminal-border text-terminal-dim
                font-mono text-sm hover:text-terminal-text transition-colors"
            >
              Close
            </button>
          </div>
        ) : (
          <>
            <div className="p-5 space-y-2">
              {[
                ['Strike', `${t.strike?.toLocaleString('en-IN')} ${isBull ? 'CE' : 'PE'}`],
                ['Expiry', t.expiry],
                ['Lots × Size', `${t.lots} × ${t.lot_size} = ${t.lots * t.lot_size} units`],
                ['Entry Premium', `₹${t.entry_ltp}`],
                ['Total Capital', `₹${t.total_cost?.toLocaleString('en-IN')}`],
                ['Max Loss', `₹${t.total_cost?.toLocaleString('en-IN')} (premium paid)`],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between text-sm font-mono border-b border-terminal-border/40 pb-2">
                  <span className="text-terminal-dim">{label}</span>
                  <span className="text-terminal-text font-medium">{value}</span>
                </div>
              ))}
              {t.reasoning && (
                <div className="pt-2">
                  <div className="text-xs font-mono text-terminal-dim mb-1">Signal reasoning</div>
                  <p className="text-terminal-text text-xs leading-relaxed">{t.reasoning}</p>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-terminal-border flex gap-3">
              <button onClick={handleClose}
                className="flex-1 py-2.5 rounded border border-terminal-border text-terminal-dim
                  font-mono text-sm hover:text-terminal-text transition-colors"
              >
                Cancel
              </button>
              <button onClick={handleConfirm} disabled={entering}
                className={`flex-1 py-2.5 rounded font-mono text-sm font-medium transition-all duration-200
                  ${isBull
                    ? 'bg-terminal-green/20 border border-terminal-green text-terminal-green hover:bg-terminal-green hover:text-terminal-bg'
                    : 'bg-terminal-red/20 border border-terminal-red text-terminal-red hover:bg-terminal-red hover:text-white'
                  } disabled:opacity-40`}
              >
                {entering ? 'Entering...' : '✓ Confirm Paper Trade'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
