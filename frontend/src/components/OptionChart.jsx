import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart } from 'lightweight-charts'

const IST_OFFSET = 19800

/**
 * Build all possible Yahoo Finance symbol formats for an NSE option.
 * Yahoo uses different formats and we try multiple to find the right one.
 */
function buildSymbolCandidates(ticker, strike, type) {
  const t = ticker.toUpperCase()
  const s = Math.round(strike)
  const ce_pe = type.toUpperCase()
  const symbols = []

  // Get upcoming Thursdays (NIFTY weekly expiry)
  const now = new Date()
  for (let weekOffset = 0; weekOffset < 3; weekOffset++) {
    const d = new Date(now.getTime() + weekOffset * 7 * 86400000)
    // Find Thursday of this week
    const day = d.getDay()
    const daysToThurs = (4 - day + 7) % 7
    const thursday = new Date(d.getTime() + daysToThurs * 86400000)

    const yy = String(thursday.getFullYear()).slice(-2)
    const mm = String(thursday.getMonth() + 1).padStart(2, '0')
    const dd = String(thursday.getDate()).padStart(2, '0')
    const months3 = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
    const mon = months3[thursday.getMonth()]
    // Single letter month codes used by some Yahoo formats
    const monthLetters = ['1','2','3','4','5','6','7','8','9','O','N','D']
    const ml = monthLetters[thursday.getMonth()]

    // Format 1: NIFTY25MAR2023000PE.NS (YY + MON3 + DD + STRIKE + CE/PE)
    symbols.push(`${t}${yy}${mon}${dd}${s}${ce_pe}.NS`)
    // Format 2: NIFTY25032023000PE.NS (YY + MM + DD + STRIKE + CE/PE)
    symbols.push(`${t}${yy}${mm}${dd}${s}${ce_pe}.NS`)
    // Format 3: NIFTY2532023000PE.NS (YY + M_letter + DD + STRIKE + CE/PE)
    symbols.push(`${t}${yy}${ml}${dd}${s}${ce_pe}.NS`)
    // Format 4: NIFTY25MAR23000PE.NS (without day - monthly)
    if (weekOffset === 0) {
      symbols.push(`${t}${yy}${mon}${s}${ce_pe}.NS`)
    }
  }

  return [...new Set(symbols)] // de-duplicate
}

/**
 * Fetch option premium OHLCV from Yahoo Finance.
 */
async function fetchOptionChart(symbols) {
  for (const symbol of symbols) {
    const urls = [
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=5m&range=5d`,
      `/yf-proxy/v8/finance/chart/${encodeURIComponent(symbol)}?interval=5m&range=5d`,
    ]

    for (const url of urls) {
      try {
        const res = await fetch(url)
        if (!res.ok) continue
        const json = await res.json()
        const result = json.chart?.result?.[0]
        if (!result?.timestamp || result.timestamp.length === 0) continue

        const timestamps = result.timestamp
        const quote = result.indicators?.quote?.[0] || {}
        const candles = []
        for (let i = 0; i < timestamps.length; i++) {
          const o = quote.open?.[i], h = quote.high?.[i], l = quote.low?.[i], c = quote.close?.[i], v = quote.volume?.[i]
          if (o == null || c == null) continue
          candles.push({
            time: timestamps[i] + IST_OFFSET,
            open: Math.round(o * 100) / 100,
            high: Math.round((h || o) * 100) / 100,
            low: Math.round((l || o) * 100) / 100,
            close: Math.round(c * 100) / 100,
            volume: v || 0,
          })
        }

        if (candles.length < 2) continue

        const meta = result.meta || {}
        return {
          candles,
          ltp: meta.regularMarketPrice,
          prevClose: meta.chartPreviousClose,
          symbol,
        }
      } catch {}
    }
  }
  return null
}

/**
 * Try fetching option chain from NSE directly (works from Indian IPs).
 */
async function fetchNSEOptionLTP(ticker, strike, type) {
  try {
    const url = `https://www.nseindia.com/api/option-chain-indices?symbol=${ticker}`
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
      },
    })
    if (!res.ok) return null
    const data = await res.json()
    const records = data?.records?.data || []
    const key = type === 'CE' ? 'CE' : 'PE'

    for (const rec of records) {
      if (rec.strikePrice === strike && rec[key]) {
        return {
          ltp: rec[key].lastPrice,
          iv: rec[key].impliedVolatility,
          oi: rec[key].openInterest,
          change: rec[key].change,
          changePct: rec[key].pchangeinOpenInterest,
          volume: rec[key].totalTradedVolume,
          bidPrice: rec[key].bidprice,
          askPrice: rec[key].askPrice,
        }
      }
    }
  } catch {}
  return null
}

