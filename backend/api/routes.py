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

# ---------------------------------------------------------------------------
# Phase 3 — kill-switch state (in-memory; resets on server restart)
# When True: paper_enter is blocked; all open trades have been halted.
# ---------------------------------------------------------------------------
_kill_switch_active: bool = False


# ---------------------------------------------------------------------------
# Shadow-mode agreement tracking (in-memory; resets on server restart)
# Phase 2.6 observability — counts how often rule signal and ML signal agree.
# ---------------------------------------------------------------------------
_shadow_stats: dict = {
    "total": 0,
    "agree": 0,
    "disagree": 0,
    "rule_only": 0,
}


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
async def _load_onnx_artifact(name: str, symbol: str, interval: str = "5m"):
    """
    Load ONNX bytes + metadata. Tries disk first (fast, works on Vercel),
    falls back to Neon DB (for environments without committed model files).
    Returns (bytes, dict) or (None, None).
    """
    import json, os
    base = os.path.join(os.path.dirname(__file__), "..", "ml", "onnx_models")
    onnx_path = os.path.join(base, f"{name}_{symbol}.onnx")
    meta_path  = os.path.join(base, f"{name}_{symbol}.json")

    if os.path.exists(onnx_path):
        with open(onnx_path, "rb") as f:
            onnx_bytes = f.read()
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
        return onnx_bytes, meta

    # Fallback: load from Neon DB
    try:
        from db.base import get_session_factory
        from sqlalchemy import text as _text
        async with get_session_factory()() as session:
            row = await session.execute(
                _text(
                    "SELECT onnx_bytes, input_features FROM model_registry_onnx "
                    "WHERE name=:name AND symbol=:symbol AND interval=:interval "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"name": name, "symbol": symbol, "interval": interval},
            )
            result = row.fetchone()
        if result is None:
            return None, None
        return bytes(result[0]), (json.loads(result[1]) if result[1] else {})
    except Exception:
        return None, None


def _infer_regime_onnx(ort, np, onnx_bytes: bytes, meta: dict, df: pd.DataFrame):
    """Regime inference via ONNX — pure numpy, no sklearn. Returns (regime_int, label_str) or None."""
    c = df.get("c")
    if c is None or len(c) < 22:
        return None
    h, l = df["h"], df["l"]
    ret = c.pct_change()
    tr  = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()

    vol     = float(ret.rolling(20).std().iloc[-1])
    mom     = float(c.pct_change(5).iloc[-1])
    last_c  = float(c.iloc[-1])
    atr_pct = float(atr.iloc[-1]) / last_c if last_c != 0 else 0.0

    if any(pd.isna([vol, mom, atr_pct])):
        return None

    feats = np.array([[vol, mom, atr_pct]], dtype=np.float32)
    sess  = ort.InferenceSession(onnx_bytes)
    raw   = int(sess.run(None, {sess.get_inputs()[0].name: feats})[0][0])

    label_map = {int(k): int(v) for k, v in meta.get("label_map", {}).items()}
    stable    = label_map.get(raw, 2)
    labels    = {"0": "TRENDING_UP", "1": "TRENDING_DOWN", "2": "RANGING"}
    return stable, labels.get(str(stable), "UNKNOWN")


def _infer_direction_onnx(ort, np, onnx_bytes: bytes, feat: pd.DataFrame):
    """Direction inference via ONNX. Returns (direction_int, confidence)."""
    _FEAT_COLS = [
        "ret_1", "ret_5", "ret_15", "ret_30", "rsi",
        "macd_line", "macd_hist", "macd_cross", "supertrend_dir",
        "bb_pos", "bb_width", "atr_pct", "ema_cross", "vol_ratio",
        "time_sin", "time_cos", "dow_sin", "dow_cos", "regime",
    ]
    row     = feat.iloc[[-1]][[c for c in _FEAT_COLS if c in feat.columns]].values.astype(np.float32)
    sess    = ort.InferenceSession(onnx_bytes)
    outputs = sess.run(None, {sess.get_inputs()[0].name: row})

    # Pipeline outputs: [class_labels, probabilities_array]
    if len(outputs) > 1:
        probs  = outputs[1][0]
        prob_up = float(probs[1]) if len(probs) > 1 else float(probs[0])
    else:
        prob_up = float(outputs[0][0])

    if prob_up >= 0.55:
        return 1, prob_up
    elif prob_up <= 0.45:
        return -1, 1.0 - prob_up
    return 0, max(prob_up, 1.0 - prob_up)


