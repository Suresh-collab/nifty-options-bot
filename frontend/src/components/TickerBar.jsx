import { useEffect, useState } from 'react'

const INDICES = [
  { symbol: '^NSEI', label: 'NIFTY 50' },
  { symbol: '^BSESN', label: 'SENSEX' },
  { symbol: '^NSEBANK', label: 'BANKNIFTY' },
  { symbol: '^CNXFIN', label: 'FINNIFTY' },
  { symbol: 'USDINR=X', label: 'USD/INR' },
]

export default function TickerBar() {
  const [quotes, setQuotes] = useState([])

  useEffect(() => {
    async function fetchQuotes() {
      const results = []
      for (const idx of INDICES) {
        try {
          const urls = [
            `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(idx.symbol)}?interval=1d&range=2d`,
            `/yf-proxy/v8/finance/chart/${encodeURIComponent(idx.symbol)}?interval=1d&range=2d`,
          ]
          for (const url of urls) {
            try {
              const res = await fetch(url)
              if (!res.ok) continue
              const json = await res.json()
              const result = json.chart?.result?.[0]
              if (!result) continue
              const meta = result.meta
              const price = meta.regularMarketPrice
              const prevClose = meta.chartPreviousClose || meta.previousClose
              const change = price - prevClose
              const changePct = (change / prevClose) * 100
              results.push({
                label: idx.label,
                price: price.toFixed(2),
                change: change.toFixed(2),
                changePct: changePct.toFixed(2),
                isUp: change >= 0,
              })
              break
            } catch {}
          }
        } catch {}
      }
      setQuotes(results)
    }

    fetchQuotes()
    const iv = setInterval(fetchQuotes, 30000) // refresh every 30s
    return () => clearInterval(iv)
  }, [])

  if (quotes.length === 0) return null

  return (
    <div className="bg-[#0f172a] border-b border-[#1e293b] overflow-hidden">
      <div className="flex items-center gap-6 px-4 py-1.5 animate-marquee whitespace-nowrap">
        {quotes.map((q, i) => (
          <div key={i} className="flex items-center gap-2 text-xs font-mono shrink-0">
            <span className="text-[#94a3b8] font-medium">{q.label}</span>
            <span className="text-white">{Number(q.price).toLocaleString('en-IN')}</span>
            <span className={q.isUp ? 'text-terminal-green' : 'text-terminal-red'}>
              {q.isUp ? '+' : ''}{q.change} ({q.isUp ? '+' : ''}{q.changePct}%)
            </span>
          </div>
        ))}
        {/* Duplicate for seamless scroll */}
        {quotes.map((q, i) => (
          <div key={`dup-${i}`} className="flex items-center gap-2 text-xs font-mono shrink-0">
            <span className="text-[#94a3b8] font-medium">{q.label}</span>
            <span className="text-white">{Number(q.price).toLocaleString('en-IN')}</span>
            <span className={q.isUp ? 'text-terminal-green' : 'text-terminal-red'}>
              {q.isUp ? '+' : ''}{q.change} ({q.isUp ? '+' : ''}{q.changePct}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
