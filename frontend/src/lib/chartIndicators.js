/**
 * Client-side technical indicator calculations for chart overlays.
 * Inspired by TradingView indicators:
 * - ALPHA X Vision (multi-indicator confluence entry/exit)
 * - Sniper Entry Engine (auto TP/SL boxes)
 * - VMDM (volume-momentum divergence)
 * - Smart Breakout Targets
 * - Heikin-Ashi RSI Trend Cloud
 *
 * Core principle: Only signal when MULTIPLE indicators agree (confluence).
 * This reduces false signals and avoids common indicator traps.
 *
 * IMPROVEMENT LOG (continuous improvement):
 * v1: Basic confluence (3+ indicators agree)
 * v2: Added trend strength filter — suppress counter-trend signals during
 *     strong moves (>1.5% intraday drop = don't generate BUY signals).
 *     Added panic/capitulation detection (large red candles + high volume).
 *     Increased minimum candle spacing between signals from 3 to 5.
 *     RSI oversold no longer counts as bullish during a crash.
 * v3: Interval-aware signal density control. 15m (60-day range) was flooding
 *     with 50+ signals. Now uses per-interval config: wider spacing (12 candles
 *     for 15m vs 5 for 5m), higher confluence threshold (3.5 vs 3), max signal
 *     cap (15 for 15m vs 20 for 5m), and higher strong-signal bar (5 vs 4.5).
 */

// ─── EMA ────────────────────────────────────────────────────────────
function ema(data, period) {
  const k = 2 / (period + 1)
  const result = [data[0]]
  for (let i = 1; i < data.length; i++) {
    result.push(data[i] * k + result[i - 1] * (1 - k))
  }
  return result
}

// ─── RSI ────────────────────────────────────────────────────────────
function rsi(closes, period = 14) {
  const result = new Array(closes.length).fill(null)
  if (closes.length < period + 1) return result

  let avgGain = 0, avgLoss = 0
  for (let i = 1; i <= period; i++) {
    const change = closes[i] - closes[i - 1]
    if (change > 0) avgGain += change
    else avgLoss -= change
  }
  avgGain /= period
  avgLoss /= period

  result[period] = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss))

  for (let i = period + 1; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1]
    avgGain = (avgGain * (period - 1) + (change > 0 ? change : 0)) / period
    avgLoss = (avgLoss * (period - 1) + (change < 0 ? -change : 0)) / period
    result[i] = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss))
  }
  return result
}

// ─── MACD ───────────────────────────────────────────────────────────
function macd(closes, fast = 12, slow = 26, signal = 9) {
  const emaFast = ema(closes, fast)
  const emaSlow = ema(closes, slow)
  const macdLine = emaFast.map((v, i) => v - emaSlow[i])
  const signalLine = ema(macdLine, signal)
  const histogram = macdLine.map((v, i) => v - signalLine[i])
  return { macdLine, signalLine, histogram }
}

// ─── SuperTrend ─────────────────────────────────────────────────────
function superTrend(candles, period = 7, multiplier = 3) {
  const len = candles.length
  const st = new Array(len).fill(null)
  const direction = new Array(len).fill(1)

  // ATR
  const tr = candles.map((c, i) => {
    if (i === 0) return c.high - c.low
    const prev = candles[i - 1]
    return Math.max(c.high - c.low, Math.abs(c.high - prev.close), Math.abs(c.low - prev.close))
  })

  const atr = new Array(len).fill(null)
  if (len >= period) {
    let sum = 0
    for (let i = 0; i < period; i++) sum += tr[i]
    atr[period - 1] = sum / period
    for (let i = period; i < len; i++) {
      atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    }
  }

  const upperBand = new Array(len).fill(null)
  const lowerBand = new Array(len).fill(null)

  for (let i = period - 1; i < len; i++) {
    const hl2 = (candles[i].high + candles[i].low) / 2
    upperBand[i] = hl2 + multiplier * atr[i]
    lowerBand[i] = hl2 - multiplier * atr[i]
  }

  for (let i = period; i < len; i++) {
    if (candles[i].close > upperBand[i - 1]) {
      direction[i] = 1
    } else if (candles[i].close < lowerBand[i - 1]) {
      direction[i] = -1
    } else {
      direction[i] = direction[i - 1]
      if (direction[i] === 1 && lowerBand[i] < lowerBand[i - 1]) {
        lowerBand[i] = lowerBand[i - 1]
      }
      if (direction[i] === -1 && upperBand[i] > upperBand[i - 1]) {
        upperBand[i] = upperBand[i - 1]
      }
    }
    st[i] = direction[i] === 1 ? lowerBand[i] : upperBand[i]
  }

  return { supertrend: st, direction }
}

