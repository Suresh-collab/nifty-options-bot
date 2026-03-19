import { useStore } from '../store'

const directionConfig = {
  BUY_CE: { label: 'BUY CALL', color: 'text-terminal-green', border: 'border-terminal-green', glow: 'glow-green', bg: 'bg-terminal-green/10', arrow: '▲' },
  BUY_PE: { label: 'BUY PUT',  color: 'text-terminal-red',   border: 'border-terminal-red',   glow: 'glow-red',   bg: 'bg-terminal-red/10',   arrow: '▼' },
  AVOID:  { label: 'AVOID',    color: 'text-terminal-amber', border: 'border-terminal-amber', glow: 'glow-amber', bg: 'bg-terminal-amber/10', arrow: '—' },
}

const confidenceBar = { High: 3, Medium: 2, Low: 1 }

// Plain-language tooltips for each field
const fieldHelp = {
  SPOT: 'Current market price of the index right now',
  'ENTRY ZONE': 'Best price range to enter the trade — wait for price to be in this range',
  STRIKE: 'The option strike price recommended for this trade',
  TARGET: 'Expected profit target — consider exiting when price reaches here',
  'STOP LOSS': 'Maximum loss level — exit immediately if price hits this to limit losses',
  SCORE: 'Overall signal strength from -100 (strong sell) to +100 (strong buy)',
}

function fmt(v) {
  if (v == null || v === undefined || isNaN(v)) return '--'
  return Number(v).toLocaleString('en-IN')
}

/**
 * Generate a plain-language action summary that any beginner can understand.
 */
