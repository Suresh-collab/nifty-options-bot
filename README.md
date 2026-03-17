# Nifty Options Bot

AI-powered options signal and paper trading tool for Nifty 50 and Sensex.
Built with FastAPI + React + Claude AI. No broker required in Phase 1 & 2.

## Quick Start

### 1. Backend setup
```bash
cd backend
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
bash start.sh
```

### 2. Frontend setup (new terminal)
```bash
cd frontend
bash start.sh
```

### 3. Open the app
Visit http://localhost:5173

---

## Project Structure
```
nifty-options-bot/
├── backend/
│   ├── data/
│   │   ├── market_data.py      # yfinance — free OHLCV
│   │   └── options_chain.py    # NSE option chain scraper
│   ├── indicators/
│   │   └── engine.py           # RSI, MACD, SuperTrend, BB, PCR
│   ├── ai/
│   │   ├── signal_engine.py    # Claude AI signal generation
│   │   └── budget_optimizer.py # Strike + lot recommendation
│   ├── paper_trading/
│   │   └── simulator.py        # SQLite-backed trade tracker
│   ├── api/
│   │   └── routes.py           # FastAPI endpoints
│   ├── main.py
│   └── requirements.txt
└── frontend/
    └── src/
        ├── components/
        │   ├── MarketStatusBar.jsx
        │   ├── TickerSelector.jsx
        │   ├── SignalCard.jsx
        │   ├── IndicatorGrid.jsx
        │   ├── BudgetOptimizer.jsx
        │   ├── TradeConfirmModal.jsx
        │   └── TradeHistory.jsx
        ├── store/index.js
        └── App.jsx
```

## API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /signal/{ticker} | Full AI signal for NIFTY or SENSEX |
| POST | /optimize | Best strike for given budget |
| GET | /market-status | NSE open/closed, expiry countdown |
| POST | /paper-trade/enter | Log a paper trade |
| POST | /paper-trade/exit | Close trade with P&L |
| GET | /paper-trade/history | All trades |
| GET | /paper-trade/stats | Win rate, total P&L |
| GET | /health | Backend status |

## Phase Roadmap
- **Phase 1** (now): Free data, AI signals, paper trading UI — ₹0 cost
- **Phase 2**: Track signal accuracy over 2–4 weeks of paper trades
- **Phase 3**: Add Zerodha Kite Connect for live execution — ₹2,000/month

## Disclaimer
For educational and paper trading purposes only.
Not SEBI registered. Not financial advice. Options trading involves significant risk.