async def _ml_shadow(ticker: str, df: pd.DataFrame) -> dict:
    """
    Run ML inference in shadow mode — never raises, always returns a dict.
    Tries ONNX path first (works on Vercel, onnxruntime ~15 MB).
    Falls back to sklearn path for local dev (sklearn + xgboost installed).
    """
    col_map   = {"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"}
    ml_df     = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    db_symbol = "NIFTY" if ticker in ("NIFTY", "SENSEX") else "BANKNIFTY"

    # ── ONNX PATH (Vercel + local when onnxruntime installed) ──────────────
    try:
        import onnxruntime as ort
        import numpy as np

        dir_bytes,    dir_meta    = await _load_onnx_artifact("direction_model",   db_symbol)
        regime_bytes, regime_meta = await _load_onnx_artifact("regime_classifier", db_symbol)

        if dir_bytes is None or regime_bytes is None:
            # onnxruntime is available but ONNX models haven't been exported yet.
            # Return no_model here — do NOT fall through to sklearn path on Vercel
            # since sklearn is not installed. Running export_onnx.py locally fixes this.
            return {"status": "no_model", "message": "Run export_onnx.py to enable ONNX inference"}

        regime_result = _infer_regime_onnx(ort, np, regime_bytes, regime_meta, ml_df)
        if regime_result is None:
            return {"status": "no_features"}
        stable_regime, regime_label = regime_result

        from ml.features import build_features
        feat = build_features(ml_df)
        if feat.empty:
            return {"status": "no_features"}
        feat["regime"] = stable_regime

        direction, confidence = _infer_direction_onnx(ort, np, dir_bytes, feat)
        dir_map = {1: "BUY_CE", -1: "BUY_PE", 0: "AVOID"}

        from config.feature_flags import is_enabled
        return {
            "status":     "active" if is_enabled("ENABLE_ML_SIGNAL") else "shadow",
            "source":     "onnx",
            "direction":  dir_map[direction],
            "confidence": round(confidence, 3),
            "regime":     regime_label,
        }
    except ImportError:
        pass  # onnxruntime not installed — fall through to sklearn
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("ONNX inference failed: %s", exc)
        # fall through to sklearn

    # ── SKLEARN PATH (local dev — sklearn + xgboost installed) ─────────────
    try:
        from config.feature_flags import is_enabled
        from ml.registry import load_model
        from ml.features import build_features
        from ml.model import predict as ml_predict

        from config.settings import get_settings as _get_settings
        _ver = _get_settings().ml_model_version or None
        regime_clf      = await load_model("regime_classifier", db_symbol, "5m", version=_ver)
        direction_model = await load_model("direction_model",   db_symbol, "5m", version=_ver)

        if regime_clf is None or direction_model is None:
            return {"status": "no_model", "message": "Run training script first"}

        feat = build_features(ml_df)
        if feat.empty:
            return {"status": "no_features"}

        feat["regime"] = regime_clf.predict(ml_df).reindex(feat.index).fillna(2)
        regime_label   = regime_clf.predict_label(ml_df).iloc[-1] if not ml_df.empty else "UNKNOWN"
        direction, confidence = ml_predict(direction_model, feat)
        dir_map = {1: "BUY_CE", -1: "BUY_PE", 0: "AVOID"}

        return {
            "status":     "active" if is_enabled("ENABLE_ML_SIGNAL") else "shadow",
            "direction":  dir_map[direction],
            "confidence": round(confidence, 3),
            "regime":     regime_label,
        }
    except ImportError:
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

        # Track rule-vs-ML agreement for shadow observability (2.6)
        rule_dir = signal.get("direction")
        ml_dir   = ml_info.get("direction") if ml_info.get("status") in ("shadow", "active") else None
        if rule_dir and ml_dir:
            _shadow_stats["total"] += 1
            if rule_dir == ml_dir:
                _shadow_stats["agree"] += 1
            else:
                _shadow_stats["disagree"] += 1
        elif rule_dir:
            _shadow_stats["rule_only"] += 1

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
    from config.settings import get_settings as _gs
    from paper_trading.simulator import get_daily_pnl, get_open_count
    from risk.engine import check_daily_cutoff, check_max_positions

    # Kill-switch blocks all new entries
    if _kill_switch_active:
        raise HTTPException(403, "Kill switch is active — all trading halted")

    cfg = _gs()

    # Daily loss / profit cutoff (3.2)
    daily_pnl = get_daily_pnl()
    halted, reason = check_daily_cutoff(
        daily_pnl, cfg.paper_trading_capital,
        cfg.daily_loss_limit_pct, cfg.daily_profit_target_pct,
    )
    if halted:
        raise HTTPException(403, f"Daily cutoff: {reason}")

    # Max open positions cap (3.5)
    open_count = get_open_count()
    allowed, reason = check_max_positions(open_count, cfg.max_open_positions)
    if not allowed:
        raise HTTPException(403, f"Position cap: {reason}")

    result = enter_trade(
        req.ticker, req.strike, req.direction,
        req.entry_price, req.lots, req.lot_size, req.signal
    )

    # Phase 5 — fire-and-forget trade entry alert (never blocks the response)
    try:
        from config.settings import get_settings as _gs5
        from notifications.telegram import send_trade_alert
        from api.ws import broadcast
        import asyncio
        _s5 = _gs5()
        asyncio.ensure_future(send_trade_alert(
            "trade_entry", req.ticker, req.direction,
            req.strike, req.entry_price,
            bot_token=_s5.telegram_bot_token,
            chat_id=_s5.telegram_chat_id,
        ))
        asyncio.ensure_future(broadcast({
            "type": "trade_event", "event": "entry",
            "ticker": req.ticker, "direction": req.direction,
            "strike": req.strike, "price": req.entry_price,
        }))
    except Exception:
        pass

    return result

