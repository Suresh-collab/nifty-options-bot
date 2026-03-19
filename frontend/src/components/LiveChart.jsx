import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart } from 'lightweight-charts'
import { useStore } from '../store'
import { fetchOHLCV } from '../lib/yahooFetch'

const INTERVALS = [
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
]

export default function LiveChart() {
  const chartRef = useRef(null)
  const chartInstance = useRef(null)
  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  const lastDataRef = useRef([])
  const isFirstLoad = useRef(true)
  const { ticker } = useStore()
  const [interval, setInterval_] = useState('5m')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastPrice, setLastPrice] = useState(null)
  const [priceChange, setPriceChange] = useState(0)

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
      height: 400,
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

    chartInstance.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    const handleResize = () => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartInstance.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
    }
  }, [])

  const fetchChart = useCallback(async (fullLoad = false) => {
    if (fullLoad) setLoading(true)
    try {
      // Try server-side first (works on localhost), fall back to client-side Yahoo fetch
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

      const prev = lastDataRef.current
      const isNewData = prev.length === 0 || fullLoad

      if (isNewData) {
        // Full data load
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
        if (isFirstLoad.current) {
          chartInstance.current?.timeScale().fitContent()
          isFirstLoad.current = false
        }
      } else {
        // Incremental update — only update changed/new candles
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
      }

      lastDataRef.current = data

      // Update price display
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
  }, [ticker, interval])

  useEffect(() => {
    // Reset on ticker/interval change
    lastDataRef.current = []
    isFirstLoad.current = true
    fetchChart(true)

    // Live polling every 10 seconds
    const iv = window.setInterval(() => fetchChart(false), 10000)
    return () => window.clearInterval(iv)
  }, [ticker, interval, fetchChart])

  const changeColor = priceChange >= 0 ? 'text-terminal-green' : 'text-terminal-red'
  const changeSign = priceChange >= 0 ? '+' : ''

  return (
    <div className="bg-terminal-surface border border-terminal-border rounded-lg overflow-hidden">
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
          {loading && <span className="text-xs font-mono text-terminal-amber animate-pulse">Loading...</span>}
        </div>
        <div className="flex gap-1">
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
        </div>
      </div>
      {error && (
        <div className="px-4 py-2 text-xs font-mono text-terminal-red">
          Chart error: {error}
        </div>
      )}
      <div ref={chartRef} />
    </div>
  )
}
