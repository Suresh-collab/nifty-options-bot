import { create } from 'zustand'
import { fetchOHLCV } from '../lib/yahooFetch'

// ── localStorage helpers ───────────────────────────────
const LS_TICKER = 'nob_ticker'
function lsGet(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback } catch { return fallback }
}
function lsSet(key, value) {
  try { localStorage.setItem(key, String(value)) } catch {}
}

export const useStore = create((set, get) => ({
  // ── Ticker ────────────────────────────────────────────
  ticker: lsGet(LS_TICKER, 'NIFTY'),
  setTicker: (t) => { lsSet(LS_TICKER, t); set({ ticker: t, signalData: null, optimizeData: null }) },

  // ── Cached OHLCV (shared between chart and signal) ───
  _cachedOHLCV: null,

  // ── Signal ────────────────────────────────────────────
  signalData: null,
  signalLoading: false,
  signalError: null,
  lastUpdated: null,

  fetchSignal: async () => {
    const { ticker } = get()
    set({ signalLoading: true, signalError: null })
    try {
      // Try server-side first (works on localhost), fall back to client-side fetch
      let res = await fetch(`/api/signal/${ticker}`)
      if (res.ok) {
        const data = await res.json()
        set({ signalData: data, signalLoading: false, lastUpdated: new Date() })
        return
      }

      // Server-side failed — fetch OHLCV client-side and compute on server
      const ohlcv = await fetchOHLCV(ticker, '5m')
      set({ _cachedOHLCV: ohlcv })

      res = await fetch('/api/compute-signal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, ohlcv }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      set({ signalData: data, signalLoading: false, lastUpdated: new Date() })
    } catch (e) {
      set({ signalError: e.message, signalLoading: false })
    }
  },

  // ── Optimize ──────────────────────────────────────────
  budget: '',
  setBudget: (b) => set({ budget: b }),
  optimizeData: null,
  optimizeLoading: false,
  optimizeError: null,

  fetchOptimize: async () => {
    const { ticker, budget } = get()
    if (!budget || isNaN(Number(budget))) return
    set({ optimizeLoading: true, optimizeError: null })
    try {
      // Try server-side first
      let res
      try {
        res = await fetch('/api/optimize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ticker, budget: Number(budget) }),
        })
        if (res.ok) {
          const data = await res.json()
          // Check if we got a valid result (not AVOID due to missing chain data)
          if (data?.plan?.recommendation !== 'AVOID' || data?.plan?.reason !== 'No option chain data.') {
            set({ optimizeData: data, optimizeLoading: false })
            return
          }
        }
      } catch {}

      // Fall back to client-side OHLCV + server compute
      let ohlcv = get()._cachedOHLCV
      if (!ohlcv) {
        ohlcv = await fetchOHLCV(ticker, '5m')
        set({ _cachedOHLCV: ohlcv })
      }

      res = await fetch('/api/compute-optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, budget: Number(budget), ohlcv }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      set({ optimizeData: data, optimizeLoading: false })
    } catch (e) {
      set({ optimizeError: e.message, optimizeLoading: false })
    }
  },

  // ── Market status ─────────────────────────────────────
  marketStatus: null,
  fetchMarketStatus: async () => {
    try {
      const res = await fetch('/api/market-status')
      const data = await res.json()
      set({ marketStatus: data })
    } catch {}
  },

  // ── Paper trades ──────────────────────────────────────
  tradeHistory: [],
  tradeStats: null,
  confirmTrade: null,
  setConfirmTrade: (t) => set({ confirmTrade: t }),

  enterPaperTrade: async (trade) => {
    const res = await fetch('/api/paper-trade/enter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(trade),
    })
    const data = await res.json()
    get().fetchTradeHistory()
    return data
  },

  exitPaperTrade: async (tradeId, exitLtp) => {
    const res = await fetch('/api/paper-trade/exit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trade_id: tradeId, exit_ltp: exitLtp }),
    })
    const data = await res.json()
    get().fetchTradeHistory()
    return data
  },

  fetchTradeHistory: async () => {
    try {
      const [histRes, statsRes] = await Promise.all([
        fetch('/api/paper-trade/history'),
        fetch('/api/paper-trade/stats'),
      ])
      const history = await histRes.json()
      const stats = await statsRes.json()
      set({ tradeHistory: history, tradeStats: stats })
    } catch {}
  },

  // ── Daily candle stats ────────────────────────────────────────────────
  dailyStats: null,
  dailyStatsLoading: false,

  fetchDailyStats: async () => {
    const { ticker } = get()
    set({ dailyStatsLoading: true })
    try {
      const res = await fetch(`/api/daily-stats/${ticker}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (Object.keys(data).length > 0) {
        set({ dailyStats: data, dailyStatsLoading: false })
        return
      }
      // Fallback: last 1D candle when intraday data isn't available (closed/weekend)
      const fallback = await fetch(`/api/chart/${ticker}?interval=1d`)
      if (fallback.ok) {
        const candles = await fallback.json()
        if (candles && candles.length > 0) {
          const last = candles[candles.length - 1]
          const prev = candles.length > 1 ? candles[candles.length - 2] : null
          const changePts = prev ? +(last.close - prev.close).toFixed(2) : null
          const changePct = prev ? +((last.close - prev.close) / prev.close * 100).toFixed(2) : null
          set({
            dailyStats: {
              ticker,
              _isFallback: true,
              day: { open: last.open, high: last.high, low: last.low, close: last.close,
                     prev_close: prev?.close ?? null, change_pts: changePts, change_pct: changePct },
            },
            dailyStatsLoading: false,
          })
          return
        }
      }
      set({ dailyStats: null, dailyStatsLoading: false })
    } catch {
      set({ dailyStatsLoading: false })
    }
  },

  // ── Phase 6: Analytics ───────────────────────────────────────────────
  analyticsData: null,
  analyticsLoading: false,

  fetchAnalytics: async () => {
    set({ analyticsLoading: true })
    try {
      const res = await fetch('/api/analytics/summary')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      set({ analyticsData: await res.json(), analyticsLoading: false })
    } catch {
      set({ analyticsLoading: false })
    }
  },

  // ── Phase 6: Scanner ─────────────────────────────────────────────────
  scannerData: null,
  scannerLoading: false,

  fetchScannerResults: async () => {
    set({ scannerLoading: true })
    try {
      const res = await fetch('/api/scanner/results')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      set({ scannerData: await res.json(), scannerLoading: false })
    } catch {
      set({ scannerLoading: false })
    }
  },

  runScanner: async () => {
    set({ scannerLoading: true })
    try {
      const res = await fetch('/api/scanner/run', { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      set({ scannerData: await res.json(), scannerLoading: false })
    } catch {
      set({ scannerLoading: false })
    }
  },

  // ── Phase 6: Admin ───────────────────────────────────────────────────
  adminFlags: null,
  adminFlagsLoading: false,
  auditLog: null,
  auditLogLoading: false,

  fetchAdminFlags: async () => {
    set({ adminFlagsLoading: true })
    try {
      const res = await fetch('/api/admin/flags')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      set({ adminFlags: data.flags, adminFlagsLoading: false })
    } catch {
      set({ adminFlagsLoading: false })
    }
  },

  toggleAdminFlag: async (name, enabled) => {
    set({ adminFlagsLoading: true })
    try {
      await fetch(`/api/admin/flags/${name}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      // Refresh flags after toggle
      const res = await fetch('/api/admin/flags')
      const data = await res.json()
      set({ adminFlags: data.flags, adminFlagsLoading: false })
    } catch {
      set({ adminFlagsLoading: false })
    }
  },

  fetchAuditLog: async (offset = 0, limit = 20) => {
    set({ auditLogLoading: true })
    try {
      const res = await fetch(`/api/admin/audit-log?limit=${limit}&offset=${offset}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      set({ auditLog: data.entries, auditLogLoading: false })
    } catch {
      set({ auditLogLoading: false })
    }
  },

  // ── Grid crosshair time sync ─────────────────────────────────────────
  // When hovering any compact (grid) chart, broadcast the cursor timestamp so
  // sibling charts can show a vertical line at the same wall-clock time.
  // { time, gen } — gen prevents the originating chart from echoing its own update.
  chartCrosshairTime: null,
  setChartCrosshairTime: (t) => set({ chartCrosshairTime: t }),

  // ── Grid snapshot — per-interval OHLCV + ST at the current cursor time ─
  // Each compact LiveChart writes its own entry keyed by interval ('1m' etc.).
  // _live: true  → last-bar data (always present after first chart load)
  // _live: false → cursor-hover data (overrides live while mouse is on chart)
  gridSnapshot: {},
  setGridSnapshot: (interval, snap) => set(state => ({
    gridSnapshot: { ...state.gridSnapshot, [interval]: snap },
  })),

  // ── Grid bookmarks — pinned timestamps shown on all compact charts ────
  // Toggled by clicking on any compact chart. Max 10 pins.
  gridBookmarks: [],
  toggleGridBookmark: (time) => set(state => {
    const TOLERANCE = 120  // 2-minute window for "same bookmark" matching
    const idx = state.gridBookmarks.findIndex(b => Math.abs(b.time - time) < TOLERANCE)
    if (idx >= 0) {
      return { gridBookmarks: state.gridBookmarks.filter((_, i) => i !== idx) }
    }
    if (state.gridBookmarks.length >= 10) return {}
    return { gridBookmarks: [...state.gridBookmarks, { time, id: `bm_${Date.now()}` }] }
  }),
}))