@router.post("/paper-trade/exit")
async def paper_exit(req: PaperTradeExitRequest):
    result = exit_trade(req.trade_id, req.exit_price)

    # Phase 5 — fire-and-forget trade exit alert
    try:
        from config.settings import get_settings as _gs5e
        from notifications.telegram import send_trade_alert
        from api.ws import broadcast
        import asyncio
        _s5e = _gs5e()
        pnl = result.get("pnl")
        asyncio.ensure_future(send_trade_alert(
            "trade_exit", "", "", 0, req.exit_price, pnl=pnl,
            bot_token=_s5e.telegram_bot_token,
            chat_id=_s5e.telegram_chat_id,
        ))
        asyncio.ensure_future(broadcast({
            "type": "trade_event", "event": "exit",
            "trade_id": req.trade_id, "exit_price": req.exit_price, "pnl": pnl,
        }))
    except Exception:
        pass

    return result

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


@router.get("/ml/shadow-stats")
async def ml_shadow_stats_endpoint():
    """
    Return rule-vs-ML agreement statistics accumulated since last server start.
    Phase 2.6 observability — shows how often the rule engine and ML signal agree.
    """
    total = _shadow_stats["total"]
    return {
        **_shadow_stats,
        "agreement_rate": round(_shadow_stats["agree"] / total, 3) if total > 0 else None,
    }


# ---------------------------------------------------------------------------
# Phase 3 — Kill switch  (3.4)
# ---------------------------------------------------------------------------