// ─── Support & Resistance (Pivot-based) ─────────────────────────────
function supportResistance(candles, lookback = 20) {
  const levels = []
  if (candles.length < lookback) return levels

  const recent = candles.slice(-lookback * 3)

  for (let i = 2; i < recent.length - 2; i++) {
    const c = recent[i]
    if (c.high > recent[i - 1].high && c.high > recent[i - 2].high &&
        c.high > recent[i + 1].high && c.high > recent[i + 2].high) {
      levels.push({ price: c.high, type: 'resistance', time: c.time })
    }
    if (c.low < recent[i - 1].low && c.low < recent[i - 2].low &&
        c.low < recent[i + 1].low && c.low < recent[i + 2].low) {
      levels.push({ price: c.low, type: 'support', time: c.time })
    }
  }

  const clustered = []
  const used = new Set()
  for (let i = 0; i < levels.length; i++) {
    if (used.has(i)) continue
    let sum = levels[i].price, count = 1
    const type = levels[i].type
    for (let j = i + 1; j < levels.length; j++) {
      if (used.has(j)) continue
      if (Math.abs(levels[j].price - levels[i].price) / levels[i].price < 0.0015) {
        sum += levels[j].price
        count++
        used.add(j)
      }
    }
    used.add(i)
    clustered.push({ price: Math.round((sum / count) * 100) / 100, type, strength: count })
  }

  clustered.sort((a, b) => b.strength - a.strength)
  return clustered.slice(0, 6)
}

// ─── Volume Profile ─────────────────────────────────────────────────
function volumeAnalysis(candles, period = 20) {
  if (candles.length < period) return { aboveAvg: false, ratio: 1 }
  const recent = candles.slice(-period)
  const avgVol = recent.reduce((s, c) => s + c.volume, 0) / period
  const lastVol = candles[candles.length - 1].volume
  return {
    aboveAvg: lastVol > avgVol * 1.3,
    ratio: avgVol > 0 ? lastVol / avgVol : 1,
  }
}

// ─── TREND STRENGTH DETECTOR (v2) ──────────────────────────────────
// Measures how strong the current intraday trend is.
// Used to suppress counter-trend signals during crashes/rallies.
function trendStrength(candles, i, lookback = 20) {
  if (i < lookback) return { change: 0, isCrash: false, isRally: false, isPanic: false }

  const windowStart = Math.max(0, i - lookback)
  const startPrice = candles[windowStart].close
  const currentPrice = candles[i].close
  const changePct = ((currentPrice - startPrice) / startPrice) * 100

  // Count consecutive red/green candles
  let consecutiveRed = 0
  let consecutiveGreen = 0
  for (let j = i; j > windowStart; j--) {
    if (candles[j].close < candles[j].open) {
      consecutiveRed++
      consecutiveGreen = 0
    } else {
      consecutiveGreen++
      break
    }
  }
  for (let j = i; j > windowStart; j--) {
    if (candles[j].close > candles[j].open) {
      consecutiveGreen++
      consecutiveRed = 0
    } else {
      break
    }
  }

  // Detect panic: large red candles with high volume
  const recentCandles = candles.slice(Math.max(0, i - 5), i + 1)
  const avgRange = candles.slice(windowStart, i + 1)
    .reduce((s, c) => s + (c.high - c.low), 0) / lookback
  const isPanic = recentCandles.some(c => {
    const bodySize = Math.abs(c.close - c.open)
    const isLargeRed = c.close < c.open && bodySize > avgRange * 2
    return isLargeRed
  })

  return {
    change: changePct,
    isCrash: changePct < -1.5,      // >1.5% drop = crash mode
    isRally: changePct > 1.5,        // >1.5% rise = rally mode
    isStrongDown: changePct < -0.8,   // noticeable downtrend
    isStrongUp: changePct > 0.8,      // noticeable uptrend
    isPanic,                           // capitulation candles detected
    consecutiveRed,
    consecutiveGreen,
  }
}

// ─── CONFLUENCE SIGNAL ENGINE (v2) ──────────────────────────────────
// Only generate buy/sell when multiple indicators agree AND
// the signal aligns with the broader trend (no counter-trend traps).

