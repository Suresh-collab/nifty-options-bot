from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
from data.market_data import get_ohlcv, get_spot_price, get_market_status
from data.options_chain import fetch_option_chain, get_next_expiry, get_atm_iv
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


# --- Market status ---
@router.get("/market-status")
async def market_status():
    return get_market_status()


# --- Full signal for a ticker ---
@router.get("/signal/{ticker}")
async def get_signal(ticker: str):
    ticker = ticker.upper()
    if ticker not in ("NIFTY", "SENSEX"):
        raise HTTPException(400, "ticker must be NIFTY or SENSEX")
    try:
        df      = get_ohlcv(ticker, interval="5m")
        spot    = get_spot_price(ticker)
        chain   = fetch_option_chain(ticker)
        iv      = get_atm_iv(chain)
        indic   = compute_indicators(df, pcr=chain["pcr"], iv=iv)
        expiry  = chain.get("expiry", get_next_expiry(ticker).strftime("%d-%b-%Y"))
        signal  = generate_signal(ticker, spot, str(expiry), indic, chain)
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
        chain  = fetch_option_chain(ticker)
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
