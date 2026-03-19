import { useStore } from '../store'

function fmt(v) {
  if (v == null || isNaN(v)) return '--'
  return Number(v).toLocaleString('en-IN')
}

export default function BudgetOptimizer() {
  const { budget, setBudget, fetchOptimize, optimizeLoading, optimizeData, optimizeError, ticker, signalData } = useStore()

  const rec = optimizeData?.plan
  const signal = optimizeData?.signal || signalData?.signal
  const spot = signalData?.spot

  return (
    <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1e293b]">
        <div className="text-xs font-mono text-[#64748b] uppercase tracking-widest">
          Smart Budget Optimizer
        </div>
        <div className="text-[10px] font-mono text-[#475569] mt-0.5">
          Enter your capital — get the best option to buy based on live trend analysis
        </div>
      </div>

      {/* Input */}
      <div className="px-4 py-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b] font-mono text-sm">₹</span>
            <input
              type="number"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && fetchOptimize()}
              placeholder="5000"
              className="w-full bg-[#1e293b] border border-[#334155] rounded px-3 py-2.5 pl-7
                text-white font-mono text-sm focus:outline-none focus:border-terminal-blue
                placeholder:text-[#475569] transition-colors"
            />
          </div>
          <button
            onClick={fetchOptimize}
            disabled={optimizeLoading || !budget}
            className="px-5 py-2.5 rounded bg-terminal-blue/20 border border-terminal-blue
              text-terminal-blue font-mono text-sm font-medium hover:bg-terminal-blue hover:text-white
              transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
          >
            {optimizeLoading ? 'Analyzing...' : 'Find Best Option →'}
          </button>
        </div>
      </div>

      {optimizeError && (
        <div className="px-4 pb-3">
          <div className="text-terminal-red text-[11px] font-mono p-2 rounded bg-terminal-red/5 border border-terminal-red/20">
            {optimizeError}
          </div>
        </div>
      )}

      {/* Trend Summary (show current analysis) */}
      {signal && !rec && (
        <div className="px-4 pb-3">
          <div className="p-3 rounded bg-[#1e293b] border border-[#334155]">
            <div className="flex items-center gap-2 mb-1">
              <span className={`text-xs font-mono font-medium ${
                signal.direction === 'BUY_CE' ? 'text-terminal-green' :
                signal.direction === 'BUY_PE' ? 'text-terminal-red' : 'text-terminal-amber'
              }`}>
                {signal.direction === 'BUY_CE' ? '▲ BULLISH' :
                 signal.direction === 'BUY_PE' ? '▼ BEARISH' : '— NEUTRAL'}
              </span>
              <span className="text-[10px] font-mono text-[#475569]">
                {signal.confidence} confidence
              </span>
            </div>
            <div className="text-[10px] font-mono text-[#64748b]">
              {spot && `${ticker} @ ${fmt(spot)}`} · Enter budget above to get specific option recommendation
            </div>
          </div>
        </div>
      )}

      {/* AVOID recommendation */}
      {rec?.recommendation === 'AVOID' && (
        <div className="px-4 pb-4">
          <div className="p-3 rounded bg-terminal-amber/5 border border-terminal-amber/30">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-terminal-amber font-mono text-sm font-medium">⏸ AVOID TRADING</span>
            </div>
            <p className="text-[#94a3b8] text-xs font-mono leading-relaxed">{rec.reason}</p>
            <p className="text-[#475569] text-[10px] font-mono mt-2">
              No clear trend detected. Wait for a stronger signal before entering a trade.
              Your capital is safer on the sidelines right now.
            </p>
          </div>
        </div>
      )}

      {/* TRADE recommendation */}
      {rec?.recommendation === 'TRADE' && (
        <div className="px-4 pb-4 space-y-3">
          {/* Primary pick */}
          <div className={`p-4 rounded border ${
            rec.direction?.includes('CE')
              ? 'bg-terminal-green/5 border-terminal-green/30'
              : 'bg-terminal-red/5 border-terminal-red/30'
          }`}>
            <div className="flex items-center justify-between mb-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`text-lg font-mono font-bold ${
                    rec.direction?.includes('CE') ? 'text-terminal-green' : 'text-terminal-red'
                  }`}>
                    {rec.direction?.includes('CE') ? '▲' : '▼'}
                  </span>
                  <span className="text-white font-mono font-bold text-lg">
                    {ticker} {fmt(rec.strike)} {rec.direction?.includes('CE') ? 'CE' : 'PE'}
                  </span>
                </div>
                <div className="text-[10px] font-mono text-[#64748b] mt-0.5">
                  {rec.direction?.includes('CE') ? 'CALL — profit when market goes UP' : 'PUT — profit when market goes DOWN'}
                  {rec.expiry && ` · Exp: ${rec.expiry}`}
                </div>
              </div>
              <div className="text-right">
                <div className="text-white font-mono font-bold text-lg">₹{rec.ltp}</div>
                <div className="text-[10px] font-mono text-[#64748b]">premium/unit</div>
              </div>
            </div>

            {/* Key metrics grid */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { l: 'Lots', v: rec.lots, sub: `× ${rec.lot_size} units` },
                { l: 'Total Cost', v: `₹${fmt(rec.total_cost)}`, cls: 'text-white font-medium' },
                { l: 'Capital Used', v: `${rec.risk_pct}%`, cls: rec.risk_pct > 50 ? 'text-terminal-red' : 'text-terminal-amber' },
                { l: 'Target P&L', v: `+₹${fmt(rec.target_pnl)}`, cls: 'text-terminal-green' },
                { l: 'Max Loss', v: `₹${fmt(rec.max_loss)}`, cls: 'text-terminal-red' },
                { l: 'Remaining', v: `₹${fmt(rec.budget_remaining)}` },
              ].map(({ l, v, cls, sub }) => (
                <div key={l} className="bg-[#0f172a]/60 rounded p-2 border border-[#1e293b]">
                  <div className="text-[10px] font-mono text-[#475569]">{l}</div>
                  <div className={`text-xs font-mono ${cls || 'text-[#94a3b8]'}`}>{v}</div>
                  {sub && <div className="text-[9px] font-mono text-[#475569]">{sub}</div>}
                </div>
              ))}
            </div>

            {/* Action guidance */}
            <div className="mt-3 p-2 rounded bg-[#0f172a] border border-[#1e293b]">
              <div className="text-[10px] font-mono text-[#64748b] leading-relaxed">
                <span className="text-terminal-blue font-medium">How to trade:</span>{' '}
                {rec.direction?.includes('CE')
                  ? `Buy ${rec.lots} lot${rec.lots > 1 ? 's' : ''} of ${ticker} ${fmt(rec.strike)} CE at ₹${rec.ltp}. Set target at ₹${fmt(rec.target_ltp)} (+50%) and stop loss at ₹${fmt(rec.sl_ltp)} (-50%).`
                  : `Buy ${rec.lots} lot${rec.lots > 1 ? 's' : ''} of ${ticker} ${fmt(rec.strike)} PE at ₹${rec.ltp}. Set target at ₹${fmt(rec.target_ltp)} (+50%) and stop loss at ₹${fmt(rec.sl_ltp)} (-50%).`
                }
              </div>
            </div>
          </div>

          {/* Alternatives */}
          {rec.alternatives?.length > 0 && (
            <div>
              <div className="text-[10px] font-mono text-[#64748b] uppercase tracking-wider mb-1.5">Other options within budget</div>
              <div className="space-y-1">
                {rec.alternatives.map((alt, i) => (
                  <div key={i} className="flex items-center justify-between p-2 rounded bg-[#1e293b] border border-[#334155] text-[11px] font-mono">
                    <span className="text-white font-medium">
                      {fmt(alt.strike)} {rec.direction?.includes('CE') ? 'CE' : 'PE'}
                    </span>
                    <span className="text-[#64748b]">{alt.lots} lot{alt.lots > 1 ? 's' : ''}</span>
                    <span className="text-[#94a3b8]">₹{alt.ltp}</span>
                    <span className="text-terminal-amber">{alt.risk_pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