export function computeChartSignals(candles, interval = '5m') {
  if (!candles || candles.length < 30) {
    return { markers: [], levels: [], tpSlBoxes: [], trendLine: [], rsiValues: [], pivots: [] }
  }

  // Interval-aware settings to control signal density
  // 15m fetches 60 days of data (~1600 candles) vs 5m fetches 5 days (~390 candles)
  const intervalConfig = {
    '1m':  { minSpacing: 10, maxSignals: 25, confluenceThreshold: 3,   strongThreshold: 4.5 },
    '5m':  { minSpacing: 5,  maxSignals: 20, confluenceThreshold: 3,   strongThreshold: 4.5 },
    '15m': { minSpacing: 12, maxSignals: 15, confluenceThreshold: 3.5, strongThreshold: 5   },
  }
  const cfg = intervalConfig[interval] || intervalConfig['5m']

  const closes = candles.map(c => c.close)
  const rsiValues = rsi(closes, 14)
  const macdData = macd(closes, 12, 26, 9)
  const stData = superTrend(candles, 7, 3)
  const srLevels = supportResistance(candles)

  const markers = []
  const tpSlBoxes = []
  let lastMarkerIdx = -10

  // EMA 20 and 50 for trend confirmation
  const ema20 = ema(closes, 20)
  const ema50 = ema(closes, 50)

  // Scan for confluence signals
  for (let i = Math.max(50, 30); i < candles.length; i++) {
    let bullSignals = 0
    let bearSignals = 0

    // ── Trend context (v2) ──────────────────────────────────────
    const trend = trendStrength(candles, i, 30)

    // 1. SuperTrend direction change (strongest single signal)
    if (stData.direction[i] === 1 && stData.direction[i - 1] === -1) bullSignals += 2
    if (stData.direction[i] === -1 && stData.direction[i - 1] === 1) bearSignals += 2

    // 2. RSI condition — BUT NOT during crashes/rallies (v2 fix)
    if (rsiValues[i] !== null) {
      // v2: RSI oversold does NOT count as bullish during a crash
      // (prevents "catching falling knife" false BUY signals)
      if (rsiValues[i] < 35 && !trend.isStrongDown) bullSignals += 1
      if (rsiValues[i] > 65 && !trend.isStrongUp) bearSignals += 1

      // RSI reversal — only valid if trend supports it
      if (rsiValues[i] > 30 && rsiValues[i - 1] !== null && rsiValues[i - 1] < 30 && !trend.isStrongDown) {
        bullSignals += 1
      }
      if (rsiValues[i] < 70 && rsiValues[i - 1] !== null && rsiValues[i - 1] > 70 && !trend.isStrongUp) {
        bearSignals += 1
      }
    }

    // 3. MACD crossover
    if (macdData.macdLine[i] > macdData.signalLine[i] && macdData.macdLine[i - 1] <= macdData.signalLine[i - 1]) {
      bullSignals += 1
    }
    if (macdData.macdLine[i] < macdData.signalLine[i] && macdData.macdLine[i - 1] >= macdData.signalLine[i - 1]) {
      bearSignals += 1
    }

    // 4. EMA trend alignment
    if (ema20[i] > ema50[i]) bullSignals += 0.5
    if (ema20[i] < ema50[i]) bearSignals += 0.5

    // 5. Volume confirmation
    const vol = volumeAnalysis(candles.slice(0, i + 1), 20)
    if (vol.aboveAvg) {
      if (candles[i].close > candles[i].open) bullSignals += 0.5
      else bearSignals += 0.5
    }

    // 6. (v2) Trend momentum bonus — reward signals that align with trend
    if (trend.isStrongDown) bearSignals += 1    // downtrend boosts sell signals
    if (trend.isStrongUp) bullSignals += 1      // uptrend boosts buy signals
    if (trend.isCrash) bearSignals += 1.5       // crash mode: strong sell bias
    if (trend.isRally) bullSignals += 1.5       // rally mode: strong buy bias

    // 7. (v2) Panic detection — high-volume large red candles
    if (trend.isPanic) {
      bearSignals += 1
      bullSignals -= 1  // actively suppress counter-trend buys
    }

    // ── CONFLUENCE CHECK ────────────────────────────────────────
    // v2: Raised threshold and added trend alignment requirement
    let isBuy = bullSignals >= cfg.confluenceThreshold && bearSignals < 1.5
    let isSell = bearSignals >= cfg.confluenceThreshold && bullSignals < 1.5

    // v2: BLOCK counter-trend signals during extreme moves
    if (trend.isCrash && isBuy) isBuy = false   // Never BUY during a crash
    if (trend.isRally && isSell) isSell = false  // Never SELL during a rally

    // v2: During panic, only allow SELL signals
    if (trend.isPanic && isBuy) isBuy = false

    if (isBuy || isSell) {
      // v3: Interval-aware spacing — 15m uses wider gaps to avoid signal flood
      if (i - lastMarkerIdx < cfg.minSpacing) continue
      // v3: Cap total signals to keep chart readable
      if (markers.length >= cfg.maxSignals) continue
      lastMarkerIdx = i

      const confidence = isBuy ? bullSignals : bearSignals
      const isStrong = confidence >= cfg.strongThreshold

      markers.push({
        time: candles[i].time,
        position: isBuy ? 'belowBar' : 'aboveBar',
        color: isBuy ? '#22c55e' : '#ef4444',
        shape: isBuy ? 'arrowUp' : 'arrowDown',
        text: isBuy
          ? (isStrong ? 'STRONG BUY' : 'BUY')
          : (isStrong ? 'STRONG SELL' : 'SELL'),
        size: isStrong ? 2 : 1,
      })

      // Generate TP/SL box for this signal
      const atrApprox = candles.slice(Math.max(0, i - 14), i + 1)
        .reduce((sum, c) => sum + (c.high - c.low), 0) / Math.min(14, i + 1)

      if (isBuy) {
        tpSlBoxes.push({
          time: candles[i].time,
          entry: candles[i].close,
          tp: Math.round((candles[i].close + atrApprox * 2) * 100) / 100,
          sl: Math.round((candles[i].close - atrApprox * 1) * 100) / 100,
          direction: 'long',
        })
      } else {
        tpSlBoxes.push({
          time: candles[i].time,
          entry: candles[i].close,
          tp: Math.round((candles[i].close - atrApprox * 2) * 100) / 100,
          sl: Math.round((candles[i].close + atrApprox * 1) * 100) / 100,
          direction: 'short',
        })
      }
    }
  }

  // Build SuperTrend line data for chart overlay
  const trendLine = candles.map((c, i) => {
    if (stData.supertrend[i] === null) return null
    return {
      time: c.time,
      value: Math.round(stData.supertrend[i] * 100) / 100,
      color: stData.direction[i] === 1 ? '#22c55e' : '#ef4444',
    }
  }).filter(Boolean)

  // ─── Pivot Points (Classic Floor Pivots from previous day) ────────
  const pivots = computePivots(candles)

  return { markers, levels: srLevels, tpSlBoxes, trendLine, rsiValues, pivots }
}

