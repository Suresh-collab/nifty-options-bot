import uuid
from typing import List
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, date, timezone
from data.market_data import get_ohlcv, get_spot_price, get_market_status, _fetch_nse_chart
from data.options_chain import fetch_option_chain, get_next_expiry, get_atm_iv, _fallback_chain
from indicators.engine import compute_indicators
from ai.signal_engine import generate_signal
from ai.budget_optimizer import optimize
from paper_trading.simulator import (
    enter_trade, exit_trade, get_history, get_stats
)

router = APIRouter()

# --- Request models ---
class OHLCVItem(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: int = 0

class ComputeSignalRequest(BaseModel):
    ticker: str
    ohlcv: List[OHLCVItem]

class ComputeOptimizeRequest(BaseModel):
    ticker: str
    budget: float
    ohlcv: List[OHLCVItem]

class OptimizeRequest(BaseModel):
    ticker: str
    budget: float

class PaperTradeEnterRequest(BaseModel):
    ticker: str
    strike: float
    direction: str
    entry_price: float
    lots: int
    lot_size: int
    signal: dict = {}

class PaperTradeExitRequest(BaseModel):
    trade_id: int
    exit_price: float


# --- Yahoo Finance proxy (avoids CORS for client-side chart fallback) ---
_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

@router.get("/yf-proxy")
async def yf_proxy(symbol: str, interval: str = "5m", range: str = "5d"):
    """Proxy Yahoo Finance API requests to avoid CORS issues."""
    allowed_intervals = {"1m", "2m", "5m", "15m", "1d"}
    if interval not in allowed_intervals:
        raise HTTPException(400, f"interval must be one of {allowed_intervals}")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={range}"
    try:
        async with httpx.AsyncClient(headers=_YF_HEADERS, timeout=10, follow_redirects=True) as client:
            resp = await client.get(url)
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except Exception as e:
        raise HTTPException(502, f"Yahoo Finance proxy failed: {str(e)}")


# --- Chart data ---
@router.get("/chart/{ticker}")
async def get_chart(ticker: str, interval: str = "5m"):
    ticker = ticker.upper()
    if ticker not in ("NIFTY", "SENSEX"):
        raise HTTPException(400, "ticker must be NIFTY or SENSEX")
    try:
        df = get_ohlcv(ticker, interval=interval)
        records = []
        for idx, row in df.iterrows():
            records.append({
                "time": int(idx.timestamp()),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return records
    except Exception as e:
        raise HTTPException(500, f"Chart data failed: {str(e)}")


# --- NSE Chart data (near real-time fallback) ---
@router.get("/nse-chart/{ticker}")
async def get_nse_chart(ticker: str, interval: str = "5m"):
    """Fetch intraday chart data from NSE India (near real-time, today only)."""
    ticker = ticker.upper()
    if ticker not in ("NIFTY", "SENSEX"):
        raise HTTPException(400, "ticker must be NIFTY or SENSEX")
    try:
        candles = _fetch_nse_chart(ticker, interval)
        if not candles:
            raise HTTPException(502, "NSE chart data unavailable")
        return candles
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"NSE chart fetch failed: {str(e)}")


# --- Market status ---
@router.get("/market-status")
async def market_status():
    return get_market_status()


# --- Full signal for a ticker ---
async def _ml_shadow(ticker: str, df: pd.DataFrame) -> dict:
    """
    Run ML inference in shadow mode — never raises, always returns a dict.
    Called after the rule-based signal so it never blocks the main response.
    Returns {} if no model is trained yet.
    """
    try:
        from config.feature_flags import is_enabled
        from ml.registry import load_model
        from ml.features import build_features
        from ml.model import predict as ml_predict

        # Only run for tickers with trained models
        db_symbol = "NIFTY" if ticker == "NIFTY" else "BANKNIFTY"

        regime_clf = await load_model("regime_classifier", db_symbol, "5m")
        direction_model = await load_model("direction_model", db_symbol, "5m")

        if regime_clf is None or direction_model is None:
            return {"status": "no_model", "message": "Run training script first"}

        feat = build_features(df)
        if feat.empty:
            return {"status": "no_features"}

        feat["regime"] = regime_clf.predict(df).reindex(feat.index).fillna(2)
        regime_label = regime_clf.predict_label(df).iloc[-1] if not df.empty else "UNKNOWN"

        direction, confidence = ml_predict(direction_model, feat)
        dir_map = {1: "BUY_CE", -1: "BUY_PE", 0: "AVOID"}

        return {
            "status":       "active" if is_enabled("ENABLE_ML_SIGNAL") else "shadow",
            "direction":    dir_map[direction],
            "confidence":   round(confidence, 3),
            "regime":       regime_label,
        }
    except ImportError:
        # scikit-learn / xgboost not installed in this environment (e.g. Vercel).
        # Return no_model so the frontend silently skips the ML panel.
        return {"status": "no_model", "message": "ML packages not available in this environment"}
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("ML shadow inference failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/signal/{ticker}")
async def get_signal(ticker: str):
    ticker = ticker.upper()
    if ticker not in ("NIFTY", "SENSEX"):
        raise HTTPException(400, "ticker must be NIFTY or SENSEX")
    try:
        df      = get_ohlcv(ticker, interval="5m")
        spot    = get_spot_price(ticker)
        chain   = fetch_option_chain(ticker, spot=spot)
        if chain.get("fallback") and not chain.get("strikes") and spot > 0:
            chain = _fallback_chain(ticker, spot)
        iv      = get_atm_iv(chain)
        indic   = compute_indicators(df, pcr=chain["pcr"], iv=iv)
        expiry  = chain.get("expiry", get_next_expiry(ticker).strftime("%d-%b-%Y"))
        signal  = generate_signal(ticker, spot, str(expiry), indic, chain)
        ml_info = await _ml_shadow(ticker, df)
        return {
            "ticker":     ticker,
            "spot":       spot,
            "indicators": indic,
            "chain_summary": {
                "pcr":      chain["pcr"],
                "max_pain": chain["max_pain"],
                "expiry":   expiry,
            },
            "signal": signal,
            "ml":     ml_info,
        }
    except Exception as e:
        raise HTTPException(500, f"Signal generation failed: {str(e)}")


# --- Budget optimizer ---
@router.post("/optimize")
async def optimize_budget(req: OptimizeRequest):
    ticker = req.ticker.upper()
    if ticker not in ("NIFTY", "SENSEX"):
        raise HTTPException(400, "ticker must be NIFTY or SENSEX")
    try:
        df     = get_ohlcv(ticker, interval="5m")
        spot   = get_spot_price(ticker)
        chain  = fetch_option_chain(ticker, spot=spot)
        # If NSE was unreachable and strikes are empty, regenerate with spot price
        if chain.get("fallback") and not chain.get("strikes") and spot > 0:
            chain = _fallback_chain(ticker, spot)
        iv     = get_atm_iv(chain)
        indic  = compute_indicators(df, pcr=chain["pcr"], iv=iv)
        expiry = chain.get("expiry", get_next_expiry(ticker).strftime("%d-%b-%Y"))
        signal = generate_signal(ticker, spot, str(expiry), indic, chain)
        plan   = optimize(req.budget, ticker, signal, chain)
        return {"signal": signal, "plan": plan}
    except Exception as e:
        raise HTTPException(500, f"Optimization failed: {str(e)}")


# --- Client-side data: compute signal from browser-fetched OHLCV ---
def _ohlcv_to_df(ohlcv: List[OHLCVItem]) -> pd.DataFrame:
    """Convert client-provided OHLCV list to a pandas DataFrame."""
    records = [{"Open": c.open, "High": c.high, "Low": c.low,
                "Close": c.close, "Volume": c.volume} for c in ohlcv]
    timestamps = [pd.Timestamp(c.time, unit="s") for c in ohlcv]
    return pd.DataFrame(records, index=timestamps)


@router.post("/compute-signal")
async def compute_signal(req: ComputeSignalRequest):
    """Compute signal from client-provided OHLCV data (avoids cloud IP blocking)."""
    ticker = req.ticker.upper()
    if ticker not in ("NIFTY", "SENSEX"):
        raise HTTPException(400, "ticker must be NIFTY or SENSEX")
    if len(req.ohlcv) < 20:
        raise HTTPException(400, "Need at least 20 candles for indicators")
    try:
        df = _ohlcv_to_df(req.ohlcv)
        spot = float(df["Close"].iloc[-1])
        chain = fetch_option_chain(ticker)
        # If NSE was unreachable and strikes are empty, regenerate with spot price
        if chain.get("fallback") and not chain.get("strikes") and spot > 0:
            chain = _fallback_chain(ticker, spot)
        iv = get_atm_iv(chain)
        indic = compute_indicators(df, pcr=chain["pcr"], iv=iv)
        expiry = chain.get("expiry", get_next_expiry(ticker).strftime("%d-%b-%Y"))
        signal = generate_signal(ticker, spot, str(expiry), indic, chain)
        return {
            "ticker": ticker,
            "spot": spot,
            "indicators": indic,
            "chain_summary": {
                "pcr": chain["pcr"],
                "max_pain": chain["max_pain"],
                "expiry": expiry,
            },
            "signal": signal,
        }
    except Exception as e:
        raise HTTPException(500, f"Signal computation failed: {str(e)}")


@router.post("/compute-optimize")
async def compute_optimize(req: ComputeOptimizeRequest):
    """Budget optimizer using client-provided OHLCV data."""
    ticker = req.ticker.upper()
    if ticker not in ("NIFTY", "SENSEX"):
        raise HTTPException(400, "ticker must be NIFTY or SENSEX")
    if len(req.ohlcv) < 20:
        raise HTTPException(400, "Need at least 20 candles for indicators")
    try:
        df = _ohlcv_to_df(req.ohlcv)
        spot = float(df["Close"].iloc[-1])
        chain = fetch_option_chain(ticker)
        # If NSE was unreachable and strikes are empty, regenerate with spot price
        if chain.get("fallback") and not chain.get("strikes") and spot > 0:
            chain = _fallback_chain(ticker, spot)
        iv = get_atm_iv(chain)
        indic = compute_indicators(df, pcr=chain["pcr"], iv=iv)
        expiry = chain.get("expiry", get_next_expiry(ticker).strftime("%d-%b-%Y"))
        signal = generate_signal(ticker, spot, str(expiry), indic, chain)
        plan = optimize(req.budget, ticker, signal, chain)
        return {"signal": signal, "plan": plan}
    except Exception as e:
        raise HTTPException(500, f"Optimization failed: {str(e)}")


# --- Paper trading ---
@router.post("/paper-trade/enter")
async def paper_enter(req: PaperTradeEnterRequest):
    return enter_trade(
        req.ticker, req.strike, req.direction,
        req.entry_price, req.lots, req.lot_size, req.signal
    )

@router.post("/paper-trade/exit")
async def paper_exit(req: PaperTradeExitRequest):
    return exit_trade(req.trade_id, req.exit_price)

@router.get("/paper-trade/history")
async def paper_history():
    return get_history()

@router.get("/paper-trade/stats")
async def paper_stats():
    return get_stats()


# --- Market News (server-side RSS fetch — no CORS issues) ---
_NEWS_FEEDS = [
    {"name": "MoneyControl Markets", "url": "https://www.moneycontrol.com/rss/marketreports.xml"},
    {"name": "ET Markets", "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"},
    {"name": "MoneyControl News", "url": "https://www.moneycontrol.com/rss/latestnews.xml"},
    {"name": "ET Stocks", "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"},
    {"name": "LiveMint Markets", "url": "https://www.livemint.com/rss/markets"},
]

_NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _parse_rss_items(xml_text: str, source_name: str) -> list:
    """Parse RSS XML and return news items."""
    items = []
    try:
        root = ET.fromstring(xml_text)
        # Handle both RSS 2.0 and Atom formats
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "")
            if not title:
                continue
            # Strip HTML tags from title and description
            import re
            title = re.sub(r'<[^>]+>', '', title).strip()
            desc = re.sub(r'<[^>]+>', '', desc)[:200].strip()
            items.append({
                "title": title,
                "link": link,
                "description": desc,
                "pubDate": pub_date,
                "source": source_name,
            })
            if len(items) >= 10:
                break
    except Exception:
        pass
    return items


@router.get("/news")
async def get_news():
    """Fetch market news from RSS feeds server-side (bypasses CORS)."""
    all_items = []
    async with httpx.AsyncClient(headers=_NEWS_HEADERS, timeout=8, follow_redirects=True) as client:
        for feed in _NEWS_FEEDS:
            try:
                resp = await client.get(feed["url"])
                if resp.status_code == 200:
                    items = _parse_rss_items(resp.text, feed["name"])
                    all_items.extend(items)
            except Exception:
                continue

    # Deduplicate by title prefix
    seen = set()
    unique = []
    for item in all_items:
        key = item["title"][:50].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # Sort by pubDate (newest first) — best effort parse
    def parse_date(s):
        try:
            return datetime.strptime(s.strip(), "%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            try:
                return datetime.strptime(s.strip(), "%a, %d %b %Y %H:%M:%S GMT")
            except Exception:
                return datetime.min

    unique.sort(key=lambda x: parse_date(x.get("pubDate", "")), reverse=True)
    return unique[:25]


# ---------------------------------------------------------------------------
# Backtesting endpoints (Phase 1)
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    symbol: str = "NIFTY"
    start_date: date
    end_date: date
    capital: float = 100_000.0
    sl_pct: float = 0.01
    tp_pct: float = 0.02


@router.post("/backtest")
async def create_backtest(req: BacktestRequest):
    """
    Run a backtest synchronously and return the full result.

    Runs inline (no background task) so it works on Vercel serverless where
    the execution context is frozen after the HTTP response is sent.
    The computation is fast: ~700 bars for 60 days of 5m data takes < 1 s.
    """
    from db.base import get_session_factory
    from data.ohlcv_loader import load_ohlcv
    from backtesting.engine import run_backtest, benchmark_buy_hold

    symbol = req.symbol.upper()
    if symbol not in ("NIFTY", "BANKNIFTY"):
        raise HTTPException(400, "symbol must be NIFTY or BANKNIFTY")
    if req.start_date >= req.end_date:
        raise HTTPException(400, "start_date must be before end_date")
    if req.capital <= 0:
        raise HTTPException(400, "capital must be positive")

    run_id = str(uuid.uuid4())
    start_dt = datetime.combine(req.start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(req.end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    try:
        factory = get_session_factory()
        async with factory() as session:
            df = await load_ohlcv(symbol, "5m", start_dt, end_dt, session)

        result = run_backtest(df, symbol, req.capital, req.sl_pct, req.tp_pct)
        result["benchmark"] = benchmark_buy_hold(df, req.capital)

        return {
            "id": run_id,
            "status": "COMPLETE",
            "symbol": symbol,
            "start_date": req.start_date.isoformat(),
            "end_date": req.end_date.isoformat(),
            "capital": req.capital,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }
    except Exception as exc:
        raise HTTPException(500, f"Backtest failed: {exc}")


# ---------------------------------------------------------------------------
# OHLCV data refresh (seed endpoint — call once to populate ohlcv_cache)
# ---------------------------------------------------------------------------

@router.post("/refresh-ohlcv")
async def refresh_ohlcv_endpoint():
    """
    Fetch latest OHLCV data from yfinance and upsert into ohlcv_cache.
    Call this once after deployment to seed the database.
    Returns a summary of rows inserted per symbol/interval.
    """
    from data.ohlcv_loader import refresh_ohlcv
    try:
        result = await refresh_ohlcv()
        return {"status": "ok", "summary": result["summary"], "errors": result.get("errors", {})}
    except Exception as exc:
        raise HTTPException(500, f"OHLCV refresh failed: {exc}")


# ---------------------------------------------------------------------------
# ML model status  (Phase 2)
# ---------------------------------------------------------------------------

@router.get("/ml/status")
async def ml_status():
    """
    Return metadata for the currently active ML models in model_registry.
    Used by the frontend to show whether models are trained and ready.
    """
    from ml.registry import list_models
    try:
        rows = await list_models()
        active = [r for r in rows if r.get("is_active")]
        return {
            "models": [
                {
                    "name":        r["name"],
                    "version":     r["version"],
                    "symbol":      r["symbol"],
                    "interval":    r["interval"],
                    "trained_at":  r["trained_at"].isoformat() if r["trained_at"] else None,
                    "train_start": r["train_start"],
                    "train_end":   r["train_end"],
                    "metrics":     r["metrics"] or {},
                    "is_active":   r["is_active"],
                }
                for r in active
            ],
            "total_versions": len(rows),
        }
    except Exception as exc:
        raise HTTPException(500, f"ML status failed: {exc}")


@router.post("/train")
async def train_endpoint():
    """
    Stub for Vercel — training must run locally.
    On a long-lived backend (Railway/Render) this would kick off the
    training script inline.
    """
    return {
        "status": "local_only",
        "message": (
            "Model training cannot run on Vercel serverless. "
            "Run locally: python backend/scripts/train.py"
        ),
    }