export default function OptionChart({ ticker = 'NIFTY', expiry }) {
  const chartRef = useRef(null)
  const chartInstance = useRef(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [optionData, setOptionData] = useState(null)
  const [nseLTP, setNseLTP] = useState(null)
  const [parsedOption, setParsedOption] = useState(null)

  const parseQuery = useCallback((q) => {
    const cleaned = q.trim().toUpperCase()
    const match = cleaned.match(/(\d{4,6})\s*(CE|PE|CALL|PUT)/i)
    if (!match) return null
    const strike = parseInt(match[1])
    let type = match[2]
    if (type === 'CALL') type = 'CE'
    if (type === 'PUT') type = 'PE'
    return { strike, type }
  }, [])

  const handleSearch = useCallback(async () => {
    const parsed = parseQuery(query)
    if (!parsed) {
      setError('Enter strike + type, e.g., "22800 PE" or "23000 CE"')
      return
    }
    setParsedOption(parsed)
    setLoading(true)
    setError(null)
    setOptionData(null)
    setNseLTP(null)

    // Try Yahoo Finance chart with multiple symbol formats
    const symbols = buildSymbolCandidates(ticker, parsed.strike, parsed.type)
    const chartData = await fetchOptionChart(symbols)

    if (chartData && chartData.candles.length > 0) {
      setOptionData(chartData)
      setLoading(false)
      return
    }

    // Yahoo failed — try NSE direct for at least LTP data
    const nseData = await fetchNSEOptionLTP(ticker, parsed.strike, parsed.type)
    if (nseData) {
      setNseLTP(nseData)
      setError(null)
      setLoading(false)
      return
    }

    // Both failed
    setError(`Chart data not available for ${ticker} ${parsed.strike} ${parsed.type}. Try during market hours or check the strike price.`)
    setLoading(false)
  }, [query, ticker, parseQuery])

  // Render chart when data changes
  useEffect(() => {
    if (!optionData || !chartRef.current) return
    if (chartInstance.current) {
      chartInstance.current.remove()
      chartInstance.current = null
    }

    const chart = createChart(chartRef.current, {
      layout: { background: { color: '#0f172a' }, textColor: '#94a3b8', fontSize: 10, fontFamily: 'monospace' },
      grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: '#1e293b' },
      timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false },
      width: chartRef.current.clientWidth,
      height: 220,
    })

    const series = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderDownColor: '#ef4444', borderUpColor: '#22c55e',
      wickDownColor: '#ef4444', wickUpColor: '#22c55e',
    })

    const volSeries = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'vol' })
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })

    series.setData(optionData.candles.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })))
    volSeries.setData(optionData.candles.map(d => ({
      time: d.time, value: d.volume,
      color: d.close >= d.open ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)',
    })))

    chart.timeScale().fitContent()
    chartInstance.current = chart

    const handleResize = () => {
      if (chartRef.current && chartInstance.current) {
        chartInstance.current.applyOptions({ width: chartRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      if (chartInstance.current) { chartInstance.current.remove(); chartInstance.current = null }
    }
  }, [optionData])

  const ltp = optionData?.ltp
  const prevClose = optionData?.prevClose
  const change = ltp && prevClose ? ltp - prevClose : null
  const changePct = change && prevClose ? (change / prevClose) * 100 : null

  return (
    <div className="bg-[#0f172a] border border-[#1e293b] rounded-lg overflow-hidden">
      <div className="px-4 py-3">
        <div className="text-xs font-mono text-[#64748b] uppercase tracking-widest mb-2">
          Option Premium Chart
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="e.g., 22800 PE or 23000 CE"
            className="flex-1 bg-[#1e293b] border border-[#334155] rounded px-3 py-2
              text-white font-mono text-sm focus:outline-none focus:border-terminal-blue
              placeholder:text-[#475569] transition-colors"
          />
          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="px-4 py-2 rounded bg-terminal-blue/20 border border-terminal-blue
              text-terminal-blue font-mono text-sm hover:bg-terminal-blue hover:text-white
              transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? '...' : 'View'}
          </button>
        </div>
      </div>

      {error && (
        <div className="px-4 pb-3">
          <div className="text-terminal-amber text-[11px] font-mono p-2 rounded bg-terminal-amber/5 border border-terminal-amber/20">
            {error}
          </div>
        </div>
      )}

      {/* Chart header with LTP */}
      {parsedOption && (optionData || nseLTP) && (
        <div className="px-4 pb-2">
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="text-white font-medium">
              {ticker} {parsedOption.strike} {parsedOption.type}
            </span>
            {ltp && <span className="text-white">₹{ltp.toFixed(2)}</span>}
            {nseLTP && !ltp && <span className="text-white">₹{nseLTP.ltp}</span>}
            {change != null && (
              <span className={`px-1.5 py-0.5 rounded ${change >= 0 ? 'bg-terminal-green/10 text-terminal-green' : 'bg-terminal-red/10 text-terminal-red'}`}>
                {change >= 0 ? '+' : ''}{change.toFixed(2)} ({changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%)
              </span>
            )}
            {optionData && <span className="text-[#475569]">5m · 5D</span>}
          </div>
        </div>
      )}

      {/* Chart canvas */}
      {optionData && <div ref={chartRef} />}

      {/* NSE LTP fallback (no chart, but show option data) */}
      {nseLTP && !optionData && parsedOption && (
        <div className="px-4 pb-4">
          <div className="grid grid-cols-2 gap-2">
            {[
              { l: 'LTP', v: `₹${nseLTP.ltp}`, cls: 'text-white font-medium' },
              { l: 'IV', v: nseLTP.iv ? `${nseLTP.iv}%` : '--' },
              { l: 'OI', v: nseLTP.oi ? Number(nseLTP.oi).toLocaleString('en-IN') : '--' },
              { l: 'Volume', v: nseLTP.volume ? Number(nseLTP.volume).toLocaleString('en-IN') : '--' },
              { l: 'Bid', v: nseLTP.bidPrice ? `₹${nseLTP.bidPrice}` : '--' },
              { l: 'Ask', v: nseLTP.askPrice ? `₹${nseLTP.askPrice}` : '--' },
            ].map(({ l, v, cls }) => (
              <div key={l} className="bg-[#1e293b] rounded p-2 border border-[#334155]">
                <div className="text-[9px] font-mono text-[#475569]">{l}</div>
                <div className={`text-[11px] font-mono ${cls || 'text-[#94a3b8]'}`}>{v}</div>
              </div>
            ))}
          </div>
          <div className="text-[10px] font-mono text-[#475569] mt-2">
            Live data from NSE. Chart view requires Yahoo Finance data.
          </div>
        </div>
      )}

      {!optionData && !nseLTP && !error && !loading && (
        <div className="px-4 pb-4 text-[11px] font-mono text-[#475569] leading-relaxed">
          Enter a strike price and type to view option premium data.
          <br />Example: <span className="text-[#94a3b8]">22800 PE</span> or <span className="text-[#94a3b8]">23000 CE</span>
        </div>
      )}
    </div>
  )
}