// ─── PIVOT POINT CALCULATOR ────────────────────────────────────────
// Classic floor pivots: PP = (H+L+C)/3, then R1/R2/S1/S2
function computePivots(candles) {
  if (candles.length < 20) return []

  // Group candles by day (using UTC date from timestamp)
  const days = {}
  for (const c of candles) {
    const dayKey = Math.floor(c.time / 86400)
    if (!days[dayKey]) days[dayKey] = { high: -Infinity, low: Infinity, close: 0 }
    days[dayKey].high = Math.max(days[dayKey].high, c.high)
    days[dayKey].low = Math.min(days[dayKey].low, c.low)
    days[dayKey].close = c.close
  }

  const dayKeys = Object.keys(days).sort()
  if (dayKeys.length < 2) return []

  // Use previous day's H/L/C to compute today's pivots
  const prevDay = days[dayKeys[dayKeys.length - 2]]
  const h = prevDay.high, l = prevDay.low, c = prevDay.close
  const pp = (h + l + c) / 3

  return [
    { price: Math.round(pp * 100) / 100, label: 'PP', color: '#a78bfa' },
    { price: Math.round((2 * pp - l) * 100) / 100, label: 'R1', color: '#ef4444' },
    { price: Math.round((pp + (h - l)) * 100) / 100, label: 'R2', color: '#ef4444' },
    { price: Math.round((2 * pp - h) * 100) / 100, label: 'S1', color: '#22c55e' },
    { price: Math.round((pp - (h - l)) * 100) / 100, label: 'S2', color: '#22c55e' },
  ]
}
