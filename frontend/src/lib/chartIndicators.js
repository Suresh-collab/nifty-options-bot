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
 * v4: DYNAMIC TRADE LIFECYCLE MANAGEMENT. Every BUY/SELL entry is now tracked
 *     through to exit. Features:
 *     - ATR-based trailing stop-loss that moves with favorable price action
 *     - Dynamic targets that extend when momentum supports continuation
 *     - Indicator-aware exits: SuperTrend flip + MACD cross triggers early exit
 *     - One trade at a time: no new entry while position is open
 *     - EXIT markers on chart: "EXIT SL ✕", "EXIT TARGET ✓", "EXIT FLIP"
 *     - Live SL/target lines on chart for active trades
 *     - Trade performance stats (win rate, P&L)
 * v5: HEIKIN ASHI HYBRID TREND FILTER. HA candles are computed alongside real
 *     candles but used ONLY as a trend filter — not for price levels.
 *     - HA trend confirmation: BUY blocked if HA is bearish (red), SELL blocked if bullish
 *     - HA color-flip detection: trend reversal early warning tightens SL in trade mgmt
 *     - HA wick analysis: no lower wick = strong uptrend (+confluence), no upper wick = strong downtrend
 *     - HA consecutive count: 3+ same-color HA candles = established trend (higher confidence)
 *     - All entry/exit/SL prices remain on REAL candle data (never HA synthetic prices)
 * v6: SELF-RETROSPECT FIXES after analyzing live chart output:
 *     Problems found: 9 Buy vs 1 Sell (bullish bias), tiny SL exits (+/-0.1%),
 *     signal clustering, re-entry churn after SL, missed the big 800pt crash.
 *     Fixes:
 *     - Wider SL (2x ATR initial, phased trailing: 2x→1.5x→1.2x as profit grows)
 *     - Wider target (3x ATR) for better reward/risk ratio
 *     - Higher spacing (10 candles for 5m) and higher confluence threshold (3.5)
 *     - Cooldown after SL exit: no same-direction re-entry for 8 candles (5m)
 *     - Better SELL detection: ongoing SuperTrend direction (+0.5), RSI momentum,
 *       MACD below-zero bias, EMA crossover events, price-below-both-EMAs
 *     - Relaxed opposing-signal gate: net score >= 2 instead of opposing < 1.5
 *       (the old gate made SELL nearly impossible due to residual bull scores)
 *     - Softened HA tightening: single HA flip no longer instantly tightens SL
 * v7: DECOUPLED ARCHITECTURE. Fixed critical regression where signals on the
 *     19th disappeared because trade lifecycle was blocking signal generation.
 *     Root cause: "one trade at a time" rule + wider SL meant the 18th BUY
 *     trade consumed all candles through the 19th crash, suppressing all signals.
 *     Fix: Split into 3 passes:
 *       Pass 1: Generate ALL signals independently (no trade state dependency)
 *       Pass 2: Run trade lifecycle over signals as informational overlay
 *       Pass 3: Build chart overlays
 *     Also: trades bounded by next signal (trade auto-closes when next entry fires),
 *     restored original spacing (5 candles for 5m), removed SL cooldown (was too
 *     aggressive), and net-score gate relaxed to 1.5 for better SELL generation.
 * v8: VISUAL CLARITY + INTERVAL TUNING. Fixed 3 major issues from v7:
 *     1. 1m was unreadable (25 signals crammed together) — widened to 30-candle
 *        spacing (30 min gaps), max 12 signals
 *     2. 15m signals clustered at start of 60-day range because maxSignals=15
 *        was hit in first few days — increased to 40 with 20-candle spacing
 *     3. Marker text too long (SL price in text caused overlap) — removed SL
 *        from marker text, shortened exit labels (SL✕, TP✓, FLIP, EXIT)
 *     Also: trades that reach next signal boundary without hitting SL/target
 *     are now properly closed and recorded (was silently dropped before),
 *     exit markers shrunk to size 1 to reduce visual noise.
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

