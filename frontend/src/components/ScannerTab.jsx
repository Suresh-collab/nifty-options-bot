import { useEffect, useRef } from 'react'
import { useStore } from '../store'

// ─── helpers ────────────────────────────────────────────────────────────────

function chgColor(pct) {
  if (pct > 0) return 'text-green-400'
  if (pct < 0) return 'text-red-400'
  return 'text-[#64748b]'
}

function chgBg(pct) {
  if (pct > 0) return 'bg-green-400/10'
  if (pct < 0) return 'bg-red-400/10'
  return ''
}

function Badge({ children, color }) {
  const cls = {
    green:  'bg-green-400/10 text-green-400 border-green-400/20',
    red:    'bg-red-400/10   text-red-400   border-red-400/20',
    yellow: 'bg-yellow-400/10 text-yellow-400 border-yellow-400/20',
    blue:   'bg-blue-400/10  text-blue-400  border-blue-400/20',
  }[color] || 'bg-[#1e293b] text-[#64748b] border-[#334155]'
  return (
    <span className={`text-[9px] font-mono border rounded px-1.5 py-0.5 ${cls}`}>
      {children}
    </span>
  )
}

function ScanTable({ rows, columns, emptyMsg }) {
  if (!rows || rows.length === 0) {
    return <div className="text-[#475569] font-mono text-xs py-4 text-center">{emptyMsg}</div>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] font-mono">
        <thead>
          <tr className="border-b border-[#1e293b]">
            {columns.map(c => (
              <th key={c.key} className="pb-2 pr-3 text-left text-[#475569] font-normal uppercase tracking-wider text-[9px] whitespace-nowrap">
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-[#0d1526] hover:bg-white/[0.02] transition-colors">
              {columns.map(c => (
                <td key={c.key} className={`py-2 pr-3 whitespace-nowrap ${c.className?.(row) || ''}`}>
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── column definitions ─────────────────────────────────────────────────────

const gainersColumns = [
  { key: 'symbol', label: 'Symbol', render: r => <span className="font-bold text-white">{r.symbol}</span> },
  { key: 'close',  label: 'LTP',    render: r => <span className="text-[#94a3b8]">₹{r.close.toLocaleString('en-IN')}</span> },
  {
    key: 'change_pct', label: 'Change',
    render: r => (
      <span className={`font-bold px-2 py-0.5 rounded ${chgBg(r.change_pct)} ${chgColor(r.change_pct)}`}>
        {r.change_pct > 0 ? '+' : ''}{r.change_pct}%
      </span>
    ),
  },
  { key: 'volume', label: 'Volume', render: r => <span className="text-[#64748b]">{(r.volume / 1e6).toFixed(1)}M</span> },
]

const losersColumns = gainersColumns

const volSpikeColumns = [
  { key: 'symbol',    label: 'Symbol',    render: r => <span className="font-bold text-white">{r.symbol}</span> },
  { key: 'close',     label: 'LTP',       render: r => <span className="text-[#94a3b8]">₹{r.close.toLocaleString('en-IN')}</span> },
  { key: 'change_pct',label: 'Change',    render: r => <span className={chgColor(r.change_pct)}>{r.change_pct > 0 ? '+' : ''}{r.change_pct}%</span> },
  { key: 'vol_ratio', label: 'Vol Ratio', render: r => <Badge color="yellow">{r.vol_ratio}x</Badge> },
  { key: 'volume',    label: 'Volume',    render: r => <span className="text-[#64748b]">{(r.volume / 1e6).toFixed(1)}M</span> },
]

const breakoutColumns = [
  { key: 'symbol', label: 'Symbol', render: r => <span className="font-bold text-white">{r.symbol}</span> },
  { key: 'close',  label: 'LTP',    render: r => <span className="text-[#94a3b8]">₹{r.close.toLocaleString('en-IN')}</span> },
  {
    key: 'type', label: 'Signal',
    render: r => r.breakout
      ? <Badge color="green">BREAKOUT</Badge>
      : <Badge color="red">BREAKDOWN</Badge>,
  },
  { key: 'change_pct', label: 'Change', render: r => <span className={chgColor(r.change_pct)}>{r.change_pct > 0 ? '+' : ''}{r.change_pct}%</span> },
  { key: 'high_20d', label: '20D High', render: r => <span className="text-[#64748b]">₹{r.high_20d.toLocaleString('en-IN')}</span> },
  { key: 'low_20d',  label: '20D Low',  render: r => <span className="text-[#64748b]">₹{r.low_20d.toLocaleString('en-IN')}</span> },
]

// ─── component ──────────────────────────────────────────────────────────────

export default function ScannerTab() {
  const { scannerData, scannerLoading, fetchScannerResults, runScanner } = useStore()
  const wsRef = useRef(null)

  useEffect(() => {
    fetchScannerResults()

    // Subscribe to WebSocket scanner_update events
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/live`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'scanner_update' && msg.data) {
          useStore.setState({ scannerData: msg.data, scannerLoading: false })
        }
      } catch {}
    }
    return () => ws.close()
  }, [])

  const scannedAt = scannerData?.scanned_at
    ? new Date(scannerData.scanned_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest">Market Scanner</div>
          {scannedAt && (
            <div className="text-[9px] font-mono text-[#334155] mt-0.5">
              Last scan: {scannedAt} · {scannerData?.total_scanned || 0} stocks scanned
            </div>
          )}
          {scannerData?.error && (
            <div className="text-[9px] font-mono text-red-400 mt-0.5">Error: {scannerData.error}</div>
          )}
        </div>
        <button
          onClick={runScanner}
          disabled={scannerLoading}
          className="px-4 py-1.5 text-[10px] font-mono rounded border border-terminal-blue text-terminal-blue hover:bg-terminal-blue hover:text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {scannerLoading ? 'Scanning…' : 'Scan Now'}
        </button>
      </div>

      {/* 2×2 grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Gainers */}
        <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest">Top Gainers</div>
            <Badge color="green">{scannerData?.gainers?.length || 0}</Badge>
          </div>
          <ScanTable rows={scannerData?.gainers} columns={gainersColumns} emptyMsg="No gainers found" />
        </div>

        {/* Losers */}
        <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest">Top Losers</div>
            <Badge color="red">{scannerData?.losers?.length || 0}</Badge>
          </div>
          <ScanTable rows={scannerData?.losers} columns={losersColumns} emptyMsg="No losers found" />
        </div>

        {/* Volume Spikes */}
        <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest">Volume Spikes ≥ 2×</div>
            <Badge color="yellow">{scannerData?.volume_spikes?.length || 0}</Badge>
          </div>
          <ScanTable rows={scannerData?.volume_spikes} columns={volSpikeColumns} emptyMsg="No volume spikes today" />
        </div>

        {/* Breakouts */}
        <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <div className="text-[10px] font-mono text-[#475569] uppercase tracking-widest">20-Day Breakouts / Breakdowns</div>
            <Badge color="blue">{scannerData?.breakouts?.length || 0}</Badge>
          </div>
          <ScanTable rows={scannerData?.breakouts} columns={breakoutColumns} emptyMsg="No breakouts today" />
        </div>
      </div>
    </div>
  )
}
