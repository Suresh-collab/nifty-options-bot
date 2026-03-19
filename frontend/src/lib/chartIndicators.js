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

  // Use recent candles to find swing highs/lows
  const recent = candles.slice(-lookback * 3)

  for (let i = 2; i < recent.length - 2; i++) {
    const c = recent[i]
    // Swing high
    if (c.high > recent[i - 1].high && c.high > recent[i - 2].high &&
        c.high > recent[i + 1].high && c.high > recent[i + 2].high) {
      levels.push({ price: c.high, type: 'resistance', time: c.time })
    }
    // Swing low
    if (c.low < recent[i - 1].low && c.low < recent[i - 2].low &&
        c.low < recent[i + 1].low && c.low < recent[i + 2].low) {
      levels.push({ price: c.low, type: 'support', time: c.time })
    }
  }

  // Cluster nearby levels (within 0.15% of each other)
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

  // Return strongest levels
  clustered.sort((a, b) => b.strength - a.strength)
  return clustered.slice(0, 6) // Top 6 levels
}

// ─── Volume Profile (simple: above/below average) ───────────────────
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

// ─── CONFLUENCE SIGNAL ENGINE ───────────────────────────────────────
// This is the core: only generate buy/sell when multiple indicators agree

export function computeChartSignals(candles) {
  if (!candles || candles.length < 30) {
    return { markers: [], levels: [], tpSlBoxes: [], trendLine: [] }
  }

  const closes = candles.map(c => c.close)
  const rsiValues = rsi(closes, 14)
  const macdData = macd(closes, 12, 26, 9)
  const stData = superTrend(candles, 7, 3)
  const srLevels = supportResistance(candles)

  const markers = []
  const tpSlBoxes = []

  // EMA 20 and 50 for trend confirmation
  const ema20 = ema(closes, 20)
  const ema50 = ema(closes, 50)

  // Scan for confluence signals
  for (let i = Math.max(50, 30); i < candles.length; i++) {
    let bullSignals = 0
    let bearSignals = 0

    // 1. SuperTrend direction change
    if (stData.direction[i] === 1 && stData.direction[i - 1] === -1) bullSignals += 2
    if (stData.direction[i] === -1 && stData.direction[i - 1] === 1) bearSignals += 2

    // 2. RSI condition
    if (rsiValues[i] !== null) {
      if (rsiValues[i] < 35) bullSignals += 1
      else if (rsiValues[i] > 65) bearSignals += 1
      // RSI reversal from oversold/overbought
      if (rsiValues[i] > 30 && rsiValues[i - 1] !== null && rsiValues[i - 1] < 30) bullSignals += 1
      if (rsiValues[i] < 70 && rsiValues[i - 1] !== null && rsiValues[i - 1] > 70) bearSignals += 1
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
      // Volume confirms the direction
      if (candles[i].close > candles[i].open) bullSignals += 0.5
      else bearSignals += 0.5
    }

    // CONFLUENCE CHECK: Only signal if score >= 3 (strong agreement)
    const isBuy = bullSignals >= 3 && bearSignals < 1.5
    const isSell = bearSignals >= 3 && bullSignals < 1.5

    if (isBuy || isSell) {
      // Avoid consecutive signals too close together (min 3 candles apart)
      const lastMarker = markers[markers.length - 1]
      if (lastMarker && i - candles.indexOf(candles.find(c => c.time === lastMarker.time)) < 3) continue

      const confidence = isBuy ? bullSignals : bearSignals
      const isStrong = confidence >= 4

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

  return { markers, levels: srLevels, tpSlBoxes, trendLine }
}
