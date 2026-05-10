import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart } from 'lightweight-charts'
import { useStore } from '../store'
import { fetchOHLCV } from '../lib/yahooFetch'
import { computeChartSignals } from '../lib/chartIndicators'

const INTERVALS = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1D', value: '1d' },
]

// ── Chart settings persistence (single-chart mode only) ───────────────────
const _CS_KEY = 'nob_chartSettings'
function _csGet(key, fallback) {
  try { return JSON.parse(localStorage.getItem(_CS_KEY) || '{}')[key] ?? fallback } catch { return fallback }
}
function _csSave(key, value) {
  try {
    const s = JSON.parse(localStorage.getItem(_CS_KEY) || '{}')
    localStorage.setItem(_CS_KEY, JSON.stringify({ ...s, [key]: value }))
  } catch {}
}

// Module-level generation counter shared across all compact chart instances on the page.
// Increments each time any compact chart broadcasts a time range change, letting
// the originating chart skip its own echo via lastSentGenerationRef.
let _syncGeneration = 0

// IST offset: +5:30 = 19800 seconds
const IST_OFFSET = 19800

function toIST(data) {
  return data.map(d => ({ ...d, time: d.time + IST_OFFSET }))
}

/**
 * Generate synthetic volume from candle activity when real volume is unavailable.
 * Uses (high - low) range as a proxy for trading activity — common technique for indices.
 */
function synthesizeVolume(data) {
  const hasRealVolume = data.some(d => (d.volume || 0) > 100)
  if (hasRealVolume) return data

  // Use candle range × body ratio as synthetic volume
  const ranges = data.map(d => (d.high - d.low) || 0)
  const avgRange = ranges.reduce((a, b) => a + b, 0) / (ranges.length || 1) || 1

  return data.map(d => {
    const range = (d.high - d.low) || 0
    const bodyRatio = Math.abs(d.close - d.open) / (range || 1)
    // Scale: range relative to average, boosted by body ratio (fuller candles = more volume)
    const syntheticVol = Math.round((range / avgRange) * (0.5 + bodyRatio) * 1000000)
    return { ...d, volume: syntheticVol, _synthetic: true }
  })
}

/** Compute Heikin Ashi candles from raw OHLCV — smoother trend visualization */
function computeHA(data) {
  const ha = []
  for (let i = 0; i < data.length; i++) {
    const haClose = (data[i].open + data[i].high + data[i].low + data[i].close) / 4
    const haOpen = i === 0
      ? (data[i].open + data[i].close) / 2
      : (ha[i - 1].open + ha[i - 1].close) / 2
    const haHigh = Math.max(data[i].high, haOpen, haClose)
    const haLow = Math.min(data[i].low, haOpen, haClose)
    ha.push({ ...data[i], open: haOpen, high: haHigh, low: haLow, close: haClose })
  }
  return ha
}

/** Cap volume at 95th percentile to prevent outlier compression */
function getVolumeCap(data) {
  const volumes = data.map(d => d.volume || 0).filter(v => v > 0)
  if (volumes.length === 0) return 1
  const sorted = [...volumes].sort((a, b) => a - b)
  return sorted[Math.floor(sorted.length * 0.95)] || sorted[sorted.length - 1] || 1
}