@router.post("/kill-switch")
async def kill_switch():
    """
    Immediately halt all trading:
      1. Sets _kill_switch_active = True (blocks future paper_enter calls).
      2. Marks every OPEN paper trade as HALTED in SQLite.
      3. Writes an audit log entry to Neon.

    Subsequent calls to POST /paper-trade/enter return HTTP 403 until the
    server restarts (intentional — requires manual operator action to resume).
    """
    global _kill_switch_active
    _kill_switch_active = True

    from paper_trading.simulator import halt_all_open
    halted_trades = halt_all_open()

    # Best-effort audit log to Neon (does not fail the response if DB is down)
    try:
        import json
        from db.base import get_session_factory
        from sqlalchemy import text as _text
        async with get_session_factory()() as session:
            await session.execute(
                _text(
                    "INSERT INTO audit_log (action, payload_json, actor) "
                    "VALUES ('KILL_SWITCH', CAST(:payload AS jsonb), 'api')"
                ),
                {"payload": json.dumps({"halted_trade_ids": [t["trade_id"] for t in halted_trades]})},
            )
            await session.commit()
    except Exception:
        pass

    # Phase 5 — critical alert on kill switch (fire-and-forget)
    try:
        from config.settings import get_settings as _gs5k
        from notifications.telegram import send_trade_alert
        from notifications.email import send_critical_alert
        from api.ws import broadcast
        import asyncio
        _s5k = _gs5k()
        asyncio.ensure_future(send_trade_alert(
            "kill_switch", "ALL", "HALTED", 0, 0,
            bot_token=_s5k.telegram_bot_token,
            chat_id=_s5k.telegram_chat_id,
        ))
        asyncio.ensure_future(send_critical_alert(
            "Kill Switch Activated",
            f"{len(halted_trades)} trades halted.",
            smtp_host=_s5k.smtp_host, smtp_port=_s5k.smtp_port,
            smtp_user=_s5k.smtp_user, smtp_password=_s5k.smtp_password,
            to_address=_s5k.alert_email_to,
        ))
        asyncio.ensure_future(broadcast({"type": "kill_switch", "trades_halted": len(halted_trades)}))
    except Exception:
        pass

    return {
        "status": "halted",
        "message": "Kill switch activated. All trading halted. Restart server to resume.",
        "trades_halted": len(halted_trades),
        "halted_trades": halted_trades,
    }


@router.get("/kill-switch/status")
async def kill_switch_status():
    """Check whether the kill switch is currently active."""
    return {"active": _kill_switch_active}


# ---------------------------------------------------------------------------
# Phase 4 — Broker routes
# ---------------------------------------------------------------------------

# In-memory store of persisted (encrypted) API credentials for this session.
# In production these would be read from the DB on startup.
_broker_credentials: dict = {}  # {"kite_api_key": <enc>, "kite_access_token": <enc>}


def _get_broker_adapter():
    """
    Return the correct BrokerAdapter based on feature flag + broker_mode.
    ENABLE_LIVE_BROKER=false (default) → always PaperBrokerAdapter.
    ENABLE_LIVE_BROKER=true + broker_mode=live → ZerodhaKiteAdapter.
    """
    from config.feature_flags import is_enabled
    from config.settings import get_settings as _gs
    from broker.paper_adapter import PaperBrokerAdapter

    if not is_enabled("ENABLE_LIVE_BROKER"):
        return PaperBrokerAdapter()

    cfg = _gs()
    if cfg.broker_mode != "live":
        return PaperBrokerAdapter()

    # Live path — decrypt credentials and build Zerodha adapter
    from broker.crypto import decrypt
    from broker.zerodha_adapter import ZerodhaKiteAdapter
    try:
        api_key      = decrypt(_broker_credentials["kite_api_key"],
                               cfg.broker_encryption_key, cfg.broker_salt)
        access_token = decrypt(_broker_credentials["kite_access_token"],
                               cfg.broker_encryption_key, cfg.broker_salt)
        return ZerodhaKiteAdapter(api_key=api_key, access_token=access_token)
    except (KeyError, Exception) as exc:
        raise HTTPException(503, f"Broker credentials not configured: {exc}")


