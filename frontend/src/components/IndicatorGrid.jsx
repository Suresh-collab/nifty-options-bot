import { useStore } from '../store'

function MiniCard({ label, children }) {
  return (
    <div className="bg-terminal-bg/60 border border-terminal-border rounded-lg p-3">
      <div className="text-xs font-mono text-terminal-dim uppercase tracking-wider mb-2">{label}</div>
      {children}
    </div>
  )
}

function SignalBadge({ signal }) {
  if (!signal) return null
  const colors = {
    BUY: 'text-terminal-green bg-terminal-green/10 border-terminal-green/30',
    BULLISH: 'text-terminal-green bg-terminal-green/10 border-terminal-green/20',
    SELL: 'text-terminal-red bg-terminal-red/10 border-terminal-red/30',
    BEARISH: 'text-terminal-red bg-terminal-red/10 border-terminal-red/20',
    NEUTRAL: 'text-terminal-dim bg-terminal-muted/30 border-terminal-border',
    OVERBOUGHT: 'text-terminal-amber bg-terminal-amber/10 border-terminal-amber/30',
    OVERSOLD: 'text-terminal-blue bg-terminal-blue/10 border-terminal-blue/30',
    SQUEEZE: 'text-terminal-amber bg-terminal-amber/10 border-terminal-amber/30',
  }
  return (
    <span className={`px-2 py-0.5 rounded border text-xs font-mono font-medium ${colors[signal] || colors.NEUTRAL}`}>
      {signal}
    </span>
  )
}

function RSIGauge({ value }) {
  if (value == null) return <span className="text-terminal-dim font-mono text-sm">--</span>
  const pct = Math.min(100, Math.max(0, value))
  const color = value > 65 ? '#ff4560' : value < 40 ? '#00e87a' : '#ffb800'
  return (
    <div>
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-xl font-mono font-bold" style={{ color }}>{value.toFixed(1)}</span>
        <SignalBadge signal={value > 65 ? 'SELL' : value < 40 ? 'BUY' : 'NEUTRAL'} />
      </div>
      <div className="h-1.5 bg-terminal-muted rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <div className="flex justify-between text-xs font-mono text-terminal-dim mt-1">
        <span>0</span><span>40</span><span>65</span><span>100</span>
      </div>
    </div>
  )
}

function fmt(v, decimals = 2) {
  if (v == null || v === undefined || isNaN(v)) return '--'
  return Number(v).toFixed(decimals)
}