function getActionSummary(signal, spot, score) {
  const dir = signal.direction
  const conf = signal.confidence

  if (dir === 'AVOID') {
    if (Math.abs(score) < 10) {
      return {
        text: 'No clear direction. The market is undecided — indicators are giving mixed signals. Do NOT trade now. Wait for a clearer setup.',
        color: 'text-terminal-amber',
        icon: '⏸',
      }
    }
    return {
      text: `Weak signal (score: ${score}). The trend is not strong enough to trade safely. Stay on the sidelines and watch. Patience protects your capital.`,
      color: 'text-terminal-amber',
      icon: '⏸',
    }
  }

  if (dir === 'BUY_CE') {
    const entryLow = signal.entry_zone?.[0]
    const entryHigh = signal.entry_zone?.[1]
    if (conf === 'High') {
      return {
        text: `Strong BULLISH signal! The market is likely to go UP. Consider buying a CALL option at strike ${fmt(signal.best_strike)}. Enter when price is between ${fmt(entryLow)} – ${fmt(entryHigh)}. Set target at ${fmt(signal.target)} and stop loss at ${fmt(signal.stop_loss)}.`,
        color: 'text-terminal-green',
        icon: '▲',
      }
    }
    if (conf === 'Medium') {
      return {
        text: `Moderate BULLISH signal. Market shows upward tendency. You may consider a CALL option at ${fmt(signal.best_strike)}, but use a strict stop loss at ${fmt(signal.stop_loss)} since confidence is not high.`,
        color: 'text-terminal-green',
        icon: '▲',
      }
    }
    return {
      text: `Weak BULLISH hint. Some indicators point up, but not enough agreement. If you trade, use very small position size and tight stop loss at ${fmt(signal.stop_loss)}.`,
      color: 'text-terminal-amber',
      icon: '△',
    }
  }

  if (dir === 'BUY_PE') {
    const entryLow = signal.entry_zone?.[0]
    const entryHigh = signal.entry_zone?.[1]
    if (conf === 'High') {
      return {
        text: `Strong BEARISH signal! The market is likely to go DOWN. Consider buying a PUT option at strike ${fmt(signal.best_strike)}. Enter when price is between ${fmt(entryLow)} – ${fmt(entryHigh)}. Set target at ${fmt(signal.target)} and stop loss at ${fmt(signal.stop_loss)}.`,
        color: 'text-terminal-red',
        icon: '▼',
      }
    }
    if (conf === 'Medium') {
      return {
        text: `Moderate BEARISH signal. Market shows downward pressure. You may consider a PUT option at ${fmt(signal.best_strike)}, but keep stop loss at ${fmt(signal.stop_loss)} since signal is moderate.`,
        color: 'text-terminal-red',
        icon: '▼',
      }
    }
    return {
      text: `Weak BEARISH hint. Some indicators point down, but not enough confirmation. If you trade, use very small size and stop loss at ${fmt(signal.stop_loss)}.`,
      color: 'text-terminal-amber',
      icon: '▽',
    }
  }

  return { text: '', color: 'text-terminal-dim', icon: '' }
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

  const action = getActionSummary(signal, spot, score)

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
      {/* Section label */}
      <div className="text-xs font-mono text-terminal-dim uppercase tracking-widest mb-3">
        What should you do?
      </div>

      {/* Plain-language action summary */}
      <div className={`mb-4 p-3 rounded border ${
        signal.direction === 'AVOID' ? 'bg-terminal-amber/5 border-terminal-amber/30' :
        signal.direction === 'BUY_CE' ? 'bg-terminal-green/5 border-terminal-green/30' :
        'bg-terminal-red/5 border-terminal-red/30'
      }`}>
        <div className="flex items-start gap-2">
          <span className={`text-lg ${action.color}`}>{action.icon}</span>
          <p className={`text-sm leading-relaxed ${action.color}`}>
            {action.text}
          </p>
        </div>
      </div>

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
          <div className="text-[10px] font-mono text-terminal-dim mt-0.5">
            {signal.confidence === 'High' ? '3 bars = strong signal' :
             signal.confidence === 'Medium' ? '2 bars = moderate signal' :
             '1 bar = weak, be cautious'}
          </div>
        </div>
      </div>

      {/* Price levels with tooltips */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { label: 'SPOT', value: fmt(spot), color: 'text-terminal-text' },
          { label: 'ENTRY ZONE', value: signal.entry_zone ? `${fmt(signal.entry_zone[0])} – ${fmt(signal.entry_zone[1])}` : '--', color: 'text-terminal-blue' },
          { label: 'STRIKE', value: fmt(strike), color: cfg.color },
          { label: 'TARGET', value: fmt(signal.target), color: 'text-terminal-green' },
          { label: 'STOP LOSS', value: fmt(signal.stop_loss), color: 'text-terminal-red' },
          { label: 'SCORE', value: score != null && !isNaN(score) ? `${score > 0 ? '+' : ''}${score}` : '--', color: score > 0 ? 'text-terminal-green' : score < 0 ? 'text-terminal-red' : 'text-terminal-amber' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-terminal-bg/60 rounded p-2.5 border border-terminal-border group relative">
            <div className="text-xs font-mono text-terminal-dim mb-0.5">{label}</div>
            <div className={`text-sm font-mono font-medium ${color}`}>{value}</div>
            {/* Hover tooltip */}
            {fieldHelp[label] && (
              <div className="hidden group-hover:block absolute bottom-full left-0 right-0 mb-1 p-2 bg-terminal-bg border border-terminal-border rounded text-[10px] font-mono text-terminal-dim z-10 shadow-lg">
                {fieldHelp[label]}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Reasoning */}
      {signal.reasoning && (
        <div className="mb-4 p-3 rounded bg-terminal-bg/50 border-l-2 border-terminal-blue">
          <div className="text-xs font-mono text-terminal-dim mb-1">AI REASONING (technical analysis)</div>
          <p className="text-terminal-text text-sm leading-relaxed">{signal.reasoning}</p>
        </div>
      )}

      {/* Quick guide for beginners */}
      <div className="mb-4 p-3 rounded bg-terminal-bg/30 border border-terminal-border/50">
        <div className="text-[10px] font-mono text-terminal-dim mb-1.5 uppercase tracking-wider">Quick Guide</div>
        <div className="grid grid-cols-1 gap-1 text-[11px] font-mono text-terminal-dim leading-relaxed">
          <div><span className="text-terminal-green">BUY CALL (CE)</span> = You expect the market to go UP. You profit if it rises.</div>
          <div><span className="text-terminal-red">BUY PUT (PE)</span> = You expect the market to go DOWN. You profit if it falls.</div>
          <div><span className="text-terminal-amber">AVOID</span> = No clear signal. Do not trade — wait for a better opportunity.</div>
          <div><span className="text-terminal-blue">Entry Zone</span> = Wait for price to be in this range before entering.</div>
          <div><span className="text-terminal-green">Target</span> = Book profits here. <span className="text-terminal-red">Stop Loss</span> = Exit here to limit loss.</div>
        </div>
      </div>

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
