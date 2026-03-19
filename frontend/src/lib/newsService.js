/**
 * Market News Service
 * Fetches live news from Indian financial RSS feeds and applies sentiment analysis.
 * Uses free RSS-to-JSON services to avoid CORS issues.
 */

const RSS_FEEDS = [
  {
    name: 'MoneyControl Markets',
    url: 'https://www.moneycontrol.com/rss/marketreports.xml',
    category: 'markets',
  },
  {
    name: 'ET Markets',
    url: 'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
    category: 'markets',
  },
  {
    name: 'MoneyControl News',
    url: 'https://www.moneycontrol.com/rss/latestnews.xml',
    category: 'general',
  },
]

// Keywords for sentiment analysis on Indian market news
const BULLISH_KEYWORDS = [
  'rally', 'surge', 'gain', 'rise', 'bullish', 'up', 'high', 'record',
  'positive', 'boost', 'recovery', 'buying', 'fii inflow', 'dii buying',
  'breakout', 'support', 'accumulation', 'strong', 'outperform', 'upgrade',
  'rebound', 'green', 'optimism', 'bull run', 'new high', 'momentum',
]

const BEARISH_KEYWORDS = [
  'crash', 'fall', 'drop', 'decline', 'bearish', 'low', 'sell', 'selloff',
  'negative', 'correction', 'fii outflow', 'foreign selling', 'weakness',
  'breakdown', 'resistance', 'red', 'panic', 'fear', 'recession', 'slump',
  'oil surge', 'crude spike', 'rupee fall', 'inflation', 'rate hike',
  'tension', 'war', 'sanctions', 'volatility spike', 'vix spike',
]

// Key market-moving factors for Indian markets
const MARKET_FACTORS = {
  oil: ['oil', 'crude', 'brent', 'opec', 'petroleum', 'fuel', 'strait of hormuz'],
  fii: ['fii', 'foreign institutional', 'foreign investor', 'dii', 'domestic institutional'],
  rupee: ['rupee', 'inr', 'usd/inr', 'dollar', 'forex', 'currency'],
  us_market: ['dow', 'nasdaq', 's&p', 'wall street', 'fed', 'us market', 'us stock'],
  global: ['china', 'europe', 'asia', 'global cue', 'geopolitical', 'iran', 'trade war'],
  rbi: ['rbi', 'repo rate', 'monetary policy', 'interest rate', 'inflation'],
}

function analyzeSentiment(title, description = '') {
  const text = `${title} ${description}`.toLowerCase()

  let bullScore = 0
  let bearScore = 0

  for (const kw of BULLISH_KEYWORDS) {
    if (text.includes(kw)) bullScore++
  }
  for (const kw of BEARISH_KEYWORDS) {
    if (text.includes(kw)) bearScore++
  }

  if (bullScore > bearScore + 1) return 'bullish'
  if (bearScore > bullScore + 1) return 'bearish'
  if (bullScore > 0 || bearScore > 0) return bearScore > bullScore ? 'bearish' : 'bullish'
  return 'neutral'
}

function detectFactors(title, description = '') {
  const text = `${title} ${description}`.toLowerCase()
  const factors = []

  for (const [factor, keywords] of Object.entries(MARKET_FACTORS)) {
    for (const kw of keywords) {
      if (text.includes(kw)) {
        factors.push(factor)
        break
      }
    }
  }

  return factors
}

function parseRSSItems(xmlText, sourceName) {
  const parser = new DOMParser()
  const doc = parser.parseFromString(xmlText, 'text/xml')
  const items = doc.querySelectorAll('item')
  const results = []

  items.forEach((item, idx) => {
    if (idx >= 10) return // Limit to 10 per source
    const title = item.querySelector('title')?.textContent || ''
    const link = item.querySelector('link')?.textContent || ''
    const description = item.querySelector('description')?.textContent || ''
    const pubDate = item.querySelector('pubDate')?.textContent || ''

    const sentiment = analyzeSentiment(title, description)
    const factors = detectFactors(title, description)

    results.push({
      title: title.replace(/<[^>]*>/g, '').trim(),
      link,
      description: description.replace(/<[^>]*>/g, '').substring(0, 150).trim(),
      pubDate: pubDate ? new Date(pubDate) : new Date(),
      source: sourceName,
      sentiment,
      factors,
    })
  })

  return results
}

// RSS-to-JSON proxy services (free, no API key)
const CORS_PROXIES = [
  (url) => `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`,
  (url) => `https://corsproxy.io/?${encodeURIComponent(url)}`,
]

async function fetchRSSFeed(feed) {
  for (const proxy of CORS_PROXIES) {
    try {
      const res = await fetch(proxy(feed.url), { signal: AbortSignal.timeout(8000) })
      if (!res.ok) continue
      const text = await res.text()
      return parseRSSItems(text, feed.name)
    } catch {
      continue
    }
  }
  return []
}

/**
 * Fetch all market news from configured RSS feeds.
 * Returns sorted, deduplicated news items with sentiment and factor tags.
 */
export async function fetchMarketNews() {
  const results = await Promise.allSettled(
    RSS_FEEDS.map(feed => fetchRSSFeed(feed))
  )

  const allNews = results
    .filter(r => r.status === 'fulfilled')
    .flatMap(r => r.value)

  // Deduplicate by title similarity
  const seen = new Set()
  const unique = allNews.filter(item => {
    const key = item.title.substring(0, 50).toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })

  // Sort by date (newest first)
  unique.sort((a, b) => b.pubDate - a.pubDate)

  return unique.slice(0, 20) // Top 20 items
}

/**
 * Compute overall market sentiment from news items.
 */
export function computeMarketMood(newsItems) {
  if (!newsItems || newsItems.length === 0) return { mood: 'neutral', score: 0 }

  let bullish = 0, bearish = 0, neutral = 0
  for (const item of newsItems) {
    if (item.sentiment === 'bullish') bullish++
    else if (item.sentiment === 'bearish') bearish++
    else neutral++
  }

  const total = newsItems.length
  const score = Math.round(((bullish - bearish) / total) * 100)

  let mood = 'neutral'
  if (score > 20) mood = 'bullish'
  else if (score < -20) mood = 'bearish'

  return {
    mood,
    score,
    bullish,
    bearish,
    neutral,
    total,
  }
}
