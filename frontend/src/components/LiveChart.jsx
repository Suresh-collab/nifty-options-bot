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
  const containerRef = useRef(null)
  const chartInstance = useRef(null)
  const rsiChartInstance = useRef(null)
  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  const stLineSeriesRef = useRef(null)
  const rsiSeriesRef = useRef(null)
  const rsiOverboughtRef = useRef(null)
  const rsiOversoldRef = useRef(null)
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
  const [showVolume, setShowVolume] = useState(true)
  const [showPivots, setShowPivots] = useState(false)
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
        const mainH = fs ? window.innerHeight - (showRSI ? 250 : 100) : 420
        chartInstance.current.applyOptions({
          width: chartRef.current.clientWidth,
          height: mainH,
        })
        chartInstance.current.timeScale().fitContent()
      }
      if (rsiChartInstance.current && rsiChartRef.current) {
        rsiChartInstance.current.applyOptions({
          width: rsiChartRef.current.clientWidth,
          height: fs ? 140 : 100,
        })
      }
    }
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [showRSI])

  // Create main chart ONCE
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
      rightPriceScale: { borderColor: '#334155' },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartRef.current.clientWidth,
      height: 420,
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
      scaleMargins: { top: 0.75, bottom: 0 },
    })

    const stLineSeries = chart.addLineSeries({
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      title: 'SuperTrend',
    })

    chartInstance.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    stLineSeriesRef.current = stLineSeries

    // Crosshair hover — show OHLCV + indicator values
    chart.subscribeCrosshairMove(param => {
      if (!param.time || !param.seriesData) {
        setCrosshairData(null)
        return
      }
      const candle = param.seriesData.get(candleSeries)
      const vol = param.seriesData.get(volumeSeries)
      const st = param.seriesData.get(stLineSeries)
      if (candle) {
        setCrosshairData({
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close,
          volume: vol?.value,
          supertrend: st?.value,
          isUp: candle.close >= candle.open,
        })
      }
    })

    const handleResize = () => {
      if (chartRef.current && chartInstance.current) {
        chartInstance.current.applyOptions({
          width: chartRef.current.clientWidth,
          height: document.fullscreenElement ? window.innerHeight - 250 : 420,
        })
      }
      if (rsiChartRef.current && rsiChartInstance.current) {
        rsiChartInstance.current.applyOptions({
          width: rsiChartRef.current.clientWidth,
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
      pivotLinesRef.current = []
    }
  }, [])

  // Create/destroy RSI sub-chart based on toggle
  useEffect(() => {
    if (showRSI && rsiChartRef.current && !rsiChartInstance.current) {
      const rsiChart = createChart(rsiChartRef.current, {
        layout: {
          background: { color: '#1e293b' },
          textColor: '#94a3b8',
          fontSize: 10,
          fontFamily: 'monospace',
        },
        grid: {
          vertLines: { color: '#334155' },
          horzLines: { color: '#334155' },
        },
        crosshair: { mode: 0 },
        rightPriceScale: {
          borderColor: '#334155',
          scaleMargins: { top: 0.05, bottom: 0.05 },
        },
        timeScale: {
          borderColor: '#334155',
          timeVisible: true,
          secondsVisible: false,
          visible: false,
        },
        width: rsiChartRef.current.clientWidth,
        height: 100,
      })

      const rsiLine = rsiChart.addLineSeries({
        color: '#a78bfa',
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: false,
        title: 'RSI',
      })

      // Overbought/oversold reference lines
      const ob = rsiChart.addLineSeries({
        color: '#ef444460',
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      const os = rsiChart.addLineSeries({
        color: '#22c55e60',
        lineWidth: 1,
        lineStyle: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })

      rsiChartInstance.current = rsiChart
      rsiSeriesRef.current = rsiLine
      rsiOverboughtRef.current = ob
      rsiOversoldRef.current = os

      // Sync crosshair between main and RSI charts
      if (chartInstance.current) {
        chartInstance.current.timeScale().subscribeVisibleLogicalRangeChange(range => {
          if (range && rsiChartInstance.current) {
            rsiChartInstance.current.timeScale().setVisibleLogicalRange(range)
          }
        })
      }

      // If we already have data, populate the RSI chart
      if (lastDataRef.current.length > 0) {
        applyRSIData(lastDataRef.current)
      }
    }

    if (!showRSI && rsiChartInstance.current) {
      rsiChartInstance.current.remove()
      rsiChartInstance.current = null
      rsiSeriesRef.current = null
      rsiOverboughtRef.current = null
      rsiOversoldRef.current = null
    }
  }, [showRSI])

  // Apply RSI data to sub-chart
  const applyRSIData = useCallback((data) => {
    if (!rsiSeriesRef.current || !rsiChartInstance.current) return
    const result = computeChartSignals(data, interval)
    const rsiVals = result.rsiValues
    if (!rsiVals) return

    const rsiData = []
    for (let i = 0; i < data.length; i++) {
      if (rsiVals[i] !== null && rsiVals[i] !== undefined) {
        rsiData.push({ time: data[i].time, value: rsiVals[i] })
      }
    }
    rsiSeriesRef.current.setData(rsiData)

    // Draw overbought (70) and oversold (30) lines
    if (rsiData.length > 1 && rsiOverboughtRef.current) {
      const refData = [
        { time: rsiData[0].time, value: 70 },
        { time: rsiData[rsiData.length - 1].time, value: 70 },
      ]
      rsiOverboughtRef.current.setData(refData)
      rsiOversoldRef.current.setData([
        { time: rsiData[0].time, value: 30 },
        { time: rsiData[rsiData.length - 1].time, value: 30 },
      ])
    }
  }, [interval])

  const applySignals = useCallback((data) => {
    if (!candleSeriesRef.current || !chartInstance.current) return

    try {
      const { markers, levels, trendLine, pivots } = computeChartSignals(data, interval)

      // Signals (markers + trend line)
      if (showSignals) {
        candleSeriesRef.current.setMarkers(markers)
        if (stLineSeriesRef.current && trendLine.length > 0) {
          stLineSeriesRef.current.setData(
            trendLine.map(p => ({ time: p.time, value: p.value, color: p.color }))
          )
        }
      } else {
        candleSeriesRef.current.setMarkers([])
        stLineSeriesRef.current?.setData([])
      }

      // Remove old S/R lines
      for (const line of srLinesRef.current) {
        try { candleSeriesRef.current.removePriceLine(line) } catch {}
      }
      srLinesRef.current = []

      // Draw S/R levels if signals are on — more visible now
      if (showSignals) {
        const limitedLevels = levels.slice(0, 4)
        for (const level of limitedLevels) {
          const priceLine = candleSeriesRef.current.createPriceLine({
            price: level.price,
            color: level.type === 'support' ? '#22c55e90' : '#ef444490',
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

      // Draw Pivot levels if enabled
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
        volumeSeriesRef.current.applyOptions({
          visible: showVolume,
        })
      }

      // RSI sub-chart data
      if (showRSI) {
        applyRSIData(data)
      }

      // Signal stats
      if (showSignals) {
        const buyCount = markers.filter(m => m.text.includes('BUY')).length
        const sellCount = markers.filter(m => m.text.includes('SELL')).length
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
  }, [showSignals, showPivots, showVolume, showRSI, interval, applyRSIData])

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
            candleSeriesRef.current.update({
              time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
            })
            volumeSeriesRef.current.update({
              time: d.time,
              value: d.volume,
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

    // 1m refreshes faster (5s), others at 10s
    const refreshMs = interval === '1m' ? 5000 : 10000
    const iv = window.setInterval(() => fetchChart(false), refreshMs)
    return () => window.clearInterval(iv)
  }, [ticker, interval, fetchChart])

  // Re-apply overlays when any toggle changes
  useEffect(() => {
    if (lastDataRef.current.length > 0) {
      applySignals(lastDataRef.current)
    }
  }, [showSignals, showPivots, showVolume, showRSI, applySignals])

  const changeColor = priceChange >= 0 ? 'text-terminal-green' : 'text-terminal-red'
  const changeSign = priceChange >= 0 ? '+' : ''

  return (
    <div ref={containerRef} className={`bg-terminal-surface border border-terminal-border rounded-lg overflow-hidden ${isFullscreen ? '!bg-terminal-bg flex flex-col' : ''}`}>
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-terminal-border shrink-0">
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
        <div className="flex items-center gap-1.5">
          {/* Indicator toggles */}
          <button
            onClick={() => setShowSignals(!showSignals)}
            className={`px-2 py-0.5 text-xs font-mono rounded transition-colors ${
              showSignals
                ? 'bg-terminal-green/20 text-terminal-green border border-terminal-green/30'
                : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-border border border-transparent'
            }`}
            title="Buy/Sell signals, SuperTrend, S/R levels"
          >
            Signals {showSignals ? 'ON' : 'OFF'}
          </button>
          <button
            onClick={() => setShowRSI(!showRSI)}
            className={`px-2 py-0.5 text-xs font-mono rounded transition-colors ${
              showRSI
                ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-border border border-transparent'
            }`}
            title="RSI (14) sub-chart: Overbought >70, Oversold <30"
          >
            RSI
          </button>
          <button
            onClick={() => setShowPivots(!showPivots)}
            className={`px-2 py-0.5 text-xs font-mono rounded transition-colors ${
              showPivots
                ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30'
                : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-border border border-transparent'
            }`}
            title="Daily Pivot Points: PP, R1, R2, S1, S2"
          >
            Pivots
          </button>
          <button
            onClick={() => setShowVolume(!showVolume)}
            className={`px-2 py-0.5 text-xs font-mono rounded transition-colors ${
              showVolume
                ? 'bg-terminal-blue/20 text-terminal-blue border border-terminal-blue/30'
                : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-border border border-transparent'
            }`}
            title="Volume bars at the bottom of chart"
          >
            Vol
          </button>
          <span className="w-px h-4 bg-terminal-border mx-0.5" />
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
          <button
            onClick={toggleFullscreen}
            className="px-2 py-0.5 text-xs font-mono rounded text-terminal-dim hover:text-terminal-text hover:bg-terminal-border transition-colors border border-transparent"
            title={isFullscreen ? 'Exit fullscreen (Esc)' : 'View chart in fullscreen'}
          >
            {isFullscreen ? '✕ Exit' : '⛶ Fullscreen'}
          </button>
        </div>
      </div>

      {/* Signal stats bar */}
      {showSignals && signalStats && (
        <div className="px-4 py-1.5 border-b border-terminal-border/50 flex items-center gap-4 text-[10px] font-mono shrink-0">
          <span className="text-terminal-dim">TREND SIGNALS:</span>
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
          <span className="text-terminal-dim ml-auto">Based on past trends, not predictions</span>
        </div>
      )}

      {error && (
        <div className="px-4 py-2 text-xs font-mono text-terminal-red shrink-0">
          Chart error: {error}
        </div>
      )}

      {/* Crosshair OHLCV info bar */}
      {crosshairData && (
        <div className="px-4 py-1 flex items-center gap-3 text-[10px] font-mono shrink-0 bg-terminal-bg/40">
          <span className="text-terminal-dim">O</span>
          <span className={crosshairData.isUp ? 'text-terminal-green' : 'text-terminal-red'}>{crosshairData.open?.toFixed(2)}</span>
          <span className="text-terminal-dim">H</span>
          <span className={crosshairData.isUp ? 'text-terminal-green' : 'text-terminal-red'}>{crosshairData.high?.toFixed(2)}</span>
          <span className="text-terminal-dim">L</span>
          <span className={crosshairData.isUp ? 'text-terminal-green' : 'text-terminal-red'}>{crosshairData.low?.toFixed(2)}</span>
          <span className="text-terminal-dim">C</span>
          <span className={crosshairData.isUp ? 'text-terminal-green' : 'text-terminal-red'}>{crosshairData.close?.toFixed(2)}</span>
          {crosshairData.volume != null && (
            <>
              <span className="text-terminal-dim">Vol</span>
              <span className="text-terminal-blue">{Number(crosshairData.volume).toLocaleString('en-IN')}</span>
            </>
          )}
          {crosshairData.supertrend != null && (
            <>
              <span className="text-terminal-dim">|</span>
              <span className="text-purple-400">SuperTrend</span>
              <span className="text-terminal-text">{crosshairData.supertrend.toFixed(2)}</span>
            </>
          )}
        </div>
      )}

      {/* Main chart */}
      <div ref={chartRef} className={isFullscreen ? 'flex-1' : ''} />

      {/* RSI sub-chart */}
      {showRSI && (
        <div className="border-t border-terminal-border/50">
          <div className="px-4 py-0.5 flex items-center gap-3 text-[10px] font-mono text-terminal-dim bg-terminal-bg/30">
            <span className="text-purple-400">RSI (14)</span>
            <span className="text-terminal-red/60">70 Overbought</span>
            <span className="text-terminal-green/60">30 Oversold</span>
          </div>
          <div ref={rsiChartRef} />
        </div>
      )}

      {/* Legend */}
      {(showSignals || showPivots) && (
        <div className="px-4 py-2 border-t border-terminal-border/50 space-y-1 shrink-0">
          <div className="flex items-center gap-4 text-[10px] font-mono text-terminal-dim flex-wrap">
            {showSignals && (
              <>
                <span><span className="inline-block w-3 h-0.5 bg-terminal-green mr-1 align-middle" />Uptrend</span>
                <span><span className="inline-block w-3 h-0.5 bg-terminal-red mr-1 align-middle" />Downtrend</span>
                <span><span className="text-terminal-green mr-1">▲</span>Buy zone</span>
                <span><span className="text-terminal-red mr-1">▼</span>Sell zone</span>
                <span><span className="inline-block w-3 h-0.5 bg-terminal-green/70 mr-1 align-middle" />Support</span>
                <span><span className="inline-block w-3 h-0.5 bg-terminal-red/70 mr-1 align-middle" />Resistance</span>
              </>
            )}
            {showPivots && (
              <>
                <span className="text-purple-400">PP</span>
                <span className="text-terminal-red">R1 R2</span>
                <span className="text-terminal-green">S1 S2</span>
              </>
            )}
          </div>
          <div className="text-[10px] font-mono text-terminal-dim/60 leading-relaxed">
            These are <b>trend-following</b> signals based on past price action — they show where the trend has been, not where it will go.
            Use them alongside news, market mood, and your own judgment. Never rely on any single indicator.
          </div>
        </div>
      )}
    </div>
  )
}
