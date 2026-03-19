import { useState, useEffect, useCallback } from 'react'
import { fetchMarketNews, computeMarketMood } from '../lib/newsService'

const SENTIMENT_CONFIG = {
  bullish: { label: 'BULLISH', color: 'text-terminal-green', bg: 'bg-terminal-green/10', border: 'border-terminal-green/30' },
  bearish: { label: 'BEARISH', color: 'text-terminal-red', bg: 'bg-terminal-red/10', border: 'border-terminal-red/30' },
  neutral: { label: 'NEUTRAL', color: 'text-terminal-dim', bg: 'bg-terminal-muted/20', border: 'border-terminal-border' },
}

const FACTOR_LABELS = {
  oil: { label: 'OIL', color: 'text-orange-400' },
  fii: { label: 'FII/DII', color: 'text-terminal-blue' },
  rupee: { label: 'INR', color: 'text-terminal-amber' },
  us_market: { label: 'US MKT', color: 'text-purple-400' },
  global: { label: 'GLOBAL', color: 'text-cyan-400' },
  rbi: { label: 'RBI', color: 'text-terminal-green' },
}

function MoodMeter({ mood }) {
  const moodConfig = {
    bullish: { emoji: '▲', color: 'text-terminal-green', barColor: 'bg-terminal-green', label: 'BULLISH' },
    bearish: { emoji: '▼', color: 'text-terminal-red', barColor: 'bg-terminal-red', label: 'BEARISH' },
    neutral: { emoji: '—', color: 'text-terminal-amber', barColor: 'bg-terminal-amber', label: 'MIXED' },
  }
  const cfg = moodConfig[mood.mood] || moodConfig.neutral

  const bullPct = mood.total > 0 ? Math.round((mood.bullish / mood.total) * 100) : 0
  const bearPct = mood.total > 0 ? Math.round((mood.bearish / mood.total) * 100) : 0

  return (
    <div className="flex items-center gap-3 px-3 py-2 bg-terminal-bg/60 rounded border border-terminal-border">
      <span className={`text-lg font-mono font-bold ${cfg.color}`}>{cfg.emoji}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className={`text-xs font-mono font-bold ${cfg.color}`}>MARKET MOOD: {cfg.label}</span>
          <span className="text-xs font-mono text-terminal-dim">
            {mood.bullish}B / {mood.bearish}Be / {mood.neutral}N
          </span>
        </div>
        <div className="h-1.5 bg-terminal-muted rounded-full overflow-hidden flex">
          {bullPct > 0 && <div className="h-full bg-terminal-green" style={{ width: `${bullPct}%` }} />}
          {bearPct > 0 && <div className="h-full bg-terminal-red" style={{ width: `${bearPct}%` }} />}
        </div>
      </div>
    </div>
  )
}

function NewsItem({ item }) {
  const cfg = SENTIMENT_CONFIG[item.sentiment] || SENTIMENT_CONFIG.neutral
  const timeAgo = getTimeAgo(item.pubDate)

  return (
    <a
      href={item.link}
      target="_blank"
      rel="noopener noreferrer"
      className="block px-3 py-2.5 hover:bg-terminal-bg/40 transition-colors border-b border-terminal-border/50 last:border-0"
    >
      <div className="flex items-start gap-2">
        <span className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border ${cfg.bg} ${cfg.border} ${cfg.color}`}>
          {cfg.label}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-mono text-terminal-text leading-snug line-clamp-2">{item.title}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="text-[10px] font-mono text-terminal-dim">{item.source}</span>
            <span className="text-[10px] font-mono text-terminal-dim">{timeAgo}</span>
            {item.factors.map(f => {
              const fc = FACTOR_LABELS[f]
              return fc ? (
                <span key={f} className={`text-[10px] font-mono font-bold ${fc.color}`}>
                  {fc.label}
                </span>
              ) : null
            })}
          </div>
        </div>
      </div>
    </a>
  )
}

function getTimeAgo(date) {
  if (!date) return ''
  const now = new Date()
  const diffMs = now - date
  const mins = Math.floor(diffMs / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

export default function MarketNews() {
  const [news, setNews] = useState([])
  const [mood, setMood] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all') // all, bullish, bearish

  const loadNews = useCallback(async () => {
    try {
      setLoading(true)
      const items = await fetchMarketNews()
      setNews(items)
      setMood(computeMarketMood(items))
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadNews()
    // Refresh news every 5 minutes
    const iv = setInterval(loadNews, 5 * 60 * 1000)
    return () => clearInterval(iv)
  }, [loadNews])

  const filtered = filter === 'all' ? news : news.filter(n => n.sentiment === filter)

  return (
    <div className="bg-terminal-surface border border-terminal-border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-terminal-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold text-terminal-text uppercase tracking-widest">
            Market News
          </span>
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-terminal-blue opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-terminal-blue"></span>
          </span>
          <span className="text-[10px] font-mono text-terminal-dim">LIVE</span>
        </div>
        <div className="flex gap-1">
          {['all', 'bullish', 'bearish'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-0.5 text-[10px] font-mono rounded transition-colors uppercase ${
                filter === f
                  ? 'bg-terminal-blue text-white'
                  : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-border'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Mood meter */}
      {mood && (
        <div className="px-3 py-2 border-b border-terminal-border/50">
          <MoodMeter mood={mood} />
        </div>
      )}

      {/* News list */}
      <div className="max-h-[400px] overflow-y-auto">
        {loading && news.length === 0 && (
          <div className="p-6 text-center">
            <div className="text-xs font-mono text-terminal-dim animate-pulse">Loading market news...</div>
          </div>
        )}
        {error && news.length === 0 && (
          <div className="p-4 text-xs font-mono text-terminal-amber">
            News unavailable: {error}
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="p-6 text-center text-xs font-mono text-terminal-dim">
            No {filter !== 'all' ? filter : ''} news available
          </div>
        )}
        {filtered.map((item, idx) => (
          <NewsItem key={`${item.title.substring(0, 30)}-${idx}`} item={item} />
        ))}
      </div>

      {/* Footer */}
      <div className="px-3 py-1.5 border-t border-terminal-border/50 flex justify-between items-center">
        <span className="text-[10px] font-mono text-terminal-dim">
          {news.length} items from MoneyControl, ET Markets
        </span>
        <button
          onClick={loadNews}
          disabled={loading}
          className="text-[10px] font-mono text-terminal-blue hover:text-terminal-text disabled:opacity-50"
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>
    </div>
  )
}
