import { useStore } from '../store'
import { computeAlignment, formatISTTime, hasCursorData, GRID_INTERVALS, IV_LABELS } from '../lib/gridUtils'

function fmt(v) {
  return v == null ? '—' : Number(v).toFixed(2)
}

function fmtVol(v) {
  if (v == null) return '—'
  if (v >= 1e7) return `${(v / 1e7).toFixed(1)}Cr`
  if (v >= 1e5) return `${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`
  return String(Math.round(v))
}

// Per-direction colour tokens
function dirClass(dir) {
  if (dir === 'UP')   return 'text-terminal-green bg-terminal-green/10 border-terminal-green/30'
  if (dir === 'DOWN') return 'text-terminal-red   bg-terminal-red/10   border-terminal-red/30'
  return 'text-[#475569] bg-[#1e293b]/40 border-[#1e293b]'
}

function signalClass(signal) {
  if (signal === 'BUY')     return 'text-terminal-green bg-terminal-green/10 border-terminal-green/30'
  if (signal === 'SELL')    return 'text-terminal-red   bg-terminal-red/10   border-terminal-red/30'
  if (signal === 'NEUTRAL') return 'text-amber-400      bg-amber-400/10      border-amber-400/30'
  return 'text-[#475569] bg-[#1e293b]/40 border-[#1e293b]'
}

export default function GridSyncPanel() {
  const { gridSnapshot, gridBookmarks } = useStore()
  const alignment = computeAlignment(gridSnapshot)
  const showInfoBar = hasCursorData(gridSnapshot)

  // Timestamp to display — prefer cursor time, fall back to any live bar time
  const cursorTime = GRID_INTERVALS
    .map(iv => gridSnapshot[iv]?.time)
    .find(t => t != null) ?? null

  return (
    <div
      className="bg-[#0f172a] border border-[#1e293b] rounded-lg px-3 py-2 space-y-1.5"
      data-testid="grid-sync-panel"
    >
      {/* ── Row 1: Confluence Strip (always visible) ── */}
      <div className="flex items-center gap-2 flex-wrap min-h-[22px]">
        <span className="text-[9px] font-mono text-[#475569] uppercase tracking-widest shrink-0 select-none">
          Confluence
        </span>

        {GRID_INTERVALS.map(iv => {
          const dir = alignment.directions[iv]
          return (
            <span
              key={iv}
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded border select-none ${dirClass(dir)}`}
            >
              {IV_LABELS[iv]} {dir === 'UP' ? '▲' : dir === 'DOWN' ? '▼' : '—'}
            </span>
          )
        })}

        <span className="text-[#1e293b] text-[10px] select-none">│</span>

        {alignment.signal ? (
          <span
            className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded border ${signalClass(alignment.signal)}`}
            data-testid="confluence-signal"
          >
            {alignment.signal} {alignment.score}%
          </span>
        ) : (
          <span className="text-[10px] font-mono text-[#334155] italic select-none">
            hover any chart
          </span>
        )}

        {/* Time stamp */}
        {cursorTime && (
          <span className="text-[10px] font-mono text-[#475569] ml-auto select-none">
            {showInfoBar ? '⊕' : '◎'} {formatISTTime(cursorTime)} IST
          </span>
        )}

        {/* Bookmark count badge */}
        {gridBookmarks.length > 0 && (
          <span
            className="text-[10px] font-mono text-amber-400/80 select-none"
            title={`${gridBookmarks.length} bookmark${gridBookmarks.length > 1 ? 's' : ''} — click any pinned candle to remove`}
          >
            📌 {gridBookmarks.length}
          </span>
        )}
      </div>

      {/* ── Row 2: Shared Info Bar (cursor-hover only) ── */}
      {showInfoBar && (
        <div
          className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-1 border-t border-[#1e293b] pt-1.5"
          data-testid="info-bar"
        >
          {GRID_INTERVALS.map(iv => {
            const snap = gridSnapshot[iv]
            const isUp = snap ? snap.close >= snap.open : null
            return (
              <div key={iv} className="min-w-0">
                <div className={`text-[9px] font-mono font-bold uppercase tracking-widest mb-0.5 ${
                  isUp === true  ? 'text-terminal-green'
                  : isUp === false ? 'text-terminal-red'
                  : 'text-[#475569]'
                }`}>
                  {IV_LABELS[iv]} {snap ? (isUp ? '▲' : '▼') : '—'}
                </div>
                {snap ? (
                  <div className="flex flex-wrap gap-x-1.5 gap-y-0 text-[9px] font-mono">
                    <span><span className="text-[#475569]">O</span><span className="text-[#94a3b8]">{fmt(snap.open)}</span></span>
                    <span>
                      <span className="text-[#475569]">H</span>
                      <span className={isUp ? 'text-terminal-green' : 'text-terminal-red'}>{fmt(snap.high)}</span>
                    </span>
                    <span>
                      <span className="text-[#475569]">L</span>
                      <span className={isUp ? 'text-terminal-green' : 'text-terminal-red'}>{fmt(snap.low)}</span>
                    </span>
                    <span><span className="text-[#475569]">C</span><span className="text-white font-bold">{fmt(snap.close)}</span></span>
                    {snap.volume != null && (
                      <span><span className="text-[#475569]">V</span><span className="text-[#94a3b8]">{fmtVol(snap.volume)}</span></span>
                    )}
                  </div>
                ) : (
                  <span className="text-[9px] font-mono text-[#334155]">not hovered</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
