import { useStore } from '../store'

export default function BudgetOptimizer() {
  const { budget, setBudget, fetchOptimize, optimizeLoading, optimizeData, optimizeError, ticker } = useStore()

  const rec = optimizeData?.plan

  return (
    <div className="bg-terminal-surface border border-terminal-border rounded-lg p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs font-mono text-terminal-dim uppercase tracking-widest">Budget Optimizer</span>
        <span className="text-xs font-mono text-terminal-dim">— enter capital, get best strike</span>
      </div>

      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-terminal-dim font-mono text-sm">₹</span>
          <input
            type="number"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetchOptimize()}
            placeholder="50000"
            className="w-full bg-terminal-bg border border-terminal-border rounded px-3 py-2.5 pl-7
              text-terminal-text font-mono text-sm focus:outline-none focus:border-terminal-blue
              placeholder:text-terminal-dim transition-colors"
          />
        </div>
        <button
          onClick={fetchOptimize}
          disabled={optimizeLoading || !budget}
          className="px-5 py-2.5 rounded bg-terminal-blue/20 border border-terminal-blue
            text-terminal-blue font-mono text-sm hover:bg-terminal-blue hover:text-white
            transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {optimizeLoading ? '...' : 'Optimize →'}
        </button>
      </div>

      {optimizeError && (
        <div className="text-terminal-red text-xs font-mono mb-3">⚠ {optimizeError}</div>
      )}

      {rec && rec.recommendation === 'AVOID' && (
        <div className="p-3 rounded bg-terminal-amber/10 border border-terminal-amber/30">
          <p className="text-terminal-amber text-sm font-mono">{rec.reason}</p>
        </div>
      )}

      {rec?.recommendation === 'TRADE' && (
        <div className="space-y-3">
          {/* Primary recommendation */}
          <div className="p-4 rounded bg-terminal-green/5 border border-terminal-green/40">
            <div className="flex justify-between items-center mb-3">
              <div>
                <span className="text-terminal-green font-mono font-bold text-lg">
                  {rec.strike?.toLocaleString('en-IN')} {rec.direction?.includes('CE') ? 'CE' : 'PE'}
                </span>
                <span className="text-terminal-dim font-mono text-xs ml-2">RECOMMENDED STRIKE</span>
              </div>
              <div className="text-right">
                <div className="text-terminal-green font-mono font-bold">₹{rec.ltp}</div>
                <div className="text-terminal-dim text-xs font-mono">premium / unit</div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { l: 'Lots', v: rec.lots },
                { l: 'Lot Size', v: rec.lot_size },
                { l: 'Total Cost', v: `₹${rec.total_cost?.toLocaleString('en-IN')}` },
                { l: 'Max Loss', v: `₹${rec.max_loss?.toLocaleString('en-IN')}` },
                { l: 'Target P&L', v: `+₹${rec.target_pnl?.toLocaleString('en-IN')}`, cls: 'text-terminal-green' },
                { l: 'Capital Used', v: `${rec.risk_pct}%`, cls: rec.risk_pct > 50 ? 'text-terminal-red' : 'text-terminal-amber' },
              ].map(({ l, v, cls }) => (
                <div key={l} className="flex justify-between text-xs font-mono">
                  <span className="text-terminal-dim">{l}</span>
                  <span className={cls || 'text-terminal-text'}>{v}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Alternatives */}
          {rec.alternatives?.length > 0 && (
            <div>
              <div className="text-xs font-mono text-terminal-dim mb-2">ALTERNATIVES</div>
              <div className="space-y-1.5">
                {rec.alternatives.map((alt, i) => (
                  <div key={i} className="flex items-center justify-between p-2.5 rounded bg-terminal-bg/60 border border-terminal-border text-xs font-mono">
                    <span className="text-terminal-text">{alt.strike?.toLocaleString('en-IN')} {rec.direction?.includes('CE') ? 'CE' : 'PE'}</span>
                    <span className="text-terminal-dim">{alt.lots} lot{alt.lots > 1 ? 's' : ''}</span>
                    <span className="text-terminal-dim">₹{alt.ltp} LTP</span>
                    <span className="text-terminal-amber">{alt.risk_pct}% risk</span>
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