export default function IndicatorGrid() {
  const { signalData } = useStore()
  if (!signalData) return null

  const ind = signalData.indicators
  const chain = signalData.chain_summary

  // Map backend fields — ind.macd has {value, signal}, ind.supertrend has {signal}
  const macdValue = ind.macd?.value
  const macdSignal = ind.macd?.signal
  const stSignal = ind.supertrend?.signal  // "BUY" or "SELL"
  const stDirection = stSignal === 'BUY' ? 'UP' : stSignal === 'SELL' ? 'DOWN' : null

  const pcr = chain?.pcr ?? ind.pcr?.value
  const pcrSignal = ind.pcr?.signal
  const maxPain = chain?.max_pain
  const iv = ind.iv?.value
  const bbWidth = ind.bollinger?.width
  const bbUpper = ind.bollinger?.upper
  const bbSignal = ind.bollinger?.signal

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      <MiniCard label="RSI (14)">
        <RSIGauge value={ind.rsi?.value} />
      </MiniCard>

      <MiniCard label="MACD (12/26/9)">
        <div className="flex justify-between items-start">
          <div>
            <div className="text-sm font-mono text-terminal-text">{fmt(macdValue)}</div>
          </div>
          <SignalBadge signal={macdSignal} />
        </div>
      </MiniCard>

      <MiniCard label="SuperTrend (7,3)">
        <div className="flex items-center gap-3">
          <span className={`text-3xl ${stDirection === 'UP' ? 'text-terminal-green' : stDirection === 'DOWN' ? 'text-terminal-red' : 'text-terminal-dim'}`}>
            {stDirection === 'UP' ? '▲' : stDirection === 'DOWN' ? '▼' : '—'}
          </span>
          <div>
            <SignalBadge signal={stSignal} />
            <div className="text-xs font-mono text-terminal-dim mt-1">Primary trend</div>
          </div>
        </div>
      </MiniCard>

      <MiniCard label="Bollinger Bands">
        <div className="flex justify-between items-start">
          <div>
            <div className="text-sm font-mono text-terminal-text">BW: {bbWidth != null ? (bbWidth * 100).toFixed(2) : '--'}%</div>
            <div className="text-xs font-mono text-terminal-dim">Upper: {bbUpper != null ? Math.round(bbUpper) : '--'}</div>
          </div>
          <SignalBadge signal={bbSignal} />
        </div>
      </MiniCard>

      <MiniCard label="PCR (Put-Call Ratio)">
        <div className="flex justify-between items-center">
          <span className={`text-xl font-mono font-bold ${
            pcr > 1.2 ? 'text-terminal-green' : pcr < 0.8 ? 'text-terminal-red' : 'text-terminal-amber'
          }`}>
            {fmt(pcr)}
          </span>
          <SignalBadge signal={pcrSignal} />
        </div>
        <div className="text-xs font-mono text-terminal-dim mt-1">
          {pcr > 1.2 ? '↑ More puts — bullish sentiment' : pcr < 0.8 ? '↓ More calls — bearish sentiment' : 'Neutral positioning'}
        </div>
      </MiniCard>

      <MiniCard label="Max Pain + IV">
        <div className="text-sm font-mono text-terminal-text">
          Pain: <span className="text-terminal-amber">{maxPain ? maxPain.toLocaleString('en-IN') : 'N/A'}</span>
        </div>
        <div className="text-sm font-mono text-terminal-text mt-0.5">
          ATM IV: <span className="text-terminal-blue">{iv ? `${fmt(iv, 1)}%` : 'N/A'}</span>
        </div>
        <div className="text-xs font-mono text-terminal-dim mt-1">
          {maxPain && signalData.spot ? `Gap: ${fmt(Math.abs(signalData.spot - maxPain) / signalData.spot * 100)}%` : 'NSE data unavailable'}
        </div>
      </MiniCard>

      {/* Confluence meter - multi-indicator agreement */}
      {ind.confluence && (
        <MiniCard label="Signal Confluence">
          <div className="flex items-center justify-between mb-1.5">
            <span className={`text-lg font-mono font-bold ${
              ind.confluence.strength === 'STRONG' ? 'text-terminal-green' :
              ind.confluence.strength === 'MODERATE' ? 'text-terminal-amber' :
              'text-terminal-dim'
            }`}>
              {ind.confluence.count}/5
            </span>
            <SignalBadge signal={ind.confluence.direction === 'NEUTRAL' ? 'NEUTRAL' :
              ind.confluence.direction === 'BUY' ? 'BULLISH' : 'BEARISH'} />
          </div>
          <div className="flex gap-0.5 mb-1.5">
            {[1,2,3,4,5].map(i => (
              <div key={i} className={`flex-1 h-1.5 rounded-sm ${
                i <= ind.confluence.count
                  ? (ind.confluence.direction === 'BUY' ? 'bg-terminal-green' :
                     ind.confluence.direction === 'SELL' ? 'bg-terminal-red' : 'bg-terminal-amber')
                  : 'bg-terminal-muted'
              }`} />
            ))}
          </div>
          <div className="flex justify-between text-[10px] font-mono text-terminal-dim">
            <span>{ind.confluence.buy_count} bullish</span>
            <span className={`font-bold ${
              ind.confluence.strength === 'STRONG' ? 'text-terminal-green' :
              ind.confluence.strength === 'MODERATE' ? 'text-terminal-amber' :
              'text-terminal-red'
            }`}>{ind.confluence.strength}</span>
            <span>{ind.confluence.sell_count} bearish</span>
          </div>
        </MiniCard>
      )}

      {/* Volume trend */}
      {ind.volume_trend && ind.volume_trend !== 'NEUTRAL' && (
        <MiniCard label="Volume Activity">
          <div className="flex items-center gap-2">
            <span className={`text-xl ${ind.volume_trend === 'HIGH' ? 'text-terminal-green' : 'text-terminal-dim'}`}>
              {ind.volume_trend === 'HIGH' ? '▲' : '▽'}
            </span>
            <div>
              <span className={`text-sm font-mono font-bold ${
                ind.volume_trend === 'HIGH' ? 'text-terminal-green' : 'text-terminal-dim'
              }`}>
                {ind.volume_trend === 'HIGH' ? 'Above Average' : 'Below Average'}
              </span>
              <div className="text-[10px] font-mono text-terminal-dim mt-0.5">
                {ind.volume_trend === 'HIGH' ? 'Volume confirms move' : 'Low conviction'}
              </div>
            </div>
          </div>
        </MiniCard>
      )}
    </div>
  )
}