async def _persist_order(req_data: dict, result, mode: str) -> None:
    """Write order row to Postgres broker_orders table. Best-effort — never fails the response."""
    import json as _json
    try:
        from db.base import get_session_factory
        from sqlalchemy import text as _text
        import uuid as _uuid
        async with get_session_factory()() as session:
            await session.execute(
                _text(
                    "INSERT INTO broker_orders "
                    "  (id, client_order_id, symbol, exchange, instrument_type, "
                    "   transaction_type, order_type, product, qty, price, "
                    "   trigger_price, status, broker_order_id, broker_response, mode) "
                    "VALUES "
                    "  (:id, :coid, :symbol, :exchange, :itype, :ttype, :otype, "
                    "   :product, :qty, :price, :tprice, :status, :boid, "
                    "   CAST(:resp AS jsonb), :mode) "
                    "ON CONFLICT (client_order_id) DO UPDATE SET "
                    "  status=EXCLUDED.status, broker_order_id=EXCLUDED.broker_order_id, "
                    "  broker_response=EXCLUDED.broker_response, updated_at=now()"
                ),
                {
                    "id":      str(_uuid.uuid4()),
                    "coid":    req_data["client_order_id"],
                    "symbol":  req_data["symbol"],
                    "exchange":req_data.get("exchange", "NSE"),
                    "itype":   req_data.get("instrument_type", "EQ"),
                    "ttype":   req_data["transaction_type"],
                    "otype":   req_data.get("order_type", "MARKET"),
                    "product": req_data.get("product", "MIS"),
                    "qty":     req_data["qty"],
                    "price":   req_data.get("price", 0),
                    "tprice":  req_data.get("trigger_price", 0),
                    "status":  result.status,
                    "boid":    result.broker_order_id or None,
                    "resp":    _json.dumps(result.raw_response),
                    "mode":    mode,
                },
            )
            await session.commit()
    except Exception:
        pass


async def _audit_order(action: str, payload: dict) -> None:
    """Append an immutable audit log row for every order attempt (4.7)."""
    import json as _json
    try:
        from db.base import get_session_factory
        from sqlalchemy import text as _text
        async with get_session_factory()() as session:
            await session.execute(
                _text(
                    "INSERT INTO audit_log (action, payload_json, actor) "
                    "VALUES (:action, CAST(:payload AS jsonb), 'broker_route')"
                ),
                {"action": action, "payload": _json.dumps(payload)},
            )
            await session.commit()
    except Exception:
        pass


class BrokerOrderRequest(BaseModel):
    symbol:           str
    exchange:         str   = "NSE"
    instrument_type:  str   = "CE"
    transaction_type: str   = "BUY"
    order_type:       str   = "MARKET"
    product:          str   = "MIS"
    qty:              int
    price:            float = 0.0
    trigger_price:    float = 0.0
    client_order_id:  str   = ""  # leave empty → auto-generated


class ApiKeyRequest(BaseModel):
    kite_api_key:      str
    kite_access_token: str


@router.get("/broker/status")
async def broker_status():
    """Return current broker mode and ENABLE_LIVE_BROKER flag state."""
    from config.feature_flags import is_enabled
    from config.settings import get_settings as _gs
    cfg = _gs()
    return {
        "enable_live_broker": is_enabled("ENABLE_LIVE_BROKER"),
        "broker_mode":        cfg.broker_mode,
        "active_adapter":     "live" if (is_enabled("ENABLE_LIVE_BROKER") and cfg.broker_mode == "live") else "paper",
        "credentials_stored": bool(_broker_credentials),
    }


