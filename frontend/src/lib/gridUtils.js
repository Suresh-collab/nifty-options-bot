/**
 * Pure utility functions for multi-timeframe grid analysis.
 * Kept free of React/Zustand so every function is directly unit-testable.
 */

export const GRID_INTERVALS = ['1m', '5m', '15m', '1d']

export const IV_LABELS = { '1m': '1M', '5m': '5M', '15m': '15M', '1d': '1D' }

/**
 * Returns 'UP' if close is strictly above the SuperTrend line,
 * 'DOWN' if at or below it, or null when either value is missing.
 */
export function getTrendDirection(close, stValue) {
  if (stValue == null || close == null) return null
  return close > stValue ? 'UP' : 'DOWN'
}

/**
 * Computes multi-timeframe alignment from a gridSnapshot map.
 * gridSnapshot: { '1m': { close, st } | null, '5m': ..., '15m': ..., '1d': ... }
 *
 * Returns:
 *   directions — per-interval direction ('UP' | 'DOWN' | null)
 *   signal     — 'BUY' | 'SELL' | 'NEUTRAL' | null (null = no data at all)
 *   score      — 0-100 % of active charts agreeing with the dominant direction
 *   up / down  — count of UP / DOWN charts
 *   active     — number of charts that have valid data
 */
export function computeAlignment(gridSnapshot) {
  let up = 0, down = 0, active = 0
  const directions = {}

  for (const iv of GRID_INTERVALS) {
    const snap = gridSnapshot[iv]
    if (!snap || snap.close == null) {
      directions[iv] = null
      continue
    }
    const dir = getTrendDirection(snap.close, snap.st)
    directions[iv] = dir
    if (dir !== null) {
      active++
      if (dir === 'UP') up++
      else down++
    }
  }

  if (!active) return { directions, signal: null, score: 0, up: 0, down: 0, active: 0 }

  const dominant = Math.max(up, down)
  const score = Math.round((dominant / active) * 100)
  const signal = up === down ? 'NEUTRAL' : up > down ? 'BUY' : 'SELL'
  return { directions, signal, score, up, down, active }
}

/**
 * Formats a unix-seconds timestamp (already IST-shifted in this app) as "HH:MM".
 * Returns '--:--' for falsy input.
 */
export function formatISTTime(unixSecs) {
  if (!unixSecs) return '--:--'
  const d = new Date(unixSecs * 1000)
  const h = String(d.getUTCHours()).padStart(2, '0')
  const m = String(d.getUTCMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

/**
 * Returns true if any snapshot entry is a cursor-hover snapshot (not live/fallback).
 * Used by the info bar to decide whether to show OHLCV detail rows.
 */
export function hasCursorData(gridSnapshot) {
  return GRID_INTERVALS.some(iv => gridSnapshot[iv] && gridSnapshot[iv]._live === false)
}
