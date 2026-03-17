import { create } from 'zustand'

export const useStore = create((set, get) => ({
  // ── Ticker ────────────────────────────────────────────
  ticker: 'NIFTY',
  setTicker: (t) => set({ ticker: t, signalData: null, optimizeData: null }),

  // ── Signal ────────────────────────────────────────────
  signalData: null,
  signalLoading: false,
  signalError: null,
  lastUpdated: null,

  fetchSignal: async () => {
    const { ticker } = get()
    set({ signalLoading: true, signalError: null })
    try {
      const res = await fetch(`/api/signal/${ticker}`)
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
      const res = await fetch('/api/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker, budget: Number(budget) }),
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
    const { ticker } = get()
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
}))
