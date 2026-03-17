import { useStore } from '../store'

const directionConfig = {
  BUY_CE: { label: 'BUY CALL', color: 'text-terminal-green', border: 'border-terminal-green', glow: 'glow-green', bg: 'bg-terminal-green/10', arrow: '▲' },
  BUY_PE: { label: 'BUY PUT',  color: 'text-terminal-red',   border: 'border-terminal-red',   glow: 'glow-red',   bg: 'bg-terminal-red/10',   arrow: '▼' },
  AVOID:  { label: 'AVOID',    color: 'text-terminal-amber', border: 'border-terminal-amber', glow: 'glow-amber', bg: 'bg-terminal-amber/10', arrow: '—' },
}

const confidenceBar = { High: 3, Medium: 2, Low: 1 }

function fmt(v) {
  if (v == null || v === undefined || isNaN(v)) return '--'
  return Number(v).toLocaleString('en-IN')
}

export default function SignalCard() {
  const { signalData, signalLoading, signalError, setConfirmTrade, optimizeData } = useStore()

  if (signalLoading) return (
    <div className="bg-terminal-surface border border-terminal-border rounded-lg p-6 animate-pulse">
      <div className="h-8 bg-terminal-muted rounded w-1/3 mb-4" />
      <div className="h-4 bg-terminal-muted rounded w-2/3 mb-2" />
      <div className="h-4 bg-terminal-muted rounded w-1/2" />
    </div>
  )

  if (signalError) return (
    <div className="bg-terminal-surface border border-terminal-red/40 rounded-lg p-6">
      <p className="text-terminal-red font-mono text-sm">⚠ {signalError}</p>
      <p className="text-terminal-dim text-xs mt-1">Check that the backend is running on port 8000</p>
    </div>
  )

  if (!signalData) return (
    <div className="bg-terminal-surface border border-terminal-border rounded-lg p-6 text-center">
      <p className="text-terminal-dim font-mono text-sm">Select a ticker and click Refresh Signal</p>
    </div>
  )

  const { signal, spot, indicators } = signalData
  const cfg = directionConfig[signal.direction] || directionConfig.AVOID
  const bars = confidenceBar[signal.confidence] || 1

  const strike = signal.best_strike || signal.recommended_strike
  const score = indicators?.combined_score ?? signal.combined_score
  const expiry = signal.expiry && signal.expiry !== 'None' ? signal.expiry : 'Weekly'

  const handleConfirm = () => {
    if (!optimizeData?.plan) return
    const plan = optimizeData.plan
    if (plan.recommendation !== 'TRADE') return
    setConfirmTrade({
      ticker: signalData.ticker,
      direction: signal.direction,
      strike: plan.strike,
      expiry: expiry,
      lots: plan.lots,
      lot_size: plan.lot_size,
      entry_ltp: plan.ltp,
      total_cost: plan.total_cost,
      confidence: signal.confidence,
      combined_score: score,
      reasoning: signal.reasoning,
    })
  }

  return (
    <div className={`bg-terminal-surface border ${cfg.border} rounded-lg p-5 ${cfg.glow} animate-slide-up`}>
      <div className="flex items-start justify-between mb-4">
        {/* Direction badge */}
        <div className={`flex items-center gap-3 px-4 py-2 rounded ${cfg.bg} border ${cfg.border}`}>
          <span className={`text-2xl font-mono font-bold ${cfg.color}`}>{cfg.arrow}</span>
          <div>
            <div className={`text-xl font-mono font-bold ${cfg.color}`}>{cfg.label}</div>
            <div className="text-terminal-dim text-xs font-mono">{signal.ticker} · {expiry}</div>
          </div>
        </div>

        {/* Confidence meter */}
        <div className="text-right">
          <div className="text-xs font-mono text-terminal-dim mb-1">CONFIDENCE</div>
          <div className="flex gap-1 justify-end mb-1">
            {[1,2,3].map(i => (
              <div key={i} className={`w-6 h-2 rounded-sm ${i <= bars
                ? (signal.confidence === 'High' ? 'bg-terminal-green' : signal.confidence === 'Medium' ? 'bg-terminal-amber' : 'bg-terminal-red')
                : 'bg-terminal-muted'}`}
              />
            ))}
          </div>
          <div className={`text-sm font-mono font-medium ${cfg.color}`}>{signal.confidence}</div>
        </div>
      </div>

      {/* Price levels */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { label: 'SPOT', value: fmt(spot), color: 'text-terminal-text' },
          { label: 'ENTRY ZONE', value: signal.entry_zone ? `${fmt(signal.entry_zone[0])} – ${fmt(signal.entry_zone[1])}` : '--', color: 'text-terminal-blue' },
          { label: 'STRIKE', value: fmt(strike), color: cfg.color },
          { label: 'TARGET', value: fmt(signal.target), color: 'text-terminal-green' },
          { label: 'STOP LOSS', value: fmt(signal.stop_loss), color: 'text-terminal-red' },
          { label: 'SCORE', value: score != null && !isNaN(score) ? `${score > 0 ? '+' : ''}${score}` : '--', color: score > 0 ? 'text-terminal-green' : score < 0 ? 'text-terminal-red' : 'text-terminal-amber' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-terminal-bg/60 rounded p-2.5 border border-terminal-border">
            <div className="text-xs font-mono text-terminal-dim mb-0.5">{label}</div>
            <div className={`text-sm font-mono font-medium ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Reasoning */}
      {signal.reasoning && (
        <div className="mb-4 p-3 rounded bg-terminal-bg/50 border-l-2 border-terminal-blue">
          <div className="text-xs font-mono text-terminal-dim mb-1">AI REASONING</div>
          <p className="text-terminal-text text-sm leading-relaxed">{signal.reasoning}</p>
        </div>
      )}

      {/* Paper trade button */}
      {signal.direction !== 'AVOID' && optimizeData?.plan?.recommendation === 'TRADE' && (
        <button
          onClick={handleConfirm}
          className="w-full py-2.5 rounded border border-terminal-green text-terminal-green
            font-mono text-sm font-medium hover:bg-terminal-green hover:text-terminal-bg
            transition-all duration-200"
        >
          Paper Trade This Signal →
        </button>
      )}
    </div>
  )
}
