import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart } from 'lightweight-charts'
import { useStore } from '../store'
import { fetchOHLCV } from '../lib/yahooFetch'
import { computeChartSignals } from '../lib/chartIndicators'

const INTERVALS = [
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
]

// IST offset: +5:30 = 19800 seconds
// Applied here (single point) so ALL data sources display IST on the chart
const IST_OFFSET = 19800

function toIST(data) {
  return data.map(d => ({ ...d, time: d.time + IST_OFFSET }))
}

export default function LiveChart() {
  const chartRef = useRef(null)
  const containerRef = useRef(null)
  const chartInstance = useRef(null)
  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  const stLineSeriesRef = useRef(null)
  const srLinesRef = useRef([])
  const lastDataRef = useRef([])
  const isFirstLoad = useRef(true)
  const { ticker } = useStore()
  const [interval, setInterval_] = useState('5m')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastPrice, setLastPrice] = useState(null)
  const [priceChange, setPriceChange] = useState(0)
  const [showSignals, setShowSignals] = useState(true)
  const [signalStats, setSignalStats] = useState(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  // Fullscreen toggle
  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {})
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {})
    }
  }, [])

  // Listen for fullscreen exit via Escape
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  useEffect(() => {
    if (!chartRef.current) return

    const chart = createChart(chartRef.current, {
      layout: {
        background: { color: '#1e293b' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: '#334155' },
        horzLines: { color: '#334155' },
      },
      crosshair: {
        mode: 0,
        vertLine: { color: '#475569', labelBackgroundColor: '#334155' },
        horzLine: { color: '#475569', labelBackgroundColor: '#334155' },
      },
      rightPriceScale: {
        borderColor: '#334155',
      },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartRef.current.clientWidth,
      height: isFullscreen ? window.innerHeight - 120 : 420,
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderDownColor: '#ef4444',
      borderUpColor: '#22c55e',
      wickDownColor: '#ef4444',
      wickUpColor: '#22c55e',
    })

    const volumeSeries = chart.addHistogramSeries({
      color: '#3b82f6',
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    })

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    })

    // SuperTrend overlay line
    const stLineSeries = chart.addLineSeries({
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })

    chartInstance.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    stLineSeriesRef.current = stLineSeries

    const handleResize = () => {
      if (chartRef.current) {
        chart.applyOptions({
          width: chartRef.current.clientWidth,
          height: document.fullscreenElement ? window.innerHeight - 120 : 420,
        })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartInstance.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      stLineSeriesRef.current = null
      srLinesRef.current = []
    }
  }, [isFullscreen])

  const applySignals = useCallback((data) => {
    if (!showSignals || !candleSeriesRef.current || !chartInstance.current) return

    try {
      const { markers, levels, tpSlBoxes, trendLine } = computeChartSignals(data)

      // Apply buy/sell markers
      candleSeriesRef.current.setMarkers(markers)

      // Apply SuperTrend line with color segments
      if (stLineSeriesRef.current && trendLine.length > 0) {
        stLineSeriesRef.current.setData(
          trendLine.map(p => ({ time: p.time, value: p.value, color: p.color }))
        )
      }

      // Remove old S/R lines
      for (const line of srLinesRef.current) {
        try { candleSeriesRef.current.removePriceLine(line) } catch {}
      }
      srLinesRef.current = []

      // Draw support/resistance levels
      for (const level of levels) {
        const priceLine = candleSeriesRef.current.createPriceLine({
          price: level.price,
          color: level.type === 'support' ? '#22c55e50' : '#ef444450',
          lineWidth: 1,
          lineStyle: 2, // dashed
          axisLabelVisible: true,
          title: `${level.type === 'support' ? 'S' : 'R'} ${level.price.toFixed(0)}`,
        })
        srLinesRef.current.push(priceLine)
      }

      // Update signal stats
      const buyCount = markers.filter(m => m.text.includes('BUY')).length
      const sellCount = markers.filter(m => m.text.includes('SELL')).length
      const strongCount = markers.filter(m => m.text.includes('STRONG')).length
      setSignalStats({
        total: markers.length,
        buys: buyCount,
        sells: sellCount,
        strong: strongCount,
        levels: levels.length,
        lastSignal: markers.length > 0 ? markers[markers.length - 1] : null,
      })
    } catch (e) {
      console.warn('Signal computation error:', e)
    }
  }, [showSignals])

  const fetchChart = useCallback(async (fullLoad = false) => {
    if (fullLoad) setLoading(true)
    try {
      let data
      try {
        const res = await fetch(`/api/chart/${ticker}?interval=${interval}`)
        if (res.ok) {
          data = await res.json()
        }
      } catch {}

      if (!data || data.length === 0) {
        data = await fetchOHLCV(ticker, interval)
      }

      if (!candleSeriesRef.current || data.length === 0) return

      // Convert all timestamps to IST for display (single point of conversion)
      data = toIST(data)

      const prev = lastDataRef.current
      const isNewData = prev.length === 0 || fullLoad

      if (isNewData) {
        candleSeriesRef.current.setData(
          data.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close }))
        )
        volumeSeriesRef.current.setData(
          data.map(d => ({
            time: d.time,
            value: d.volume,
            color: d.close >= d.open ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)',
          }))
        )

        applySignals(data)

        if (isFirstLoad.current) {
          chartInstance.current?.timeScale().fitContent()
          isFirstLoad.current = false
        }
      } else {
        const lastOldTime = prev.length > 0 ? prev[prev.length - 1].time : 0
        for (const d of data) {
          if (d.time >= lastOldTime) {
            candleSeriesRef.current.update({
              time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
            })
            volumeSeriesRef.current.update({
              time: d.time,
              value: d.volume,
              color: d.close >= d.open ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)',
            })
          }
        }
        applySignals(data)
      }

      lastDataRef.current = data

      const latest = data[data.length - 1]
      const prevCandle = data.length > 1 ? data[data.length - 2] : latest
      setLastPrice(latest.close)
      setPriceChange(((latest.close - prevCandle.close) / prevCandle.close * 100))
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [ticker, interval, applySignals])

  useEffect(() => {
    lastDataRef.current = []
    isFirstLoad.current = true
    fetchChart(true)

    const iv = window.setInterval(() => fetchChart(false), 10000)
    return () => window.clearInterval(iv)
  }, [ticker, interval, fetchChart])

  // Re-apply signals when toggle changes
  useEffect(() => {
    if (lastDataRef.current.length > 0) {
      if (showSignals) {
        applySignals(lastDataRef.current)
      } else {
        candleSeriesRef.current?.setMarkers([])
        stLineSeriesRef.current?.setData([])
        for (const line of srLinesRef.current) {
          try { candleSeriesRef.current?.removePriceLine(line) } catch {}
        }
        srLinesRef.current = []
        setSignalStats(null)
      }
    }
  }, [showSignals, applySignals])

  const changeColor = priceChange >= 0 ? 'text-terminal-green' : 'text-terminal-red'
  const changeSign = priceChange >= 0 ? '+' : ''

  return (
    <div ref={containerRef} className={`bg-terminal-surface border border-terminal-border rounded-lg overflow-hidden ${isFullscreen ? 'bg-terminal-bg' : ''}`}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-terminal-border">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm font-bold text-terminal-text">{ticker}</span>
          {lastPrice && (
            <>
              <span className="font-mono text-sm text-terminal-text">
                {lastPrice.toFixed(2)}
              </span>
              <span className={`font-mono text-xs ${changeColor}`}>
                {changeSign}{priceChange.toFixed(2)}%
              </span>
            </>
          )}
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-terminal-green opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-terminal-green"></span>
          </span>
          <span className="text-xs font-mono text-terminal-dim">LIVE</span>
          <span className="text-xs font-mono text-terminal-blue">IST</span>
          {loading && <span className="text-xs font-mono text-terminal-amber animate-pulse">Loading...</span>}
        </div>
        <div className="flex items-center gap-2">
          {/* Signal toggle */}
          <button
            onClick={() => setShowSignals(!showSignals)}
            className={`px-2 py-0.5 text-xs font-mono rounded transition-colors ${
              showSignals
                ? 'bg-terminal-green/20 text-terminal-green border border-terminal-green/30'
                : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-border border border-transparent'
            }`}
            title="Toggle buy/sell signals, SuperTrend, and S/R levels"
          >
            {showSignals ? 'Signals ON' : 'Signals OFF'}
          </button>
          {/* Interval buttons */}
          {INTERVALS.map(i => (
            <button
              key={i.value}
              onClick={() => setInterval_(i.value)}
              className={`px-2 py-0.5 text-xs font-mono rounded transition-colors ${
                interval === i.value
                  ? 'bg-terminal-blue text-white'
                  : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-border'
              }`}
            >
              {i.label}
            </button>
          ))}
          {/* Fullscreen button */}
          <button
            onClick={toggleFullscreen}
            className="px-2 py-0.5 text-xs font-mono rounded text-terminal-dim hover:text-terminal-text hover:bg-terminal-border transition-colors border border-transparent"
            title={isFullscreen ? 'Exit fullscreen (Esc)' : 'View chart in fullscreen'}
          >
            {isFullscreen ? '⊠ Exit' : '⛶ Fullscreen'}
          </button>
        </div>
      </div>

      {/* Signal stats bar with explanations */}
      {showSignals && signalStats && (
        <div className="px-4 py-1.5 border-b border-terminal-border/50 flex items-center gap-4 text-[10px] font-mono">
          <span className="text-terminal-dim">SIGNALS:</span>
          <span className="text-terminal-green">{signalStats.buys} BUY</span>
          <span className="text-terminal-red">{signalStats.sells} SELL</span>
          {signalStats.strong > 0 && (
            <span className="text-terminal-amber">{signalStats.strong} STRONG</span>
          )}
          <span className="text-terminal-dim">|</span>
          <span className="text-terminal-dim">S/R: {signalStats.levels} levels</span>
          {signalStats.lastSignal && (
            <>
              <span className="text-terminal-dim">|</span>
              <span className={signalStats.lastSignal.text.includes('BUY') ? 'text-terminal-green' : 'text-terminal-red'}>
                Last: {signalStats.lastSignal.text}
              </span>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="px-4 py-2 text-xs font-mono text-terminal-red">
          Chart error: {error}
        </div>
      )}
      <div ref={chartRef} />

      {/* Legend with explanations */}
      {showSignals && (
        <div className="px-4 py-2 border-t border-terminal-border/50 space-y-1.5">
          <div className="flex items-center gap-4 text-[10px] font-mono text-terminal-dim flex-wrap">
            <span><span className="inline-block w-3 h-0.5 bg-terminal-green mr-1 align-middle" />SuperTrend Up</span>
            <span><span className="inline-block w-3 h-0.5 bg-terminal-red mr-1 align-middle" />SuperTrend Down</span>
            <span><span className="text-terminal-green mr-1">▲</span>Buy Signal</span>
            <span><span className="text-terminal-red mr-1">▼</span>Sell Signal</span>
            <span><span className="inline-block w-3 h-0.5 bg-terminal-green/50 mr-1 align-middle" />Support (floor)</span>
            <span><span className="inline-block w-3 h-0.5 bg-terminal-red/50 mr-1 align-middle" />Resistance (ceiling)</span>
          </div>
          <div className="text-[10px] font-mono text-terminal-dim/70 leading-relaxed">
            <span className="text-terminal-green">S (Support)</span> = price level where stock tends to bounce up (good to buy near).{' '}
            <span className="text-terminal-red">R (Resistance)</span> = price level where stock tends to fall back (consider selling near).{' '}
            Signals appear only when 3+ indicators agree (reduces false signals).
          </div>
        </div>
      )}
    </div>
  )
}
