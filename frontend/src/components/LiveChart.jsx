import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart } from 'lightweight-charts'
import { useStore } from '../store'
import { fetchOHLCV } from '../lib/yahooFetch'
import { computeChartSignals } from '../lib/chartIndicators'

const INTERVALS = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
]

// IST offset: +5:30 = 19800 seconds
const IST_OFFSET = 19800

function toIST(data) {
  return data.map(d => ({ ...d, time: d.time + IST_OFFSET }))
}

export default function LiveChart() {
  const chartRef = useRef(null)
  const rsiChartRef = useRef(null)
  const macdChartRef = useRef(null)
  const containerRef = useRef(null)
  const chartInstance = useRef(null)
  const rsiChartInstance = useRef(null)
  const macdChartInstance = useRef(null)
  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  const stLineSeriesRef = useRef(null)
  const ema20SeriesRef = useRef(null)
  const ema50SeriesRef = useRef(null)
  const rsiSeriesRef = useRef(null)
  const rsiOverboughtRef = useRef(null)
  const rsiOversoldRef = useRef(null)
  const macdLineRef = useRef(null)
  const macdSignalRef = useRef(null)
  const macdHistRef = useRef(null)
  const srLinesRef = useRef([])
  const pivotLinesRef = useRef([])
  const lastDataRef = useRef([])
  const isFirstLoad = useRef(true)
  const { ticker } = useStore()
  const [interval, setInterval_] = useState('5m')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastPrice, setLastPrice] = useState(null)
  const [priceChange, setPriceChange] = useState(0)
  const [showSignals, setShowSignals] = useState(true)
  const [showRSI, setShowRSI] = useState(false)
  const [showMACD, setShowMACD] = useState(false)
  const [showVolume, setShowVolume] = useState(true)
  const [showPivots, setShowPivots] = useState(false)
  const [showEMA, setShowEMA] = useState(false)
  const [signalStats, setSignalStats] = useState(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [crosshairData, setCrosshairData] = useState(null)

  // Fullscreen toggle
  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch(() => {})
    } else {
      document.exitFullscreen().catch(() => {})
    }
  }, [])

  // Sync fullscreen state and resize charts
  useEffect(() => {
    const handler = () => {
      const fs = !!document.fullscreenElement
      setIsFullscreen(fs)
      if (chartInstance.current && chartRef.current) {
        const subPanels = (showRSI ? 150 : 0) + (showMACD ? 150 : 0)
        const mainH = fs ? window.innerHeight - subPanels - 120 : 500
        chartInstance.current.applyOptions({
          width: chartRef.current.clientWidth,
          height: mainH,
        })
        chartInstance.current.timeScale().fitContent()
      }
      if (rsiChartInstance.current && rsiChartRef.current) {
        rsiChartInstance.current.applyOptions({ width: rsiChartRef.current.clientWidth })
      }
      if (macdChartInstance.current && macdChartRef.current) {
        macdChartInstance.current.applyOptions({ width: macdChartRef.current.clientWidth })
      }
    }
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [showRSI, showMACD])

  // Create main chart ONCE
  useEffect(() => {
    if (!chartRef.current) return

    const chart = createChart(chartRef.current, {
      layout: {
        background: { color: '#0f172a' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: "'Inter', 'SF Pro', system-ui, monospace",
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: {
        mode: 0,
        vertLine: { color: '#475569', labelBackgroundColor: '#334155' },
        horzLine: { color: '#475569', labelBackgroundColor: '#334155' },
      },
      rightPriceScale: {
        borderColor: '#1e293b',
        scaleMargins: { top: 0.05, bottom: 0.2 },
      },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 5,
        barSpacing: 8,
      },
      width: chartRef.current.clientWidth,
      height: 500,
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
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    const stLineSeries = chart.addLineSeries({
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      title: 'SuperTrend',
    })

    // EMA lines (hidden by default, toggled via showEMA)
    const ema20Series = chart.addLineSeries({
      color: '#f59e0b',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      title: 'EMA 20',
      visible: false,
    })
    const ema50Series = chart.addLineSeries({
      color: '#8b5cf6',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      title: 'EMA 50',
      visible: false,
    })

    chartInstance.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    stLineSeriesRef.current = stLineSeries
    ema20SeriesRef.current = ema20Series
    ema50SeriesRef.current = ema50Series

    // Crosshair hover — show OHLCV + indicator values
    chart.subscribeCrosshairMove(param => {
      if (!param.time || !param.seriesData) {
        setCrosshairData(null)
        return
      }
      const candle = param.seriesData.get(candleSeries)
      const vol = param.seriesData.get(volumeSeries)
      const st = param.seriesData.get(stLineSeries)
      const e20 = param.seriesData.get(ema20Series)
      const e50 = param.seriesData.get(ema50Series)
      if (candle) {
        setCrosshairData({
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
          volume: vol?.value,
          supertrend: st?.value,
          ema20: e20?.value,
          ema50: e50?.value,
          isUp: candle.close >= candle.open,
        })
      }
    })

    const handleResize = () => {
      if (chartRef.current && chartInstance.current) {
        chartInstance.current.applyOptions({
          width: chartRef.current.clientWidth,
        })
      }
      ;[rsiChartInstance, macdChartInstance].forEach(ref => {
        if (ref.current) {
          ref.current.applyOptions({ width: chartRef.current?.clientWidth || 0 })
        }
      })
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartInstance.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      stLineSeriesRef.current = null
      ema20SeriesRef.current = null
      ema50SeriesRef.current = null
      srLinesRef.current = []
      pivotLinesRef.current = []
    }
  }, [])

  // Create/destroy RSI sub-chart
  useEffect(() => {
    if (showRSI && rsiChartRef.current && !rsiChartInstance.current) {
      const rsiChart = createChart(rsiChartRef.current, {
        layout: { background: { color: '#0f172a' }, textColor: '#94a3b8', fontSize: 10, fontFamily: 'monospace' },
        grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        crosshair: { mode: 0 },
        rightPriceScale: { borderColor: '#1e293b', scaleMargins: { top: 0.1, bottom: 0.1 } },
        timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false, visible: false },
        width: rsiChartRef.current.clientWidth,
        height: 120,
      })
      const rsiLine = rsiChart.addLineSeries({ color: '#a78bfa', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true, title: 'RSI 14' })
      const ob = rsiChart.addLineSeries({ color: '#ef444450', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false })
      const os = rsiChart.addLineSeries({ color: '#22c55e50', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false })
      const mid = rsiChart.addLineSeries({ color: '#475569', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false })

      rsiChartInstance.current = rsiChart
      rsiSeriesRef.current = rsiLine
      rsiOverboughtRef.current = { ob, os, mid }

      // Sync time scale
      if (chartInstance.current) {
        chartInstance.current.timeScale().subscribeVisibleLogicalRangeChange(range => {
          if (range && rsiChartInstance.current) rsiChartInstance.current.timeScale().setVisibleLogicalRange(range)
        })
      }
      if (lastDataRef.current.length > 0) applySubCharts(lastDataRef.current)
    }
    if (!showRSI && rsiChartInstance.current) {
      rsiChartInstance.current.remove()
      rsiChartInstance.current = null
      rsiSeriesRef.current = null
      rsiOverboughtRef.current = null
    }
  }, [showRSI])

  // Create/destroy MACD sub-chart
  useEffect(() => {
    if (showMACD && macdChartRef.current && !macdChartInstance.current) {
      const mc = createChart(macdChartRef.current, {
        layout: { background: { color: '#0f172a' }, textColor: '#94a3b8', fontSize: 10, fontFamily: 'monospace' },
        grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        crosshair: { mode: 0 },
        rightPriceScale: { borderColor: '#1e293b' },
        timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false, visible: false },
        width: macdChartRef.current.clientWidth,
        height: 120,
      })
      macdLineRef.current = mc.addLineSeries({ color: '#3b82f6', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true, title: 'MACD' })
      macdSignalRef.current = mc.addLineSeries({ color: '#f97316', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'Signal' })
      macdHistRef.current = mc.addHistogramSeries({ priceFormat: { type: 'price' }, priceScaleId: '' })

      macdChartInstance.current = mc

      if (chartInstance.current) {
        chartInstance.current.timeScale().subscribeVisibleLogicalRangeChange(range => {
          if (range && macdChartInstance.current) macdChartInstance.current.timeScale().setVisibleLogicalRange(range)
        })
      }
      if (lastDataRef.current.length > 0) applySubCharts(lastDataRef.current)
    }
    if (!showMACD && macdChartInstance.current) {
      macdChartInstance.current.remove()
      macdChartInstance.current = null
      macdLineRef.current = null
      macdSignalRef.current = null
      macdHistRef.current = null
    }
  }, [showMACD])

  // Apply data to RSI & MACD sub-charts
  const applySubCharts = useCallback((data) => {
    const result = computeChartSignals(data, interval)

    // RSI
    if (rsiSeriesRef.current && rsiChartInstance.current) {
      const rsiVals = result.rsiValues || []
      const rsiData = []
      for (let i = 0; i < data.length; i++) {
        if (rsiVals[i] !== null && rsiVals[i] !== undefined) {
          rsiData.push({ time: data[i].time, value: rsiVals[i] })
        }
      }
      rsiSeriesRef.current.setData(rsiData)
      if (rsiData.length > 1 && rsiOverboughtRef.current) {
        const t0 = rsiData[0].time, t1 = rsiData[rsiData.length - 1].time
        rsiOverboughtRef.current.ob.setData([{ time: t0, value: 70 }, { time: t1, value: 70 }])
        rsiOverboughtRef.current.os.setData([{ time: t0, value: 30 }, { time: t1, value: 30 }])
        rsiOverboughtRef.current.mid.setData([{ time: t0, value: 50 }, { time: t1, value: 50 }])
      }
    }

    // MACD
    if (macdLineRef.current && macdChartInstance.current) {
      const macdData = result.macdChartData || []
      macdLineRef.current.setData(macdData.map(d => ({ time: d.time, value: d.macd })))
      macdSignalRef.current.setData(macdData.map(d => ({ time: d.time, value: d.signal })))
      macdHistRef.current.setData(macdData.map(d => ({
        time: d.time,
        value: d.histogram,
        color: d.histogram >= 0 ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)',
      })))
    }
  }, [interval])

  const applySignals = useCallback((data) => {
    if (!candleSeriesRef.current || !chartInstance.current) return

    try {
      const { markers, levels, trendLine, pivots, ema20Line, ema50Line } = computeChartSignals(data, interval)

      // Signals (markers + trend line)
      if (showSignals) {
        candleSeriesRef.current.setMarkers(markers)
        if (stLineSeriesRef.current && trendLine.length > 0) {
          stLineSeriesRef.current.setData(trendLine.map(p => ({ time: p.time, value: p.value, color: p.color })))
          stLineSeriesRef.current.applyOptions({ visible: true })
        }
      } else {
        candleSeriesRef.current.setMarkers([])
        if (stLineSeriesRef.current) stLineSeriesRef.current.applyOptions({ visible: false })
      }

      // EMA overlay lines
      if (ema20SeriesRef.current) {
        ema20SeriesRef.current.setData(ema20Line || [])
        ema20SeriesRef.current.applyOptions({ visible: showEMA })
      }
      if (ema50SeriesRef.current) {
        ema50SeriesRef.current.setData(ema50Line || [])
        ema50SeriesRef.current.applyOptions({ visible: showEMA })
      }

      // Remove old S/R lines
      for (const line of srLinesRef.current) {
        try { candleSeriesRef.current.removePriceLine(line) } catch {}
      }
      srLinesRef.current = []

      // Draw S/R levels
      if (showSignals) {
        for (const level of levels.slice(0, 4)) {
          const priceLine = candleSeriesRef.current.createPriceLine({
            price: level.price,
            color: level.type === 'support' ? '#22c55e80' : '#ef444480',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: true,
            title: `${level.type === 'support' ? 'S' : 'R'} ${level.price.toFixed(0)}`,
          })
          srLinesRef.current.push(priceLine)
        }
      }

      // Remove old Pivot lines
      for (const line of pivotLinesRef.current) {
        try { candleSeriesRef.current.removePriceLine(line) } catch {}
      }
      pivotLinesRef.current = []

      if (showPivots && pivots && pivots.length > 0) {
        for (const p of pivots) {
          const priceLine = candleSeriesRef.current.createPriceLine({
            price: p.price,
            color: p.color,
            lineWidth: 1,
            lineStyle: p.label === 'PP' ? 0 : 2,
            axisLabelVisible: true,
            title: p.label,
          })
          pivotLinesRef.current.push(priceLine)
        }
      }

      // Volume visibility
      if (volumeSeriesRef.current) {
        volumeSeriesRef.current.applyOptions({ visible: showVolume })
      }

      // Sub-charts
      applySubCharts(data)

      // Signal stats
      if (showSignals) {
        const buyCount = markers.filter(m => m.text.includes('Buy')).length
        const sellCount = markers.filter(m => m.text.includes('Sell')).length
        const strongCount = markers.filter(m => m.text.includes('STRONG')).length
        setSignalStats({
          total: markers.length,
          buys: buyCount,
          sells: sellCount,
          strong: strongCount,
          levels: Math.min(levels.length, 4),
          lastSignal: markers.length > 0 ? markers[markers.length - 1] : null,
        })
      } else {
        setSignalStats(null)
      }
    } catch (e) {
      console.warn('Signal computation error:', e)
    }
  }, [showSignals, showPivots, showVolume, showEMA, interval, applySubCharts])

  const fetchChart = useCallback(async (fullLoad = false) => {
    if (fullLoad) setLoading(true)
    try {
      let data
      try {
        const res = await fetch(`/api/chart/${ticker}?interval=${interval}`)
        if (res.ok) data = await res.json()
      } catch {}

      if (!data || data.length === 0) {
        data = await fetchOHLCV(ticker, interval)
      }

      if (!candleSeriesRef.current || data.length === 0) return

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
            color: d.close >= d.open ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)',
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
            candleSeriesRef.current.update({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })
            volumeSeriesRef.current.update({
              time: d.time, value: d.volume,
              color: d.close >= d.open ? 'rgba(34,197,94,0.5)' : 'rgba(239,68,68,0.5)',
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
    const refreshMs = interval === '1m' ? 5000 : 10000
    const iv = window.setInterval(() => fetchChart(false), refreshMs)
    return () => window.clearInterval(iv)
  }, [ticker, interval, fetchChart])

  // Re-apply overlays when toggles change
  useEffect(() => {
    if (lastDataRef.current.length > 0) applySignals(lastDataRef.current)
  }, [showSignals, showPivots, showVolume, showEMA, applySignals])

  const changeColor = priceChange >= 0 ? 'text-terminal-green' : 'text-terminal-red'
  const changeSign = priceChange >= 0 ? '+' : ''

  // Toggle button helper
  const ToggleBtn = ({ active, onClick, title, label, activeClass }) => (
    <button
      onClick={onClick}
      className={`px-2 py-0.5 text-[11px] font-mono rounded transition-all duration-150 ${
        active ? activeClass : 'text-terminal-dim hover:text-terminal-text hover:bg-white/5 border border-transparent'
      }`}
      title={title}
    >
      {label}
    </button>
  )

  return (
    <div ref={containerRef} className={`bg-[#0f172a] border border-[#1e293b] rounded-lg overflow-hidden ${isFullscreen ? 'flex flex-col' : ''}`}>
      {/* ── Top toolbar ── */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#1e293b] shrink-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold text-white">{ticker}</span>
          {lastPrice && (
            <>
              <span className="font-mono text-sm text-white">{lastPrice.toFixed(2)}</span>
              <span className={`font-mono text-xs px-1.5 py-0.5 rounded ${
                priceChange >= 0 ? 'bg-terminal-green/10 text-terminal-green' : 'bg-terminal-red/10 text-terminal-red'
              }`}>
                {changeSign}{priceChange.toFixed(2)}%
              </span>
            </>
          )}
          <span className="relative flex h-2 w-2 ml-1">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-terminal-green opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-terminal-green"></span>
          </span>
          <span className="text-[10px] font-mono text-terminal-dim">LIVE</span>
          <span className="text-[10px] font-mono text-terminal-blue">IST</span>
          {loading && <span className="text-[10px] font-mono text-terminal-amber animate-pulse ml-1">Loading...</span>}
        </div>

        <div className="flex items-center gap-1">
          {/* Interval buttons */}
          {INTERVALS.map(i => (
            <button
              key={i.value}
              onClick={() => setInterval_(i.value)}
              className={`px-2.5 py-0.5 text-[11px] font-mono rounded transition-all ${
                interval === i.value
                  ? 'bg-terminal-blue text-white font-medium'
                  : 'text-terminal-dim hover:text-white hover:bg-white/5'
              }`}
            >
              {i.label}
            </button>
          ))}

          <span className="w-px h-4 bg-[#334155] mx-1" />

          {/* Indicator toggles */}
          <ToggleBtn active={showSignals} onClick={() => setShowSignals(!showSignals)}
            label={showSignals ? '● Signals' : '○ Signals'}
            activeClass="bg-terminal-green/15 text-terminal-green border border-terminal-green/30"
            title="Buy/Sell signals + SuperTrend + S/R levels" />
          <ToggleBtn active={showEMA} onClick={() => setShowEMA(!showEMA)}
            label="EMA"
            activeClass="bg-amber-500/15 text-amber-400 border border-amber-500/30"
            title="EMA 20 (amber) & EMA 50 (purple) moving averages" />
          <ToggleBtn active={showRSI} onClick={() => setShowRSI(!showRSI)}
            label="RSI"
            activeClass="bg-purple-500/15 text-purple-400 border border-purple-500/30"
            title="RSI (14) — Overbought >70, Oversold <30" />
          <ToggleBtn active={showMACD} onClick={() => setShowMACD(!showMACD)}
            label="MACD"
            activeClass="bg-blue-500/15 text-blue-400 border border-blue-500/30"
            title="MACD (12,26,9) histogram" />
          <ToggleBtn active={showPivots} onClick={() => setShowPivots(!showPivots)}
            label="Pivot"
            activeClass="bg-purple-500/15 text-purple-400 border border-purple-500/30"
            title="Daily Pivot Points: PP, R1, R2, S1, S2" />
          <ToggleBtn active={showVolume} onClick={() => setShowVolume(!showVolume)}
            label="Vol"
            activeClass="bg-blue-500/15 text-blue-400 border border-blue-500/30"
            title="Volume bars" />

          <span className="w-px h-4 bg-[#334155] mx-1" />

          <button
            onClick={toggleFullscreen}
            className="px-2 py-0.5 text-[11px] font-mono rounded text-terminal-dim hover:text-white hover:bg-white/5 transition-all"
            title={isFullscreen ? 'Exit fullscreen (Esc)' : 'Fullscreen'}
          >
            {isFullscreen ? '✕' : '⛶'}
          </button>
        </div>
      </div>

      {/* ── Signal stats bar ── */}
      {showSignals && signalStats && (
        <div className="px-3 py-1 border-b border-[#1e293b]/70 flex items-center gap-3 text-[10px] font-mono shrink-0 bg-[#0f172a]">
          <span className="text-terminal-green font-medium">{signalStats.buys} Buy</span>
          <span className="text-terminal-red font-medium">{signalStats.sells} Sell</span>
          {signalStats.strong > 0 && <span className="text-amber-400 font-medium">{signalStats.strong} Strong</span>}
          <span className="text-[#475569]">|</span>
          <span className="text-[#64748b]">S/R: {signalStats.levels}</span>
          {signalStats.lastSignal && (
            <>
              <span className="text-[#475569]">|</span>
              <span className={signalStats.lastSignal.text.includes('Buy') ? 'text-terminal-green' : 'text-terminal-red'}>
                Latest: {signalStats.lastSignal.text}
              </span>
            </>
          )}
          <span className="text-[#475569] ml-auto">Trend-based signals, not predictions</span>
        </div>
      )}

      {error && (
        <div className="px-3 py-1.5 text-[11px] font-mono text-terminal-red shrink-0 bg-terminal-red/5">
          Chart error: {error}
        </div>
      )}

      {/* ── Crosshair OHLCV data bar (TradingView style) ── */}
      <div className="px-3 py-0.5 flex items-center gap-2 text-[10px] font-mono shrink-0 bg-[#0f172a] min-h-[20px]">
        {crosshairData ? (
          <>
            <span className="text-[#64748b]">O</span>
            <span className={crosshairData.isUp ? 'text-terminal-green' : 'text-terminal-red'}>{crosshairData.open?.toFixed(2)}</span>
            <span className="text-[#64748b]">H</span>
            <span className={crosshairData.isUp ? 'text-terminal-green' : 'text-terminal-red'}>{crosshairData.high?.toFixed(2)}</span>
            <span className="text-[#64748b]">L</span>
            <span className={crosshairData.isUp ? 'text-terminal-green' : 'text-terminal-red'}>{crosshairData.low?.toFixed(2)}</span>
            <span className="text-[#64748b]">C</span>
            <span className={crosshairData.isUp ? 'text-terminal-green' : 'text-terminal-red'}>{crosshairData.close?.toFixed(2)}</span>
            {crosshairData.volume != null && (
              <><span className="text-[#64748b] ml-1">Vol</span><span className="text-[#94a3b8]">{Number(crosshairData.volume).toLocaleString('en-IN')}</span></>
            )}
            {crosshairData.supertrend != null && showSignals && (
              <><span className="text-[#475569] ml-1">|</span><span className="text-[#64748b]">ST</span><span className="text-[#94a3b8]">{crosshairData.supertrend.toFixed(2)}</span></>
            )}
            {crosshairData.ema20 != null && showEMA && (
              <><span className="text-[#475569]">|</span><span className="text-amber-400">E20</span><span className="text-[#94a3b8]">{crosshairData.ema20.toFixed(2)}</span></>
            )}
            {crosshairData.ema50 != null && showEMA && (
              <><span className="text-purple-400">E50</span><span className="text-[#94a3b8]">{crosshairData.ema50.toFixed(2)}</span></>
            )}
          </>
        ) : (
          <span className="text-[#475569]">Hover over chart for details</span>
        )}
      </div>

      {/* ── Main chart ── */}
      <div ref={chartRef} className={isFullscreen ? 'flex-1' : ''} />

      {/* ── RSI sub-chart ── */}
      {showRSI && (
        <div className="border-t border-[#1e293b]">
          <div className="px-3 py-0.5 flex items-center gap-2 text-[10px] font-mono bg-[#0f172a]">
            <span className="text-purple-400 font-medium">RSI (14)</span>
            <span className="text-[#475569]">|</span>
            <span className="text-terminal-red/50">70</span>
            <span className="text-[#475569]">50</span>
            <span className="text-terminal-green/50">30</span>
          </div>
          <div ref={rsiChartRef} />
        </div>
      )}

      {/* ── MACD sub-chart ── */}
      {showMACD && (
        <div className="border-t border-[#1e293b]">
          <div className="px-3 py-0.5 flex items-center gap-2 text-[10px] font-mono bg-[#0f172a]">
            <span className="text-blue-400 font-medium">MACD</span>
            <span className="text-[#475569]">(12, 26, 9)</span>
            <span className="text-[#475569]">|</span>
            <span className="text-blue-400">MACD</span>
            <span className="text-orange-400">Signal</span>
            <span className="text-terminal-green/60">Histogram</span>
          </div>
          <div ref={macdChartRef} />
        </div>
      )}

      {/* ── Legend footer ── */}
      {(showSignals || showPivots || showEMA) && (
        <div className="px-3 py-1.5 border-t border-[#1e293b] shrink-0 bg-[#0f172a]">
          <div className="flex items-center gap-3 text-[10px] font-mono text-[#64748b] flex-wrap">
            {showSignals && (
              <>
                <span><span className="inline-block w-2 h-2 rounded-full bg-terminal-green mr-1 align-middle" />SuperTrend Up</span>
                <span><span className="inline-block w-2 h-2 rounded-full bg-terminal-red mr-1 align-middle" />SuperTrend Down</span>
                <span><span className="text-terminal-green mr-0.5">▲</span>Buy</span>
                <span><span className="text-terminal-red mr-0.5">▼</span>Sell</span>
                <span>S = Support</span>
                <span>R = Resistance</span>
              </>
            )}
            {showEMA && (
              <>
                <span><span className="inline-block w-3 h-0.5 bg-amber-400 mr-1 align-middle" />EMA 20</span>
                <span><span className="inline-block w-3 h-0.5 bg-purple-500 mr-1 align-middle" />EMA 50</span>
              </>
            )}
            {showPivots && <span className="text-purple-400">PP R1 R2 S1 S2</span>}
          </div>
        </div>
      )}
    </div>
  )
}