// ─── Heikin Ashi (v5) ─────────────────────────────────────────────────
// Computes HA candles + per-candle trend analysis for use as a filter.
// Returns HA candles and per-bar trend signals (NOT for price display).
function heikinAshi(candles) {
  const len = candles.length
  if (len === 0) return { ha: [], trend: [] }

  const ha = new Array(len)
  const trend = new Array(len)

  // First HA candle
  ha[0] = {
    open: (candles[0].open + candles[0].close) / 2,
    close: (candles[0].open + candles[0].high + candles[0].low + candles[0].close) / 4,
    high: candles[0].high,
    low: candles[0].low,
  }
  ha[0].isBullish = ha[0].close >= ha[0].open

  for (let i = 1; i < len; i++) {
    const c = candles[i]
    const haOpen = (ha[i - 1].open + ha[i - 1].close) / 2
    const haClose = (c.open + c.high + c.low + c.close) / 4
    const haHigh = Math.max(c.high, haOpen, haClose)
    const haLow = Math.min(c.low, haOpen, haClose)

    ha[i] = { open: haOpen, close: haClose, high: haHigh, low: haLow }
    ha[i].isBullish = haClose >= haOpen

    // ── HA Wick Analysis ──
    const body = Math.abs(haClose - haOpen)
    const upperWick = haHigh - Math.max(haOpen, haClose)
    const lowerWick = Math.min(haOpen, haClose) - haLow

    // Strong bullish: no lower wick (or tiny) = buyers in full control
    const noLowerWick = lowerWick < body * 0.1
    // Strong bearish: no upper wick = sellers in full control
    const noUpperWick = upperWick < body * 0.1
    // Indecision: both wicks present, small body (doji-like)
    const isIndecision = upperWick > body * 0.5 && lowerWick > body * 0.5

    // ── Consecutive HA color count ──
    let consecutiveBull = 0
    let consecutiveBear = 0
    if (ha[i].isBullish) {
      consecutiveBull = 1
      for (let j = i - 1; j >= 0 && ha[j].isBullish; j--) consecutiveBull++
    } else {
      consecutiveBear = 1
      for (let j = i - 1; j >= 0 && !ha[j].isBullish; j--) consecutiveBear++
    }

    // ── Color flip detection ──
    const colorFlipToBull = ha[i].isBullish && !ha[i - 1].isBullish
    const colorFlipToBear = !ha[i].isBullish && ha[i - 1].isBullish

    trend[i] = {
      isBullish: ha[i].isBullish,
      isStrongBullish: ha[i].isBullish && noLowerWick,
      isStrongBearish: !ha[i].isBullish && noUpperWick,
      isIndecision,
      consecutiveBull,
      consecutiveBear,
      colorFlipToBull,
      colorFlipToBear,
      // Established trend: 3+ consecutive same-color HA candles
      isEstablishedBull: consecutiveBull >= 3,
      isEstablishedBear: consecutiveBear >= 3,
    }
  }

  // First candle trend
  trend[0] = {
    isBullish: ha[0].isBullish,
    isStrongBullish: false, isStrongBearish: false, isIndecision: false,
    consecutiveBull: ha[0].isBullish ? 1 : 0,
    consecutiveBear: ha[0].isBullish ? 0 : 1,
    colorFlipToBull: false, colorFlipToBear: false,
    isEstablishedBull: false, isEstablishedBear: false,
  }

  return { ha, trend }
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

// ─── ATR (Average True Range) — standalone for trade management ─────
function atr(candles, period = 14) {
  const len = candles.length
  const tr = candles.map((c, i) => {
    if (i === 0) return c.high - c.low
    const prev = candles[i - 1]
    return Math.max(c.high - c.low, Math.abs(c.high - prev.close), Math.abs(c.low - prev.close))
  })
  const result = new Array(len).fill(null)
  if (len < period) return result
  let sum = 0
  for (let i = 0; i < period; i++) sum += tr[i]
  result[period - 1] = sum / period
  for (let i = period; i < len; i++) {
    result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
  }
  return result
}

// ─── DYNAMIC TRADE MANAGER (v4) ────────────────────────────────────
// Manages the full lifecycle of each trade:
// - Entry → dynamic trailing SL (ATR-based) → EXIT (SL hit / target hit / indicator flip)
// - SL and targets are recalculated every candle based on current ATR
// - Trailing SL locks in profits as price moves favorably
// - Indicator deterioration (SuperTrend flip, MACD cross against) tightens stops
//
// Key principles:
// 1. ATR-adaptive: wider stops in volatile markets, tighter in calm markets
// 2. Trailing: SL only moves in favorable direction, never backwards
// 3. Indicator-aware: if indicators flip against the trade, force early exit
// 4. One trade at a time: no new entry while a trade is active

function manageTradeLifecycle(candles, entryIdx, direction, atrValues, stData, macdData, rsiValues, ema20, ema50, haTrend, maxIdx) {
  const entry = candles[entryIdx].close
  const entryATR = atrValues[entryIdx] || (candles[entryIdx].high - candles[entryIdx].low)
  // v7: maxIdx = boundary (next signal index or data end) — trade can't extend past it
  const endIdx = maxIdx || candles.length

  // v6: Wider initial levels: SL = 2x ATR, Target = 3x ATR (gives 1.5 R:R)
  let currentSL = direction === 'long'
    ? entry - entryATR * 2.0
    : entry + entryATR * 2.0
  let currentTarget = direction === 'long'
    ? entry + entryATR * 3.0
    : entry - entryATR * 3.0

  let highWaterMark = entry
  let lowWaterMark = entry
  let exitIdx = null
  let exitReason = null
  let exitPrice = null
  let tradeZones = []
  let indicatorWarnings = 0

  for (let i = entryIdx + 1; i < endIdx; i++) {
    const c = candles[i]
    const currentATR = atrValues[i] || entryATR

    // ── Update water marks ──
    if (c.high > highWaterMark) highWaterMark = c.high
    if (c.low < lowWaterMark) lowWaterMark = c.low

    // ── TRAILING STOP-LOSS (ATR-based, only moves in favorable direction) ──
    // v6: Wider trail multipliers to avoid premature SL hits on normal volatility
    // Phase 1 (initial): 2x ATR — give the trade room to breathe
    // Phase 2 (in profit by 1x ATR): 1.5x ATR — start protecting gains
    // Phase 3 (in profit by 2x ATR): 1.2x ATR — lock in profit aggressively
    if (direction === 'long') {
      const profitATRs = (highWaterMark - entry) / entryATR
      const trailMultiplier = profitATRs >= 2.0 ? 1.2 : profitATRs >= 1.0 ? 1.5 : 2.0
      const trailedSL = highWaterMark - currentATR * trailMultiplier
      if (trailedSL > currentSL) currentSL = trailedSL  // only move UP

      // Dynamic target: extend if trend is strong and price is near target
      if (c.close > currentTarget - currentATR * 0.5) {
        const momentum = stData.direction[i] === 1 && ema20[i] > ema50[i]
        if (momentum) {
          currentTarget = c.close + currentATR * 2.0  // extend target
        }
      }
    } else {
      const profitATRs = (entry - lowWaterMark) / entryATR
      const trailMultiplier = profitATRs >= 2.0 ? 1.2 : profitATRs >= 1.0 ? 1.5 : 2.0
      const trailedSL = lowWaterMark + currentATR * trailMultiplier
      if (trailedSL < currentSL) currentSL = trailedSL  // only move DOWN

      if (c.close < currentTarget + currentATR * 0.5) {
        const momentum = stData.direction[i] === -1 && ema20[i] < ema50[i]
        if (momentum) {
          currentTarget = c.close - currentATR * 2.0
        }
      }
    }

    // ── v5/v6: HEIKIN ASHI TREND MONITORING ──
    // v6: Softened HA tightening — single flip is just a warning, not an immediate tighten.
    // Only tighten meaningfully on established HA trend against us (3+ candles).
    const ht = haTrend[i]
    if (ht) {
      // HA established trend against us (3+ consecutive) — tighten to 1.2x ATR trail
      if (direction === 'long' && ht.isEstablishedBear) {
        const tighterSL = highWaterMark - currentATR * 1.2
        if (tighterSL > currentSL) currentSL = tighterSL
      }
      if (direction === 'short' && ht.isEstablishedBull) {
        const tighterSL = lowWaterMark + currentATR * 1.2
        if (tighterSL < currentSL) currentSL = tighterSL
      }
    }

    // ── INDICATOR-BASED STOP TIGHTENING ──
    // If indicators flip against the trade, tighten SL aggressively
    let indicatorsAgainst = 0
    // SuperTrend flip
    if (direction === 'long' && stData.direction[i] === -1) indicatorsAgainst++
    if (direction === 'short' && stData.direction[i] === 1) indicatorsAgainst++
    // MACD cross against
    if (direction === 'long' && macdData.macdLine[i] < macdData.signalLine[i]) indicatorsAgainst++
    if (direction === 'short' && macdData.macdLine[i] > macdData.signalLine[i]) indicatorsAgainst++
    // RSI extreme against
    if (direction === 'long' && rsiValues[i] !== null && rsiValues[i] > 75) indicatorsAgainst++
    if (direction === 'short' && rsiValues[i] !== null && rsiValues[i] < 25) indicatorsAgainst++
    // v5: HA trend against counts as an indicator
    if (direction === 'long' && ht && ht.isEstablishedBear) indicatorsAgainst++
    if (direction === 'short' && ht && ht.isEstablishedBull) indicatorsAgainst++

    if (indicatorsAgainst >= 2) {
      indicatorWarnings++
      // After 2+ candles of indicator disagreement, tighten SL to breakeven or better
      if (indicatorWarnings >= 2) {
        if (direction === 'long') {
          const tightSL = Math.max(currentSL, entry)  // at least breakeven
          currentSL = tightSL
        } else {
          const tightSL = Math.min(currentSL, entry)
          currentSL = tightSL
        }
      }
      // After 3+ candles of indicator disagreement with SuperTrend flipped, force exit
      if (indicatorWarnings >= 3 && (
        (direction === 'long' && stData.direction[i] === -1) ||
        (direction === 'short' && stData.direction[i] === 1)
      )) {
        exitIdx = i
        exitPrice = c.close
        exitReason = 'INDICATOR_FLIP'
        break
      }
    } else {
      indicatorWarnings = Math.max(0, indicatorWarnings - 1)  // decay warnings
    }

    // Store current zone for chart display
    tradeZones.push({
      time: c.time,
      sl: Math.round(currentSL * 100) / 100,
      target: Math.round(currentTarget * 100) / 100,
    })

    // ── CHECK EXIT CONDITIONS ──
    if (direction === 'long') {
      // SL hit: use low price (intracandle SL trigger)
      if (c.low <= currentSL) {
        exitIdx = i
        exitPrice = currentSL  // assume filled at SL level
        exitReason = 'STOP_LOSS'
        break
      }
      // Target hit: use high price
      if (c.high >= currentTarget) {
        exitIdx = i
        exitPrice = currentTarget
        exitReason = 'TARGET'
        break
      }
    } else {
      if (c.high >= currentSL) {
        exitIdx = i
        exitPrice = currentSL
        exitReason = 'STOP_LOSS'
        break
      }
      if (c.low <= currentTarget) {
        exitIdx = i
        exitPrice = currentTarget
        exitReason = 'TARGET'
        break
      }
    }
  }

  return { exitIdx, exitReason, exitPrice, entry, tradeZones }
}

// ─── CONFLUENCE SIGNAL ENGINE (v7) ──────────────────────────────────
// v7: DECOUPLED architecture. Signal generation and trade lifecycle are
// now two SEPARATE passes:
//   Pass 1: Generate ALL buy/sell signals based purely on indicator confluence
//   Pass 2: Run trade lifecycle simulation over those signals (informational overlay)
// This ensures signals are never suppressed by active trades — the user always
// sees every entry/exit opportunity on the chart.

export function computeChartSignals(candles, interval = '5m') {
  if (!candles || candles.length < 30) {
    return { markers: [], levels: [], tpSlBoxes: [], trendLine: [], rsiValues: [], pivots: [], ema20Line: [], ema50Line: [], macdChartData: [], activeTradeZone: null, tradeHistory: [] }
  }

  // v9: Spacing-only density control — NO maxSignals cap.
  // The cap was causing signals to run out in recent days because all slots
  // were consumed early in the data range. Spacing alone controls density:
  // - 1m: 30 candles = 30 min between signals
  // - 5m: 8 candles = 40 min between signals
  // - 15m: 15 candles = ~4 hours between signals
  const intervalConfig = {
    '1m':  { minSpacing: 30, confluenceThreshold: 3.5, strongThreshold: 5   },
    '5m':  { minSpacing: 8,  confluenceThreshold: 3,   strongThreshold: 4.5 },
    '15m': { minSpacing: 15, confluenceThreshold: 3.5, strongThreshold: 5   },
  }
  const cfg = intervalConfig[interval] || intervalConfig['5m']

  const closes = candles.map(c => c.close)
  const rsiValues = rsi(closes, 14)
  const macdData = macd(closes, 12, 26, 9)
  const stData = superTrend(candles, 7, 3)
  const srLevels = supportResistance(candles)
  const atrValues = atr(candles, 14)
  const haData = heikinAshi(candles)  // v5: Heikin Ashi trend filter

  // EMA 20 and 50 for trend confirmation
  const ema20 = ema(closes, 20)
  const ema50 = ema(closes, 50)

  // ═══════════════════════════════════════════════════════════════════
  // PASS 1: SIGNAL GENERATION (independent — no trade state dependency)
  // ═══════════════════════════════════════════════════════════════════
  const signals = []  // raw signals with index, direction, confidence
  let lastSignalIdx = -10

  for (let i = Math.max(50, 30); i < candles.length; i++) {
    let bullSignals = 0
    let bearSignals = 0

    const trend = trendStrength(candles, i, 30)

    // 1. SuperTrend direction (v6: reward ongoing direction, not just flip)
    if (stData.direction[i] === 1 && stData.direction[i - 1] === -1) bullSignals += 2
    else if (stData.direction[i] === 1) bullSignals += 0.5
    if (stData.direction[i] === -1 && stData.direction[i - 1] === 1) bearSignals += 2
    else if (stData.direction[i] === -1) bearSignals += 0.5

    // 2. RSI conditions + momentum
    if (rsiValues[i] !== null) {
      if (rsiValues[i] < 35 && !trend.isStrongDown) bullSignals += 1
      if (rsiValues[i] > 65 && !trend.isStrongUp) bearSignals += 1

      if (rsiValues[i] > 30 && rsiValues[i - 1] !== null && rsiValues[i - 1] < 30 && !trend.isStrongDown) bullSignals += 1
      if (rsiValues[i] < 70 && rsiValues[i - 1] !== null && rsiValues[i - 1] > 70 && !trend.isStrongUp) bearSignals += 1

      // v6: RSI momentum — helps detect trend shifts
      if (i >= 5 && rsiValues[i - 5] !== null) {
        if (rsiValues[i] < rsiValues[i - 5] - 15 && rsiValues[i] < 50) bearSignals += 0.5
        if (rsiValues[i] > rsiValues[i - 5] + 15 && rsiValues[i] > 50) bullSignals += 0.5
      }
    }

    // 3. MACD crossover + position
    if (macdData.macdLine[i] > macdData.signalLine[i] && macdData.macdLine[i - 1] <= macdData.signalLine[i - 1]) bullSignals += 1
    if (macdData.macdLine[i] < macdData.signalLine[i] && macdData.macdLine[i - 1] >= macdData.signalLine[i - 1]) bearSignals += 1
    if (macdData.macdLine[i] < 0 && macdData.signalLine[i] < 0) bearSignals += 0.5
    if (macdData.macdLine[i] > 0 && macdData.signalLine[i] > 0) bullSignals += 0.5

    // 4. EMA trend alignment + crossover
    if (ema20[i] > ema50[i]) bullSignals += 0.5
    if (ema20[i] < ema50[i]) bearSignals += 0.5
    if (i > 0) {
      if (ema20[i] < ema50[i] && ema20[i - 1] >= ema50[i - 1]) bearSignals += 1
      if (ema20[i] > ema50[i] && ema20[i - 1] <= ema50[i - 1]) bullSignals += 1
    }
    if (candles[i].close < ema20[i] && candles[i].close < ema50[i]) bearSignals += 0.5
    if (candles[i].close > ema20[i] && candles[i].close > ema50[i]) bullSignals += 0.5

    // 5. Volume confirmation
    const vol = volumeAnalysis(candles.slice(0, i + 1), 20)
    if (vol.aboveAvg) {
      if (candles[i].close > candles[i].open) bullSignals += 0.5
      else bearSignals += 0.5
    }

    // 6. Trend momentum bonus
    if (trend.isStrongDown) bearSignals += 1
    if (trend.isStrongUp) bullSignals += 1
    if (trend.isCrash) bearSignals += 1.5
    if (trend.isRally) bullSignals += 1.5

    // 7. Panic detection
    if (trend.isPanic) {
      bearSignals += 1
      bullSignals -= 1
    }

    // 8. Heikin Ashi trend filter
    const haTrend = haData.trend[i]
    if (haTrend) {
      if (haTrend.isEstablishedBull) bullSignals += 1
      if (haTrend.isEstablishedBear) bearSignals += 1
      if (haTrend.isStrongBullish) bullSignals += 0.5
      if (haTrend.isStrongBearish) bearSignals += 0.5
      if (haTrend.colorFlipToBull) bullSignals += 1
      if (haTrend.colorFlipToBear) bearSignals += 1
      if (haTrend.isIndecision) {
        bullSignals -= 0.5
        bearSignals -= 0.5
      }
    }

    // ── CONFLUENCE CHECK (v7: net-score based) ───────────────────
    const netBull = bullSignals - bearSignals
    const netBear = bearSignals - bullSignals
    let isBuy = bullSignals >= cfg.confluenceThreshold && netBull >= 1.5
    let isSell = bearSignals >= cfg.confluenceThreshold && netBear >= 1.5

    // Trend safety gates
    if (trend.isCrash && isBuy) isBuy = false
    if (trend.isRally && isSell) isSell = false
    if (trend.isPanic && isBuy) isBuy = false

    // HA trend gate
    if (haTrend && haTrend.isEstablishedBear && isBuy) isBuy = false
    if (haTrend && haTrend.isEstablishedBull && isSell) isSell = false

    if (isBuy || isSell) {
      if (i - lastSignalIdx < cfg.minSpacing) continue
      // v9: No maxSignals cap — spacing alone controls density
      lastSignalIdx = i

      signals.push({
        idx: i,
        isBuy,
        isSell,
        confidence: isBuy ? bullSignals : bearSignals,
        isStrong: (isBuy ? bullSignals : bearSignals) >= cfg.strongThreshold,
        direction: isBuy ? 'long' : 'short',
      })
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  // PASS 2: BUILD MARKERS + TRADE LIFECYCLE (informational overlay)
  // ═══════════════════════════════════════════════════════════════════
  const markers = []
  const tpSlBoxes = []
  const tradeHistory = []
  let allTradeZones = []
  let activeTradeZone = null

  for (let s = 0; s < signals.length; s++) {
    const sig = signals[s]
    const i = sig.idx
    const currentATR = atrValues[i] || (candles[i].high - candles[i].low)

    const entrySL = sig.isBuy
      ? Math.round((candles[i].close - currentATR * 2.0) * 100) / 100
      : Math.round((candles[i].close + currentATR * 2.0) * 100) / 100
    const entryTarget = sig.isBuy
      ? Math.round((candles[i].close + currentATR * 3.0) * 100) / 100
      : Math.round((candles[i].close - currentATR * 3.0) * 100) / 100

    // v9: Clear entry labels — "BUY ▲" = enter long, "SELL ▼" = enter short
    // Paired with exit markers (SL/TP/EXIT) to show complete trade lifecycle
    markers.push({
      time: candles[i].time,
      position: sig.isBuy ? 'belowBar' : 'aboveBar',
      color: sig.isBuy ? '#22c55e' : '#ef4444',
      shape: sig.isBuy ? 'arrowUp' : 'arrowDown',
      text: sig.isBuy
        ? (sig.isStrong ? 'STRONG BUY ▲' : 'BUY ▲')
        : (sig.isStrong ? 'STRONG SELL ▼' : 'SELL ▼'),
      size: 2,
    })

    tpSlBoxes.push({
      time: candles[i].time,
      entry: candles[i].close,
      tp: entryTarget,
      sl: entrySL,
      direction: sig.direction,
    })

    // ── Trade lifecycle: track from this signal to the NEXT signal or data end ──
    const nextSignalIdx = (s + 1 < signals.length) ? signals[s + 1].idx : candles.length
    const tradeResult = manageTradeLifecycle(
      candles, i, sig.direction, atrValues, stData, macdData, rsiValues, ema20, ema50, haData.trend,
      nextSignalIdx
    )

    if (tradeResult.tradeZones.length > 0) {
      allTradeZones.push({
        entryTime: candles[i].time,
        entryPrice: candles[i].close,
        direction: sig.direction,
        zones: tradeResult.tradeZones,
      })
    }

    // v8: Determine exit — either from lifecycle (SL/target/flip) or at boundary
    let exitIdx = tradeResult.exitIdx
    let exitPrice = tradeResult.exitPrice
    let exitReason = tradeResult.exitReason

    // If trade reached next signal without SL/target/flip, close at boundary price
    if (exitIdx === null && s + 1 < signals.length) {
      exitIdx = nextSignalIdx - 1  // close on the candle before next signal
      exitPrice = candles[exitIdx].close
      exitReason = 'NEXT_SIGNAL'
    }

    if (exitIdx !== null) {
      const pnl = sig.direction === 'long'
        ? exitPrice - tradeResult.entry
        : tradeResult.entry - exitPrice
      const pnlPct = ((pnl / tradeResult.entry) * 100).toFixed(2)
      const isProfit = pnl > 0

      // v8: Short exit labels
      let exitLabel = ''
      if (exitReason === 'STOP_LOSS') {
        exitLabel = `SL ✕ ${pnlPct > 0 ? '+' : ''}${pnlPct}%`
      } else if (exitReason === 'TARGET') {
        exitLabel = `TP ✓ +${pnlPct}%`
      } else if (exitReason === 'INDICATOR_FLIP') {
        exitLabel = `FLIP ${pnlPct > 0 ? '+' : ''}${pnlPct}%`
      } else if (exitReason === 'NEXT_SIGNAL') {
        exitLabel = `EXIT ${pnlPct > 0 ? '+' : ''}${pnlPct}%`
      }

      markers.push({
        time: candles[exitIdx].time,
        position: sig.direction === 'long' ? 'aboveBar' : 'belowBar',
        color: isProfit ? '#22d3ee' : '#f97316',
        shape: isProfit ? 'circle' : 'square',
        text: exitLabel,
        size: 1,  // v8: smaller exit markers to reduce clutter
      })

      tradeHistory.push({
        entryTime: candles[i].time,
        exitTime: candles[exitIdx].time,
        direction: sig.direction,
        entry: tradeResult.entry,
        exit: exitPrice,
        pnl: Math.round(pnl * 100) / 100,
        pnlPct: parseFloat(pnlPct),
        reason: exitReason,
      })
    } else {
      // Last signal with no exit = active trade
      activeTradeZone = {
        entryTime: candles[i].time,
        entryPrice: candles[i].close,
        direction: sig.direction,
        zones: tradeResult.tradeZones,
        currentSL: tradeResult.tradeZones.length > 0
          ? tradeResult.tradeZones[tradeResult.tradeZones.length - 1].sl
          : entrySL,
        currentTarget: tradeResult.tradeZones.length > 0
          ? tradeResult.tradeZones[tradeResult.tradeZones.length - 1].target
          : entryTarget,
      }
    }
  }

  // Sort markers by time (entry + exit markers may be interleaved)
  markers.sort((a, b) => a.time - b.time)

  // ═══════════════════════════════════════════════════════════════════
  // PASS 3: CHART OVERLAYS (unchanged)
  // ═══════════════════════════════════════════════════════════════════

  // Build SuperTrend line data for chart overlay
  const trendLine = candles.map((c, i) => {
    if (stData.supertrend[i] === null) return null
    return {
      time: c.time,
      value: Math.round(stData.supertrend[i] * 100) / 100,
      color: stData.direction[i] === 1 ? '#22c55e' : '#ef4444',
    }
  }).filter(Boolean)

  const pivots = computePivots(candles)

  const ema20Line = candles.map((c, i) => i >= 20 ? { time: c.time, value: Math.round(ema20[i] * 100) / 100 } : null).filter(Boolean)
  const ema50Line = candles.map((c, i) => i >= 50 ? { time: c.time, value: Math.round(ema50[i] * 100) / 100 } : null).filter(Boolean)

  const macdChartData = candles.map((c, i) => {
    if (i < 26) return null
    return {
      time: c.time,
      macd: Math.round(macdData.macdLine[i] * 100) / 100,
      signal: Math.round(macdData.signalLine[i] * 100) / 100,
      histogram: Math.round(macdData.histogram[i] * 100) / 100,
    }
  }).filter(Boolean)

  // Trade performance stats
  const totalTrades = tradeHistory.length + (activeTradeZone ? 1 : 0)
  const wins = tradeHistory.filter(t => t.pnl > 0).length
  const losses = tradeHistory.filter(t => t.pnl <= 0).length
  const totalPnlPts = tradeHistory.reduce((s, t) => s + t.pnl, 0)
  const tradeStats = {
    totalTrades,
    completedTrades: tradeHistory.length,
    wins,
    losses,
    winRate: tradeHistory.length > 0 ? Math.round((wins / tradeHistory.length) * 100) : 0,
    totalPnlPts: Math.round(totalPnlPts * 100) / 100,
    hasActiveTrade: !!activeTradeZone,
  }

  // HA trend for current candle
  const lastHA = haData.trend[candles.length - 1]
  const haTrendStatus = lastHA ? {
    isBullish: lastHA.isBullish,
    isStrong: lastHA.isStrongBullish || lastHA.isStrongBearish,
    consecutive: lastHA.isBullish ? lastHA.consecutiveBull : lastHA.consecutiveBear,
    isEstablished: lastHA.isEstablishedBull || lastHA.isEstablishedBear,
    colorFlip: lastHA.colorFlipToBull || lastHA.colorFlipToBear,
    isIndecision: lastHA.isIndecision,
  } : null

  return { markers, levels: srLevels, tpSlBoxes, trendLine, rsiValues, pivots, ema20Line, ema50Line, macdChartData, activeTradeZone, tradeHistory, allTradeZones, tradeStats, haTrendStatus }
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
