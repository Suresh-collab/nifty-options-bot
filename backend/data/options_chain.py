import httpx
import json
from datetime import datetime, timedelta
import time

_cache: dict = {}
CACHE_TTL = 90  # seconds — NSE updates OI every ~1 min

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

NSE_OPTION_CHAIN_URLS = {
    "NIFTY":  "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
    "SENSEX": "https://www.nseindia.com/api/option-chain-indices?symbol=SENSEX",
}

def _cache_get(key):
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
    return None

def _cache_set(key, data):
    _cache[key] = (time.time(), data)

def get_next_expiry(ticker: str) -> datetime:
    """
    Nifty expires every Thursday, Sensex every Friday.
    Returns the next upcoming expiry datetime.
    """
    now = datetime.now()
    target_weekday = 3 if ticker.upper() == "NIFTY" else 4  # Thu=3, Fri=4
    days_ahead = (target_weekday - now.weekday()) % 7
    if days_ahead == 0 and now.hour >= 15:
        days_ahead = 7
    expiry = now + timedelta(days=days_ahead)
    return expiry.replace(hour=15, minute=30, second=0, microsecond=0)

def fetch_option_chain(ticker: str) -> dict:
    """
    Fetch raw option chain data from NSE.
    Returns parsed chain with strikes, OI, IV, LTP for CE and PE.
    """
    cache_key = f"chain_{ticker}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = NSE_OPTION_CHAIN_URLS.get(ticker.upper())
    if not url:
        raise ValueError(f"Unknown ticker: {ticker}")

    # NSE requires a session cookie — first hit the homepage
    with httpx.Client(headers=NSE_HEADERS, timeout=15, follow_redirects=True) as client:
        client.get("https://www.nseindia.com", timeout=10)
        resp = client.get(url, timeout=10)
        resp.raise_for_status()
        raw = resp.json()

    records = raw.get("records", {})
    data = records.get("data", [])
    expiry_dates = records.get("expiryDates", [])
    spot_price = records.get("underlyingValue", 0)

    # Parse first expiry only (nearest weekly)
    nearest_expiry = expiry_dates[0] if expiry_dates else None
    strikes = []

    for item in data:
        if item.get("expiryDate") != nearest_expiry:
            continue
        strike = item.get("strikePrice", 0)
        ce = item.get("CE", {})
        pe = item.get("PE", {})
        strikes.append({
            "strike":   strike,
            "ce_ltp":   ce.get("lastPrice", 0),
            "ce_oi":    ce.get("openInterest", 0),
            "ce_iv":    ce.get("impliedVolatility", 0),
            "ce_chg_oi": ce.get("changeinOpenInterest", 0),
            "pe_ltp":   pe.get("lastPrice", 0),
            "pe_oi":    pe.get("openInterest", 0),
            "pe_iv":    pe.get("impliedVolatility", 0),
            "pe_chg_oi": pe.get("changeinOpenInterest", 0),
        })

    total_ce_oi = sum(s["ce_oi"] for s in strikes)
    total_pe_oi = sum(s["pe_oi"] for s in strikes)
    pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 1.0

    # Max Pain: strike where total OTM payout is minimized
    max_pain = _calc_max_pain(strikes)

    result = {
        "ticker":        ticker,
        "spot":          spot_price,
        "expiry":        nearest_expiry,
        "pcr":           pcr,
        "max_pain":      max_pain,
        "total_ce_oi":   total_ce_oi,
        "total_pe_oi":   total_pe_oi,
        "strikes":       strikes,
        "fetched_at":    datetime.now().isoformat(),
    }

    _cache_set(cache_key, result)
    return result

def _calc_max_pain(strikes: list) -> float:
    """Calculates the max pain strike price."""
    if not strikes:
        return 0
    min_pain = float("inf")
    max_pain_strike = 0
    for candidate in strikes:
        s = candidate["strike"]
        pain = 0
        for row in strikes:
            k = row["strike"]
            if s > k:
                pain += (s - k) * row["ce_oi"]
            elif s < k:
                pain += (k - s) * row["pe_oi"]
        if pain < min_pain:
            min_pain = pain
            max_pain_strike = s
    return max_pain_strike

def get_atm_iv(chain: dict) -> float:
    """Returns the average IV at the ATM strike."""
    spot = chain["spot"]
    strikes = chain["strikes"]
    if not strikes:
        return 0
    atm = min(strikes, key=lambda x: abs(x["strike"] - spot))
    iv = (atm["ce_iv"] + atm["pe_iv"]) / 2
    return round(iv, 2)
