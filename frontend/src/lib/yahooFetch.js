const SYMBOLS = {
  NIFTY: '^NSEI',
  SENSEX: '^BSESN',
}

// IST offset: +5:30 = 19800 seconds
const IST_OFFSET_SECONDS = 19800

/**
 * Fetch OHLCV data from Yahoo Finance directly (client-side).
 * This avoids cloud IP blocking since the request comes from the user's browser.
 */
export async function fetchOHLCV(ticker, interval = '5m') {
  const symbol = SYMBOLS[ticker.toUpperCase()] || ticker
  const range = ['1m', '2m', '5m'].includes(interval) ? '5d' : '60d'

  // Try direct Yahoo Finance API first, fall back to proxy
  const urls = [
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${interval}&range=${range}`,
    `/yf-proxy/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${interval}&range=${range}`,
  ]

  let lastError = null
  for (const url of urls) {
    try {
      const res = await fetch(url)
      if (!res.ok) continue
      const json = await res.json()
      return parseYahooChart(json)
    } catch (e) {
      lastError = e
    }
  }

  throw lastError || new Error('Failed to fetch chart data')
}

function parseYahooChart(json) {
  const result = json.chart?.result?.[0]
  if (!result) throw new Error('No chart data in response')

  const timestamps = result.timestamp || []
  const quote = result.indicators?.quote?.[0] || {}

  const candles = []
  for (let i = 0; i < timestamps.length; i++) {
    const open = quote.open?.[i]
    const high = quote.high?.[i]
    const low = quote.low?.[i]
    const close = quote.close?.[i]
    const volume = quote.volume?.[i]

    // Skip null entries
    if (open == null || close == null) continue

    // Convert UTC timestamp to IST for lightweight-charts display
    // lightweight-charts treats timestamps as UTC, so we add IST offset
    const istTime = timestamps[i] + IST_OFFSET_SECONDS

    candles.push({
      time: istTime,
      open: Math.round(open * 100) / 100,
      high: Math.round(high * 100) / 100,
      low: Math.round(low * 100) / 100,
      close: Math.round(close * 100) / 100,
      volume: volume || 0,
    })
  }

  return candles
}