export default function LiveChart({ defaultInterval = '5m', compact = false, defaultCandleType = 'candle', defaultShowSignals = true, defaultShowVolume = true }) {
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
  const tradeLinesRef = useRef([])  // v4: active trade SL/target/entry lines
  const lastDataRef = useRef([])
  const volCapRef = useRef(1)
  const syncingCrosshairRef = useRef(false)
  const syncingTimeRef = useRef(false)
  // Grid crosshair sync ref: prevents the originating chart from echoing its own broadcast
  const lastSentGenerationRef = useRef(-1)

  // Read main chart's actual rendered price scale width and force sub-charts to match.
  // Called via setTimeout so lightweight-charts has finished its layout pass first.
  const syncPriceScaleWidths = useCallback(() => {
    if (!chartInstance.current) return
    const w = chartInstance.current.priceScale('right').width()
    // w can be 0 if the chart hasn't painted yet — retry after another frame
    if (!w || w < 40) { setTimeout(syncPriceScaleWidths, 100); return }
    rsiChartInstance.current?.applyOptions({ rightPriceScale: { minimumWidth: w } })
    macdChartInstance.current?.applyOptions({ rightPriceScale: { minimumWidth: w } })
  }, [])
  const rsiDataRef = useRef([])
  const macdDataRef = useRef({ macd: [], signal: [] })
  const isFirstLoad = useRef(true)
  const { ticker, chartCrosshairTime, setChartCrosshairTime } = useStore()
  const [interval, setInterval_] = useState(() =>
    compact ? defaultInterval : _csGet('interval', defaultInterval)
  )
  const [candleType, setCandleType] = useState(() =>
    compact ? defaultCandleType : _csGet('candleType', defaultCandleType)
  )
  const candleTypeRef = useRef(compact ? defaultCandleType : _csGet('candleType', defaultCandleType))

  useEffect(() => {
    // Grid mode only: enforce the hardcoded interval from props
    if (!compact) return
    setInterval_(defaultInterval)
    isFirstLoad.current = true
  }, [defaultInterval])

  useEffect(() => {
    // Grid mode only: enforce the hardcoded candle type from props
    if (!compact) return
    setCandleType(defaultCandleType)
    candleTypeRef.current = defaultCandleType
  }, [defaultCandleType])

  // Keep ref in sync so fetchChart closure always has current value without re-subscribing
  useEffect(() => { candleTypeRef.current = candleType }, [candleType])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [lastPrice, setLastPrice] = useState(null)
  const [priceChange, setPriceChange] = useState(0)
  const [showSignals, setShowSignals] = useState(() =>
    compact ? defaultShowSignals : _csGet('showSignals', defaultShowSignals)
  )
  const [showRSI, setShowRSI] = useState(() =>
    compact ? false : _csGet('showRSI', false)
  )
  const [showMACD, setShowMACD] = useState(() =>
    compact ? false : _csGet('showMACD', false)
  )
  const [showVolume, setShowVolume] = useState(() =>
    compact ? defaultShowVolume : _csGet('showVolume', defaultShowVolume)
  )
  const [showPivots, setShowPivots] = useState(() =>
    compact ? false : _csGet('showPivots', false)
  )
  const [showEMA, setShowEMA] = useState(() =>
    compact ? false : _csGet('showEMA', false)
  )

  // Persist single-chart settings to localStorage whenever they change
  useEffect(() => { if (!compact) _csSave('interval',     interval)    }, [interval,     compact])
  useEffect(() => { if (!compact) _csSave('candleType',   candleType)  }, [candleType,   compact])
  useEffect(() => { if (!compact) _csSave('showSignals',  showSignals) }, [showSignals,  compact])
  useEffect(() => { if (!compact) _csSave('showRSI',      showRSI)     }, [showRSI,      compact])
  useEffect(() => { if (!compact) _csSave('showMACD',     showMACD)    }, [showMACD,     compact])
  useEffect(() => { if (!compact) _csSave('showVolume',   showVolume)  }, [showVolume,   compact])
  useEffect(() => { if (!compact) _csSave('showPivots',   showPivots)  }, [showPivots,   compact])
  useEffect(() => { if (!compact) _csSave('showEMA',      showEMA)     }, [showEMA,      compact])

  // Grid crosshair sync: apply an incoming cursor timestamp from a sibling compact chart.
  // Finds the nearest candle to the broadcast wall-clock time and pins the crosshair there.
  // Skip if this chart originated the broadcast (matched by generation id).
  useEffect(() => {
    if (!compact || !chartInstance.current) return
    if (!chartCrosshairTime) {
      chartInstance.current.clearCrosshairPosition?.()
      setCrosshairData(null)
      return
    }
    if (chartCrosshairTime.gen === lastSentGenerationRef.current) return
    const data = lastDataRef.current
    if (!data.length || !candleSeriesRef.current) return
    // Find nearest candle to the broadcast timestamp (different intervals ≠ exact match)
    let nearest = data[0]
    let minDiff = Math.abs(data[0].time - chartCrosshairTime.time)
    for (let i = 1; i < data.length; i++) {
      const diff = Math.abs(data[i].time - chartCrosshairTime.time)
      if (diff < minDiff) { minDiff = diff; nearest = data[i] }
    }
    syncingCrosshairRef.current = true
    try {
      chartInstance.current.setCrosshairPosition(nearest.close, nearest.time, candleSeriesRef.current)
      setCrosshairData({
        open: nearest.open, high: nearest.high, low: nearest.low, close: nearest.close,
        volume: nearest.volume, isUp: nearest.close >= nearest.open,
      })
    } finally {
      syncingCrosshairRef.current = false
    }
  }, [chartCrosshairTime, compact])

  const [signalStats, setSignalStats] = useState(null)
  const [tradeStats, setTradeStats] = useState(null)  // v4: trade performance stats
  const [activeTradeInfo, setActiveTradeInfo] = useState(null)  // v4: current open trade
  const [haTrend, setHaTrend] = useState(null)  // v5: HA trend status
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

  // Sync fullscreen state and resize charts.
  // Wrapped in rAF so the browser fullscreen layout settles before we read dimensions,
  // and so React's re-render (which adds flex-1 to the chart div) has time to run.
  useEffect(() => {
    const handler = () => {
      const fs = !!document.fullscreenElement
      setIsFullscreen(fs)
      requestAnimationFrame(() => {
        if (chartInstance.current && chartRef.current) {
          const subPanels = (showRSI ? 150 : 0) + (showMACD ? 150 : 0)
          const mainH = fs
            ? window.innerHeight - subPanels - 120
            : (compact ? 280 : Math.max(400, window.innerHeight - 280))
          chartInstance.current.applyOptions({
            width: fs ? window.innerWidth : chartRef.current.clientWidth,
            height: mainH,
          })
          chartInstance.current.timeScale().fitContent()
        }
        if (rsiChartInstance.current && rsiChartRef.current) {
          rsiChartInstance.current.applyOptions({
            width: fs ? window.innerWidth : rsiChartRef.current.clientWidth,
          })
        }
        if (macdChartInstance.current && macdChartRef.current) {
          macdChartInstance.current.applyOptions({
            width: fs ? window.innerWidth : macdChartRef.current.clientWidth,
          })
        }
      })
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
        scaleMargins: { top: 0.05, bottom: 0.22 },
        minimumWidth: 90,
      },
      timeScale: {
        borderColor: '#1e293b',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 5,
        barSpacing: 8,
      },
      width: chartRef.current.clientWidth,
      height: compact ? 280 : Math.max(400, window.innerHeight - 280),
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
      color: '#26a69a',
      base: 0,
    })
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.7, bottom: 0 },
      visible: false,
      drawTicks: false,
    })

    const stLineSeries = chart.addLineSeries({
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: !compact,   // grid: no axis price box, line color is enough
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

    // Crosshair hover — show OHLCV + indicator values; sync position to sub-charts.
    // In grid mode, broadcast the cursor timestamp so sibling charts can sync their vertical line.
    chart.subscribeCrosshairMove(param => {
      if (syncingCrosshairRef.current) return
      if (!param.time || !param.seriesData) {
        setCrosshairData(null)
        rsiChartInstance.current?.clearCrosshairPosition?.()
        macdChartInstance.current?.clearCrosshairPosition?.()
        if (compact) setChartCrosshairTime(null)
        return
      }
      const candle = param.seriesData.get(candleSeries)
      const vol = param.seriesData.get(volumeSeries)
      const st = param.seriesData.get(stLineSeries)
      const e20 = param.seriesData.get(ema20Series)
      const e50 = param.seriesData.get(ema50Series)
      const t = param.time
      const rsiEntry = rsiDataRef.current.find(d => d.time === t)
      const macdEntry = macdDataRef.current.macd.find(d => d.time === t)
      const macdSigEntry = macdDataRef.current.signal.find(d => d.time === t)
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
          rsi: rsiEntry?.value,
          macd: macdEntry?.value,
          macdSignal: macdSigEntry?.value,
          isUp: candle.close >= candle.open,
        })
      }
      // Lock crosshair position across indicator panels within this chart instance
      syncingCrosshairRef.current = true
      try {
        if (rsiChartInstance.current && rsiSeriesRef.current && rsiEntry) {
          rsiChartInstance.current.setCrosshairPosition(rsiEntry.value, t, rsiSeriesRef.current)
        } else {
          rsiChartInstance.current?.clearCrosshairPosition?.()
        }
        if (macdChartInstance.current && macdLineRef.current && macdEntry) {
          macdChartInstance.current.setCrosshairPosition(macdEntry.value, t, macdLineRef.current)
        } else {
          macdChartInstance.current?.clearCrosshairPosition?.()
        }
      } finally {
        syncingCrosshairRef.current = false
      }
      // Grid mode: broadcast wall-clock time to sibling compact charts
      if (compact) {
        const gen = ++_syncGeneration
        lastSentGenerationRef.current = gen
        setChartCrosshairTime({ time: t, gen })
      }
    })

    // Sync main chart time scale → RSI + MACD within this chart instance only.
    // Grid charts intentionally do NOT sync scroll/zoom across timeframes — each interval
    // has its own time density so sharing logical bar indices produces wrong results.
    chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
      if (syncingTimeRef.current || !range) return
      syncingTimeRef.current = true
      try {
        rsiChartInstance.current?.timeScale().setVisibleLogicalRange(range)
        macdChartInstance.current?.timeScale().setVisibleLogicalRange(range)
      } finally {
        syncingTimeRef.current = false
      }
    })

    const handleResize = () => {
      // rAF ensures CSS grid reflow finishes before we read clientWidth.
      // Also check fullscreen: the resize event fires when entering/exiting fullscreen,
      // and we must not reset the chart back to the non-fullscreen compact height (280px).
      requestAnimationFrame(() => {
        const isFs = !!document.fullscreenElement
        if (chartRef.current && chartInstance.current) {
          chartInstance.current.applyOptions({
            width: isFs ? window.innerWidth : chartRef.current.clientWidth,
            height: isFs ? window.innerHeight - 120 : (compact ? 280 : Math.max(400, window.innerHeight - 280)),
          })
        }
        ;[rsiChartInstance, macdChartInstance].forEach(ref => {
          if (ref.current) {
            ref.current.applyOptions({ width: isFs ? window.innerWidth : (chartRef.current?.clientWidth || 0) })
          }
        })
        setTimeout(syncPriceScaleWidths, 150)
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
      tradeLinesRef.current = []
    }
  }, [])

  // Create/destroy RSI sub-chart
  useEffect(() => {
    if (showRSI && rsiChartRef.current && !rsiChartInstance.current) {
      const rsiChart = createChart(rsiChartRef.current, {
        layout: { background: { color: '#0f172a' }, textColor: '#94a3b8', fontSize: 10, fontFamily: 'monospace' },
        grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        crosshair: { mode: 0 },
        rightPriceScale: { borderColor: '#1e293b', scaleMargins: { top: 0.1, bottom: 0.1 }, minimumWidth: 90 },
        timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false, visible: false },
        width: rsiChartRef.current.clientWidth,
        height: 120,
      })
      // Overbought zone (baseline at 70 — red shading above)
      const obZone = rsiChart.addBaselineSeries({
        baseValue: { type: 'price', price: 70 },
        topLineColor: 'transparent',
        topFillColor1: 'rgba(239,68,68,0.25)',
        topFillColor2: 'rgba(239,68,68,0.05)',
        bottomLineColor: 'transparent',
        bottomFillColor1: 'transparent',
        bottomFillColor2: 'transparent',
        lineWidth: 0,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })

      // Oversold zone (baseline at 40 — green shading below)
      const osZone = rsiChart.addBaselineSeries({
        baseValue: { type: 'price', price: 40 },
        topLineColor: 'transparent',
        topFillColor1: 'transparent',
        topFillColor2: 'transparent',
        bottomLineColor: 'transparent',
        bottomFillColor1: 'rgba(34,197,94,0.25)',
        bottomFillColor2: 'rgba(34,197,94,0.05)',
        lineWidth: 0,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })

      const rsiLine = rsiChart.addLineSeries({ color: '#a78bfa', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true, title: 'RSI 14' })

      // Add clear horizontal reference lines at 70, 50, 40
      rsiLine.createPriceLine({ price: 70, color: '#ef4444', lineWidth: 1, lineStyle: 0, axisLabelVisible: true, title: 'OB 70' })
      rsiLine.createPriceLine({ price: 40, color: '#22c55e', lineWidth: 1, lineStyle: 0, axisLabelVisible: true, title: 'OS 40' })
      rsiLine.createPriceLine({ price: 50, color: '#64748b', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '' })

      rsiChartInstance.current = rsiChart
      rsiSeriesRef.current = rsiLine
      rsiOverboughtRef.current = { obZone, osZone }

      // Sync initial time range from main chart (fixes misalignment on refresh)
      const initRange = chartInstance.current?.timeScale().getVisibleLogicalRange()
      if (initRange) rsiChart.timeScale().setVisibleLogicalRange(initRange)
      // Sync price scale widths so crosshair aligns
      setTimeout(syncPriceScaleWidths, 150)

      // RSI → main + MACD (reverse sync so panning RSI moves main chart too)
      rsiChart.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (syncingTimeRef.current || !range) return
        syncingTimeRef.current = true
        try {
          chartInstance.current?.timeScale().setVisibleLogicalRange(range)
          macdChartInstance.current?.timeScale().setVisibleLogicalRange(range)
        } finally {
          syncingTimeRef.current = false
        }
      })

      // Sync crosshair back to main chart when user hovers RSI panel
      rsiChart.subscribeCrosshairMove(rsiParam => {
        if (syncingCrosshairRef.current) return
        if (!rsiParam.time) {
          chartInstance.current?.clearCrosshairPosition?.()
          macdChartInstance.current?.clearCrosshairPosition?.()
          return
        }
        const t = rsiParam.time
        const data = lastDataRef.current.find(d => d.time === t)
        if (!data || !chartInstance.current || !candleSeriesRef.current) return
        syncingCrosshairRef.current = true
        try {
          chartInstance.current.setCrosshairPosition(data.close, t, candleSeriesRef.current)
          const macdEntry = macdDataRef.current.macd.find(d => d.time === t)
          if (macdChartInstance.current && macdLineRef.current && macdEntry) {
            macdChartInstance.current.setCrosshairPosition(macdEntry.value, t, macdLineRef.current)
          }
          setCrosshairData({
            open: data.open, high: data.high, low: data.low, close: data.close,
            volume: data.volume, isUp: data.close >= data.open,
            rsi: rsiDataRef.current.find(d => d.time === t)?.value,
            macd: macdDataRef.current.macd.find(d => d.time === t)?.value,
            macdSignal: macdDataRef.current.signal.find(d => d.time === t)?.value,
          })
        } finally {
          syncingCrosshairRef.current = false
        }
      })

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
        rightPriceScale: { borderColor: '#1e293b', minimumWidth: 90 },
        timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false, visible: false },
        width: macdChartRef.current.clientWidth,
        height: 120,
      })
      macdLineRef.current = mc.addLineSeries({ color: '#3b82f6', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: true, title: 'MACD' })
      macdSignalRef.current = mc.addLineSeries({ color: '#f97316', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'Signal' })
      macdHistRef.current = mc.addHistogramSeries({ priceFormat: { type: 'price' }, priceScaleId: '' })

      macdChartInstance.current = mc

      // Sync initial time range from main chart (fixes misalignment on refresh)
      const initRange = chartInstance.current?.timeScale().getVisibleLogicalRange()
      if (initRange) mc.timeScale().setVisibleLogicalRange(initRange)
      // Sync price scale widths so crosshair aligns
      setTimeout(syncPriceScaleWidths, 150)

      // MACD → main + RSI (reverse sync so panning MACD moves main chart too)
      mc.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (syncingTimeRef.current || !range) return
        syncingTimeRef.current = true
        try {
          chartInstance.current?.timeScale().setVisibleLogicalRange(range)
          rsiChartInstance.current?.timeScale().setVisibleLogicalRange(range)
        } finally {
          syncingTimeRef.current = false
        }
      })

      // Sync crosshair back to main chart when user hovers MACD panel
      mc.subscribeCrosshairMove(macdParam => {
        if (syncingCrosshairRef.current) return
        if (!macdParam.time) {
          chartInstance.current?.clearCrosshairPosition?.()
          rsiChartInstance.current?.clearCrosshairPosition?.()
          return
        }
        const t = macdParam.time
        const data = lastDataRef.current.find(d => d.time === t)
        if (!data || !chartInstance.current || !candleSeriesRef.current) return
        syncingCrosshairRef.current = true
        try {
          chartInstance.current.setCrosshairPosition(data.close, t, candleSeriesRef.current)
          const rsiEntry = rsiDataRef.current.find(d => d.time === t)
          if (rsiChartInstance.current && rsiSeriesRef.current && rsiEntry) {
            rsiChartInstance.current.setCrosshairPosition(rsiEntry.value, t, rsiSeriesRef.current)
          }
          setCrosshairData({
            open: data.open, high: data.high, low: data.low, close: data.close,
            volume: data.volume, isUp: data.close >= data.open,
            rsi: rsiDataRef.current.find(d => d.time === t)?.value,
            macd: macdDataRef.current.macd.find(d => d.time === t)?.value,
            macdSignal: macdDataRef.current.signal.find(d => d.time === t)?.value,
          })
        } finally {
          syncingCrosshairRef.current = false
        }
      })

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

  // Apply data to RSI & MACD sub-charts; always update lookup refs for crosshair sync
  const applySubCharts = useCallback((data) => {
    const result = computeChartSignals(data, interval)

    // Build RSI data — stored in ref for crosshair value lookup regardless of panel state
    const rsiVals = result.rsiValues || []
    const rsiData = []
    for (let i = 0; i < data.length; i++) {
      if (rsiVals[i] !== null && rsiVals[i] !== undefined) {
        rsiData.push({ time: data[i].time, value: rsiVals[i] })
      }
    }
    rsiDataRef.current = rsiData

    // Build MACD data — stored in ref for crosshair value lookup regardless of panel state
    const macdData = result.macdChartData || []
    macdDataRef.current = {
      macd: macdData.map(d => ({ time: d.time, value: d.macd })),
      signal: macdData.map(d => ({ time: d.time, value: d.signal })),
    }

    // RSI
    if (rsiSeriesRef.current && rsiChartInstance.current) {
      rsiSeriesRef.current.setData(rsiData)
      if (rsiData.length > 0 && rsiOverboughtRef.current) {
        rsiOverboughtRef.current.obZone.setData(rsiData)
        rsiOverboughtRef.current.osZone.setData(rsiData)
      }
    }

    // MACD
    if (macdLineRef.current && macdChartInstance.current) {
      macdLineRef.current.setData(macdDataRef.current.macd)
      macdSignalRef.current.setData(macdDataRef.current.signal)
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
      const { markers, levels, trendLine, pivots, ema20Line, ema50Line, activeTradeZone, tradeStats: ts, tradeHistory, haTrendStatus: haStatus } = computeChartSignals(data, interval)

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

      // Draw S/R levels — R1/R2 (nearest→farthest resistance), S1/S2 (nearest→farthest support)
      if (showSignals) {
        const resistances = levels
          .filter(l => l.type === 'resistance')
          .sort((a, b) => a.price - b.price)  // ascending: R1 = lowest (nearest above price)
        const supports = levels
          .filter(l => l.type === 'support')
          .sort((a, b) => b.price - a.price)  // descending: S1 = highest (nearest below price)
        const taggedLevels = [
          ...resistances.slice(0, 2).map((l, i) => ({ ...l, tag: `R${i + 1}` })),
          ...supports.slice(0, 2).map((l, i) => ({ ...l, tag: `S${i + 1}` })),
        ]
        for (const level of taggedLevels) {
          const priceLine = candleSeriesRef.current.createPriceLine({
            price: level.price,
            color: level.type === 'support' ? '#22c55e80' : '#ef444480',
            lineWidth: 1,
            lineStyle: 2,
            axisLabelVisible: !compact,
            title: level.tag,
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

      // v4: Remove old trade zone lines
      for (const line of tradeLinesRef.current) {
        try { candleSeriesRef.current.removePriceLine(line) } catch {}
      }
      tradeLinesRef.current = []

      // v4: Draw active trade zone lines (SL, Target, Entry)
      if (showSignals && activeTradeZone) {
        const dir = activeTradeZone.direction === 'long' ? '▲' : '▼'
        const entryLine = candleSeriesRef.current.createPriceLine({
          price: activeTradeZone.entryPrice,
          color: '#3b82f6',
          lineWidth: 2,
          lineStyle: 0,
          axisLabelVisible: !compact,
          title: `ENTRY ${dir}`,
        })
        tradeLinesRef.current.push(entryLine)

        const slLine = candleSeriesRef.current.createPriceLine({
          price: activeTradeZone.currentSL,
          color: '#f97316',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: !compact,
          title: compact ? 'SL' : 'STOP LOSS',
        })
        tradeLinesRef.current.push(slLine)

        const tpLine = candleSeriesRef.current.createPriceLine({
          price: activeTradeZone.currentTarget,
          color: '#22d3ee',
          lineWidth: 2,
          lineStyle: 2,
          axisLabelVisible: !compact,
          title: compact ? 'TP' : 'TARGET',
        })
        tradeLinesRef.current.push(tpLine)

        setActiveTradeInfo({
          direction: activeTradeZone.direction,
          entry: activeTradeZone.entryPrice,
          sl: activeTradeZone.currentSL,
          target: activeTradeZone.currentTarget,
          currentPrice: data[data.length - 1]?.close,
        })
      } else {
        setActiveTradeInfo(null)
      }

      // Volume visibility
      if (volumeSeriesRef.current) {
        volumeSeriesRef.current.applyOptions({ visible: showVolume })
      }

      // Sub-charts
      applySubCharts(data)

      // Signal stats + v4 trade stats
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
        setTradeStats(ts || null)
        setHaTrend(haStatus || null)
      } else {
        setSignalStats(null)
        setTradeStats(null)
        setHaTrend(null)
      }
      // Re-sync price scale widths after every signal update (price lines can change
      // the main chart's scale width; sub-charts must match or crosshair drifts).
      setTimeout(syncPriceScaleWidths, 300)
    } catch (e) {
      console.warn('Signal computation error:', e)
    }
  }, [showSignals, showPivots, showVolume, showEMA, interval, compact, applySubCharts, syncPriceScaleWidths])

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

      if (interval !== '1d') data = toIST(data)

      // Try NSE real-time data to patch the latest candles (reduces Yahoo delay)
      try {
        const nseRes = await fetch(`/api/nse-chart/${ticker}?interval=${interval}`)
        if (nseRes.ok) {
          const nseCandles = await nseRes.json()
          if (nseCandles && nseCandles.length > 0) {
            // NSE returns UTC timestamps — convert to IST
            const nseIST = toIST(nseCandles)
            // Merge: replace/append Yahoo candles with fresher NSE data
            const yahooCutoff = data.length > 0 ? data[data.length - 1].time : 0
            const nseNew = nseIST.filter(c => c.time >= yahooCutoff)
            if (nseNew.length > 0) {
              // Replace the last Yahoo candle if NSE has same timestamp
              if (data.length > 0 && nseNew[0].time === data[data.length - 1].time) {
                data[data.length - 1] = { ...data[data.length - 1], ...nseNew[0], volume: data[data.length - 1].volume || nseNew[0].volume }
                nseNew.shift()
              }
              // Append any newer NSE candles
              data = data.concat(nseNew)
            }
          }
        }
      } catch {} // NSE fallback is best-effort — don't break chart if it fails
      data = synthesizeVolume(data)

      const prev = lastDataRef.current
      const isNewData = prev.length === 0 || fullLoad

      if (isNewData) {
        const displayData = candleTypeRef.current === 'ha' ? computeHA(data) : data
        candleSeriesRef.current.setData(
          displayData.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close }))
        )
        // Normalize volume: cap at 95th percentile so outliers don't crush other bars
        const vCap = getVolumeCap(data)
        volCapRef.current = vCap
        volumeSeriesRef.current.setData(
          displayData.map(d => ({
            time: d.time,
            value: Math.min(d.volume || 0, vCap * 1.5),
            color: d.close >= d.open ? 'rgba(34,197,94,0.8)' : 'rgba(239,68,68,0.8)',
          }))
        )
        applySignals(data)

        if (isFirstLoad.current) {
          if (chartInstance.current && data.length > 0) {
            let fromIdx
            let toIdx = data.length - 1 + 3
            if (compact) {
              // Grid view: always show last 25 candles with 8-bar right pad (≈ 33 bars wide).
              // Fixed count regardless of interval so all four quadrants look consistent.
              const compactCount = 25
              const rightPad = 8
              fromIdx = Math.max(0, data.length - compactCount)
              toIdx = data.length - 1 + rightPad
            } else {
              // Single view: show last 1 trading day (2 days for 15m)
              const lastTime = data[data.length - 1].time
              const lastDayStart = Math.floor(lastTime / 86400) * 86400
              const daysToShow = interval === '15m' ? 2 : 1
              fromIdx = interval === '1d'
                ? Math.max(0, data.length - 90)
                : data.findIndex(d => d.time >= lastDayStart - (daysToShow - 1) * 86400)
            }
            if (fromIdx >= 0 && fromIdx < data.length - 5) {
              chartInstance.current.timeScale().setVisibleLogicalRange({
                from: fromIdx,
                to: toIdx,
              })
            } else {
              chartInstance.current.timeScale().fitContent()
            }
          }
          isFirstLoad.current = false
          // Sync price scale widths after first render so crosshair aligns across panels
          setTimeout(syncPriceScaleWidths, 150)
        }
      } else {
        const lastOldTime = prev.length > 0 ? prev[prev.length - 1].time : 0
        // HA requires full recompute for accurate values on each tick
        const displayData = candleTypeRef.current === 'ha' ? computeHA(data) : data
        for (const d of displayData) {
          if (d.time >= lastOldTime) {
            candleSeriesRef.current.update({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })
            volumeSeriesRef.current.update({
              time: d.time,
              value: Math.min(d.volume || 0, (volCapRef.current || d.volume) * 1.5),
              color: d.close >= d.open ? 'rgba(34,197,94,0.8)' : 'rgba(239,68,68,0.8)',
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
  }, [ticker, interval, applySignals, syncPriceScaleWidths])

  useEffect(() => {
    lastDataRef.current = []
    isFirstLoad.current = true
    fetchChart(true)
    const refreshMs = interval === '1m' ? 5000 : interval === '1d' ? 60000 : 10000
    const iv = window.setInterval(() => fetchChart(false), refreshMs)
    return () => window.clearInterval(iv)
  }, [ticker, interval, fetchChart])

  // Re-apply overlays when toggles change
  useEffect(() => {
    if (lastDataRef.current.length > 0) applySignals(lastDataRef.current)
  }, [showSignals, showPivots, showVolume, showEMA, applySignals])

  // Re-render candles instantly when candleType toggles (no refetch)
  useEffect(() => {
    if (!lastDataRef.current.length || !candleSeriesRef.current) return
    const displayData = candleType === 'ha' ? computeHA(lastDataRef.current) : lastDataRef.current
    candleSeriesRef.current.setData(
      displayData.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close }))
    )
  }, [candleType])

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
          <ToggleBtn active={candleType === 'ha'} onClick={() => setCandleType(candleType === 'ha' ? 'candle' : 'ha')}
            label="HA"
            activeClass="bg-orange-500/15 text-orange-400 border border-orange-500/30"
            title="Heikin Ashi candles (smoothed trend)" />
          {!compact && (
            <>
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
            </>
          )}
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
      {showSignals && signalStats && !compact && (
        <div className="px-3 py-1 border-b border-[#1e293b]/70 flex items-center gap-3 text-[10px] font-mono shrink-0 bg-[#0f172a] flex-wrap">
          <span className="text-terminal-green font-medium">{signalStats.buys} Buy</span>
          <span className="text-terminal-red font-medium">{signalStats.sells} Sell</span>
          {signalStats.strong > 0 && <span className="text-amber-400 font-medium">{signalStats.strong} Strong</span>}
          <span className="text-[#475569]">|</span>
          <span className="text-[#64748b]">S/R: {signalStats.levels}</span>
          {signalStats.lastSignal && (
            <>
              <span className="text-[#475569]">|</span>
              <span className={signalStats.lastSignal.text.includes('BUY') ? 'text-terminal-green' : 'text-terminal-red'}>
                Latest: {signalStats.lastSignal.text}
              </span>
            </>
          )}
          {tradeStats && (
            <>
              <span className="text-[#475569]">|</span>
              <span className="text-[#94a3b8]">Trades: {tradeStats.completedTrades}</span>
              {tradeStats.completedTrades > 0 && (
                <>
                  <span className={tradeStats.winRate >= 50 ? 'text-terminal-green' : 'text-terminal-red'}>
                    Win: {tradeStats.winRate}%
                  </span>
                  <span className={tradeStats.totalPnlPts >= 0 ? 'text-terminal-green' : 'text-terminal-red'}>
                    P&L: {tradeStats.totalPnlPts > 0 ? '+' : ''}{tradeStats.totalPnlPts} pts
                  </span>
                </>
              )}
            </>
          )}
          {haTrend && (
            <>
              <span className="text-[#475569]">|</span>
              <span className={`font-medium ${haTrend.isBullish ? 'text-terminal-green' : 'text-terminal-red'}`}>
                HA: {haTrend.isBullish ? '▲' : '▼'}{haTrend.isStrong ? '●' : '○'} {haTrend.consecutive}
                {haTrend.isEstablished ? ' TREND' : ''}
                {haTrend.colorFlip ? ' FLIP!' : ''}
                {haTrend.isIndecision ? ' ⟷' : ''}
              </span>
            </>
          )}
          <span className="text-[#475569] ml-auto">HA filtered • Dynamic SL • ATR trailing</span>
        </div>
      )}

      {/* v4: Active trade status bar */}
      {showSignals && activeTradeInfo && !compact && (
        <div className={`px-3 py-1.5 border-b flex items-center gap-3 text-[10px] font-mono shrink-0 ${
          activeTradeInfo.direction === 'long'
            ? 'bg-terminal-green/5 border-terminal-green/20'
            : 'bg-terminal-red/5 border-terminal-red/20'
        }`}>
          <span className={`font-bold ${activeTradeInfo.direction === 'long' ? 'text-terminal-green' : 'text-terminal-red'}`}>
            ACTIVE {activeTradeInfo.direction === 'long' ? 'LONG ▲' : 'SHORT ▼'}
          </span>
          <span className="text-[#475569]">|</span>
          <span className="text-blue-400">Entry: {activeTradeInfo.entry.toFixed(2)}</span>
          <span className="text-[#475569]">|</span>
          <span className="text-orange-400">SL: {activeTradeInfo.sl.toFixed(2)}</span>
          <span className="text-[#475569]">|</span>
          <span className="text-cyan-400">Target: {activeTradeInfo.target.toFixed(2)}</span>
          {activeTradeInfo.currentPrice && (
            <>
              <span className="text-[#475569]">|</span>
              {(() => {
                const pnl = activeTradeInfo.direction === 'long'
                  ? activeTradeInfo.currentPrice - activeTradeInfo.entry
                  : activeTradeInfo.entry - activeTradeInfo.currentPrice
                const pnlPct = ((pnl / activeTradeInfo.entry) * 100).toFixed(2)
                return (
                  <span className={pnl >= 0 ? 'text-terminal-green font-bold' : 'text-terminal-red font-bold'}>
                    P&L: {pnl >= 0 ? '+' : ''}{pnlPct}% ({pnl >= 0 ? '+' : ''}{pnl.toFixed(2)} pts)
                  </span>
                )
              })()}
            </>
          )}
          <span className="text-amber-400/70 ml-auto animate-pulse">● TRACKING</span>
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
            {crosshairData.rsi != null && showRSI && (
              <><span className="text-[#475569]">|</span><span className="text-purple-400">RSI</span><span className={crosshairData.rsi > 70 ? 'text-terminal-red font-bold' : crosshairData.rsi < 40 ? 'text-terminal-green font-bold' : 'text-[#94a3b8]'}>{crosshairData.rsi.toFixed(1)}</span></>
            )}
            {crosshairData.macd != null && showMACD && (
              <><span className="text-[#475569]">|</span><span className="text-blue-400">MACD</span><span className="text-[#94a3b8]">{crosshairData.macd.toFixed(2)}</span><span className="text-[#475569] mx-0.5">/</span><span className="text-orange-400">Sig</span><span className="text-[#94a3b8]">{crosshairData.macdSignal?.toFixed(2)}</span></>
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
            <span className="text-terminal-red">OB 70</span>
            <span className="text-[#64748b]">50</span>
            <span className="text-terminal-green">OS 40</span>
            {crosshairData?.rsi != null && (
              <>
                <span className="text-[#475569]">|</span>
                <span className={`font-bold ${crosshairData.rsi > 70 ? 'text-terminal-red' : crosshairData.rsi < 40 ? 'text-terminal-green' : 'text-purple-300'}`}>
                  RSI {crosshairData.rsi.toFixed(1)}
                </span>
              </>
            )}
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
            {crosshairData?.macd != null && (
              <>
                <span className="text-[#475569]">|</span>
                <span className="text-blue-300 font-bold">{crosshairData.macd.toFixed(2)}</span>
                <span className="text-orange-300">{crosshairData.macdSignal?.toFixed(2)}</span>
              </>
            )}
          </div>
          <div ref={macdChartRef} />
        </div>
      )}

      {/* ── Legend footer ── */}
      {!compact && (showSignals || showPivots || showEMA) && (
        <div className="px-3 py-1.5 border-t border-[#1e293b] shrink-0 bg-[#0f172a]">
          <div className="flex items-center gap-3 text-[10px] font-mono text-[#64748b] flex-wrap">
            {showSignals && (
              <>
                <span><span className="inline-block w-2 h-2 rounded-full bg-terminal-green mr-1 align-middle" />SuperTrend Up</span>
                <span><span className="inline-block w-2 h-2 rounded-full bg-terminal-red mr-1 align-middle" />SuperTrend Down</span>
                <span><span className="text-terminal-green mr-0.5">▲</span>Buy</span>
                <span><span className="text-terminal-red mr-0.5">▼</span>Sell</span>
                <span><span className="text-cyan-400 mr-0.5">●</span>Exit Profit</span>
                <span><span className="text-orange-400 mr-0.5">■</span>Exit Loss</span>
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