@router.post("/broker/api-keys")
async def store_api_keys(req: ApiKeyRequest):
    """
    Encrypt and store Kite API credentials in memory (4.5).
    Plaintext is never written to disk or logs — only the Fernet token is kept.
    """
    from config.settings import get_settings as _gs
    from broker.crypto import encrypt, is_valid_key
    cfg = _gs()
    if not cfg.broker_encryption_key:
        raise HTTPException(400, "BROKER_ENCRYPTION_KEY env var is not set")
    if not is_valid_key(cfg.broker_encryption_key):
        raise HTTPException(400, "BROKER_ENCRYPTION_KEY is not a valid Fernet key")

    _broker_credentials["kite_api_key"]      = encrypt(req.kite_api_key,
                                                        cfg.broker_encryption_key,
                                                        cfg.broker_salt)
    _broker_credentials["kite_access_token"] = encrypt(req.kite_access_token,
                                                        cfg.broker_encryption_key,
                                                        cfg.broker_salt)

    await _audit_order("API_KEYS_STORED", {"masked_api_key": req.kite_api_key[:4] + "****"})
    return {"status": "stored", "message": "Credentials encrypted and stored in memory"}


@router.post("/broker/order")
async def place_broker_order(req: BrokerOrderRequest):
    """
    Place an order via the active broker adapter (paper or live).
    Idempotent: duplicate client_order_id returns the existing DB row (4.6).
    """
    import uuid as _uuid
    from config.feature_flags import is_enabled
    from config.settings import get_settings as _gs
    from broker.interface import OrderRequest as BrokerReq

    client_oid = req.client_order_id or str(_uuid.uuid4())
    mode = "live" if (is_enabled("ENABLE_LIVE_BROKER") and _gs().broker_mode == "live") else "paper"

    broker_req = BrokerReq(
        symbol=req.symbol,
        exchange=req.exchange,
        instrument_type=req.instrument_type,
        transaction_type=req.transaction_type,
        order_type=req.order_type,
        product=req.product,
        qty=req.qty,
        price=req.price,
        trigger_price=req.trigger_price,
        client_order_id=client_oid,
    )

    adapter = _get_broker_adapter()
    result  = await adapter.place_order(broker_req)

    req_dict = {**req.model_dump(), "client_order_id": client_oid}
    await _persist_order(req_dict, result, mode)
    await _audit_order("ORDER_PLACE_ATTEMPT", {
        "client_order_id": client_oid,
        "symbol": req.symbol,
        "status": result.status,
        "broker_order_id": result.broker_order_id,
        "mode": mode,
    })

    return {
        "client_order_id": client_oid,
        "broker_order_id": result.broker_order_id,
        "status":          result.status,
        "message":         result.message,
        "mode":            mode,
    }


@router.delete("/broker/order/{order_id}")
async def cancel_broker_order(order_id: str):
    """Cancel an open order by broker_order_id."""
    adapter = _get_broker_adapter()
    result  = await adapter.cancel_order(order_id)
    await _audit_order("ORDER_CANCEL_ATTEMPT", {
        "broker_order_id": order_id,
        "status": result.status,
    })
    return {"broker_order_id": order_id, "status": result.status, "message": result.message}


@router.get("/broker/orders")
async def list_broker_orders():
    """List all orders from the active adapter."""
    adapter = _get_broker_adapter()
    orders  = await adapter.get_orders()
    return [
        {
            "broker_order_id":  o.broker_order_id,
            "client_order_id":  o.client_order_id,
            "symbol":           o.symbol,
            "transaction_type": o.transaction_type,
            "qty":              o.qty,
            "price":            o.price,
            "status":           o.status,
            "filled_qty":       o.filled_qty,
            "average_price":    o.average_price,
        }
        for o in orders
    ]


@router.get("/broker/positions")
async def list_broker_positions():
    """List all open positions from the active adapter."""
    adapter   = _get_broker_adapter()
    positions = await adapter.get_positions()
    return [
        {
            "symbol":          p.symbol,
            "qty":             p.qty,
            "avg_price":       p.avg_price,
            "pnl":             p.pnl,
            "product":         p.product,
            "instrument_type": p.instrument_type,
        }
        for p in positions
    ]


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


