import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart } from 'lightweight-charts'

// IST offset
const IST_OFFSET = 19800

/**
 * Build Yahoo Finance symbol for an NSE option.
 * Format examples:
 *   NIFTY 22800 PE expiring 20-Mar-2025 → NIFTY25MAR22800PE.NS
 *   NIFTY 23000 CE expiring 27-Mar-2025 → NIFTY25MAR2723000CE.NS (weekly)
 */
function buildYahooOptionSymbol(ticker, strike, type, expiry) {
  const t = ticker.toUpperCase()
  const ce_pe = type.toUpperCase()
  const s = Math.round(strike)

  if (!expiry) {
    // Guess current week's expiry (Thursday for NIFTY)
    const now = new Date()
    const day = now.getDay()
    const daysToThurs = (4 - day + 7) % 7 || 7
    const expDate = new Date(now.getTime() + daysToThurs * 86400000)
    const yy = String(expDate.getFullYear()).slice(-2)
    const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
    const mon = months[expDate.getMonth()]
    const dd = String(expDate.getDate()).padStart(2, '0')
    return `${t}${yy}${mon}${dd}${s}${ce_pe}.NS`
  }

  // Parse expiry like "20-Mar-2025" or "27-Mar-2025"
  const parts = expiry.split('-')
  if (parts.length === 3) {
    const dd = parts[0].padStart(2, '0')
    const mon = parts[1].toUpperCase()
    const yy = parts[2].slice(-2)
    return `${t}${yy}${mon}${dd}${s}${ce_pe}.NS`
  }

  return null
}

/**
 * Fetch option premium OHLCV from Yahoo Finance.
 */
async function fetchOptionChart(symbol) {
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
      if (!result || !result.timestamp) continue

      const timestamps = result.timestamp
      const quote = result.indicators?.quote?.[0] || {}
      const candles = []
      for (let i = 0; i < timestamps.length; i++) {
        const o = quote.open?.[i], h = quote.high?.[i], l = quote.low?.[i], c = quote.close?.[i], v = quote.volume?.[i]
        if (o == null || c == null) continue
        candles.push({
          time: timestamps[i] + IST_OFFSET,
          open: Math.round(o * 100) / 100,
          high: Math.round(h * 100) / 100,
          low: Math.round(l * 100) / 100,
          close: Math.round(c * 100) / 100,
          volume: v || 0,
        })
      }

      const meta = result.meta || {}
      return {
        candles,
        ltp: meta.regularMarketPrice,
        prevClose: meta.chartPreviousClose,
        symbol: meta.symbol,
      }
    } catch {}
  }
  return null
}

export default function OptionChart({ ticker = 'NIFTY', expiry }) {
  const chartRef = useRef(null)
  const chartInstance = useRef(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [optionData, setOptionData] = useState(null)
  const [parsedOption, setParsedOption] = useState(null)

  // Parse user input like "22800 PE" or "23000 CE"
  const parseQuery = useCallback((q) => {
    const cleaned = q.trim().toUpperCase()
    // Match patterns: "22800 PE", "22800PE", "23000 CE", "NIFTY 22800 PE"
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

    // Try multiple symbol formats
    const symbols = []
    if (expiry) {
      const sym = buildYahooOptionSymbol(ticker, parsed.strike, parsed.type, expiry)
      if (sym) symbols.push(sym)
    }
    // Try current week's Thursday
    const now = new Date()
    const day = now.getDay()
    const daysToThurs = (4 - day + 7) % 7 || 7
    const expDate = new Date(now.getTime() + daysToThurs * 86400000)
    const yy = String(expDate.getFullYear()).slice(-2)
    const months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
    const mon = months[expDate.getMonth()]
    const dd = String(expDate.getDate()).padStart(2, '0')
    symbols.push(`${ticker}${yy}${mon}${dd}${parsed.strike}${parsed.type}.NS`)
    // Also try monthly format (without day)
    symbols.push(`${ticker}${yy}${mon}${parsed.strike}${parsed.type}.NS`)
    // Try next week too
    const nextExpDate = new Date(expDate.getTime() + 7 * 86400000)
    const nMon = months[nextExpDate.getMonth()]
    const nDd = String(nextExpDate.getDate()).padStart(2, '0')
    const nYy = String(nextExpDate.getFullYear()).slice(-2)
    symbols.push(`${ticker}${nYy}${nMon}${nDd}${parsed.strike}${parsed.type}.NS`)

    // De-duplicate
    const uniqueSymbols = [...new Set(symbols)]

    let data = null
    for (const sym of uniqueSymbols) {
      data = await fetchOptionChart(sym)
      if (data && data.candles.length > 0) break
    }

    if (!data || data.candles.length === 0) {
      setError(`Could not fetch chart for ${ticker} ${parsed.strike} ${parsed.type}. Option may not be actively traded or symbol format may differ.`)
      setLoading(false)
      return
    }

    setOptionData(data)
    setLoading(false)
  }, [query, ticker, expiry, parseQuery])

  // Render chart when data changes
  useEffect(() => {
    if (!optionData || !chartRef.current) return

    // Clean up old chart
    if (chartInstance.current) {
      chartInstance.current.remove()
      chartInstance.current = null
    }

    const chart = createChart(chartRef.current, {
      layout: {
        background: { color: '#0f172a' },
        textColor: '#94a3b8',
        fontSize: 10,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: '#1e293b' },
      timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false },
      width: chartRef.current.clientWidth,
      height: 250,
    })

    const series = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderDownColor: '#ef4444',
      borderUpColor: '#22c55e',
      wickDownColor: '#ef4444',
      wickUpColor: '#22c55e',
    })

    const volSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })

    series.setData(optionData.candles.map(d => ({
      time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
    })))
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
      if (chartInstance.current) {
        chartInstance.current.remove()
        chartInstance.current = null
      }
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

      {parsedOption && optionData && (
        <div className="px-4 pb-2">
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="text-white font-medium">
              {ticker} {parsedOption.strike} {parsedOption.type}
            </span>
            {ltp && (
              <span className="text-white">₹{ltp.toFixed(2)}</span>
            )}
            {change != null && (
              <span className={`px-1.5 py-0.5 rounded ${change >= 0 ? 'bg-terminal-green/10 text-terminal-green' : 'bg-terminal-red/10 text-terminal-red'}`}>
                {change >= 0 ? '+' : ''}{change.toFixed(2)} ({changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%)
              </span>
            )}
            <span className="text-[#475569]">5m · 5D</span>
          </div>
        </div>
      )}

      {optionData && <div ref={chartRef} />}

      {!optionData && !error && !loading && (
        <div className="px-4 pb-4 text-[11px] font-mono text-[#475569]">
          Enter a strike price and type (CE/PE) to view the option's premium chart.
          Example: "22800 PE" to see NIFTY 22800 Put premium movement.
        </div>
      )}
    </div>
  )
}