# ---------------------------------------------------------------------------
# Phase 6.1 — Portfolio analytics
# ---------------------------------------------------------------------------

@router.get("/analytics/equity-curve")
async def analytics_equity_curve():
    """Time-series of per-trade P&L and cumulative P&L sorted by exit time."""
    from paper_trading.simulator import get_history
    from analytics.engine import build_equity_curve
    return build_equity_curve(get_history())


@router.get("/analytics/summary")
async def analytics_summary():
    """Full analytics: equity curve, drawdown series, win-rate, streaks."""
    from paper_trading.simulator import get_history
    from analytics.engine import compute_analytics
    return compute_analytics(get_history())


# ---------------------------------------------------------------------------
# Phase 6.2 — Market scanner
# ---------------------------------------------------------------------------

@router.get("/scanner/results")
async def scanner_results():
    """Return cached Nifty-50 scan (gainers, losers, volume spikes, breakouts)."""
    from scanner.engine import run_scan_async
    return await run_scan_async()


@router.post("/scanner/run")
async def scanner_run():
    """Force a fresh scan, update cache, and push results to WS clients."""
    import asyncio
    from scanner.engine import invalidate_cache, run_scan_async
    invalidate_cache()
    results = await run_scan_async()
    try:
        from api.ws import broadcast
        asyncio.ensure_future(broadcast({"type": "scanner_update", "data": results}))
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Phase 6.3 — Admin endpoints
# ---------------------------------------------------------------------------

_VALID_FLAGS = ["ENABLE_ML_SIGNAL", "ENABLE_LIVE_BROKER", "ENABLE_AUTO_EXECUTION"]


@router.get("/admin/audit-log")
async def admin_audit_log(limit: int = 50, offset: int = 0):
    """Paginated immutable audit log from Postgres."""
    try:
        from db.base import get_session_factory
        from sqlalchemy import text as _text
        async with get_session_factory()() as session:
            rows = await session.execute(
                _text(
                    "SELECT id, action, payload_json, actor, created_at "
                    "FROM audit_log ORDER BY created_at DESC "
                    "LIMIT :limit OFFSET :offset"
                ),
                {"limit": min(limit, 200), "offset": max(offset, 0)},
            )
            entries = [
                {
                    "id":         str(r[0]),
                    "action":     r[1],
                    "payload":    r[2],
                    "actor":      r[3],
                    "created_at": r[4].isoformat() if r[4] else None,
                }
                for r in rows.fetchall()
            ]
        return {"entries": entries, "limit": limit, "offset": offset}
    except Exception as exc:
        raise HTTPException(500, f"Audit log query failed: {exc}")


@router.get("/admin/flags")
async def admin_flags():
    """List all feature flags and their current state (env + in-memory overrides)."""
    from config.feature_flags import is_enabled
    return {
        "flags": [{"name": f, "enabled": is_enabled(f)} for f in _VALID_FLAGS]
    }


class FlagUpdateRequest(BaseModel):
    enabled: bool


@router.patch("/admin/flags/{flag_name}")
async def admin_toggle_flag(flag_name: str, req: FlagUpdateRequest):
    """Toggle a feature flag in-memory (resets on server restart)."""
    if flag_name not in _VALID_FLAGS:
        raise HTTPException(400, f"Unknown flag. Valid: {_VALID_FLAGS}")
    from config.feature_flags import set_flag
    set_flag(flag_name, req.enabled)
    try:
        import json as _json
        from db.base import get_session_factory
        from sqlalchemy import text as _text
        async with get_session_factory()() as session:
            await session.execute(
                _text(
                    "INSERT INTO audit_log (action, payload_json, actor) "
                    "VALUES ('FLAG_TOGGLE', CAST(:payload AS jsonb), 'admin_ui')"
                ),
                {"payload": _json.dumps({"flag": flag_name, "enabled": req.enabled})},
            )
            await session.commit()
    except Exception:
        pass
    return {"flag": flag_name, "enabled": req.enabled}
