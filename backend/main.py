import os
import sys

# Ensure backend/ is on sys.path so short imports (config.*, db.*, middleware.*)
# work when uvicorn is started from the backend/ directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.ws import ws_router, start_pnl_poller, start_oi_snapshot_poller
from config.settings import get_settings
from middleware.logging import RequestLoggingMiddleware, setup_logging

_settings = get_settings()
setup_logging(_settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P&L poller — broadcasts paper-trade state to connected WS clients.
    pnl_task = await start_pnl_poller(interval=1.0)
    # OI snapshot poller — no-ops unless ENABLE_OI_FLOW_LOGGING is true.
    # Starts collecting forward-test data for OI Buildup once enabled.
    oi_task = await start_oi_snapshot_poller(
        interval=_settings.oi_snapshot_interval_sec,
    )
    # APScheduler — daily P&L summary at 3:30 PM IST (10:00 UTC).
    from scheduler.jobs import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()
    yield
    pnl_task.cancel()
    oi_task.cancel()
    scheduler.shutdown(wait=False)


app = FastAPI(title="Nifty Options Bot", version="1.0.0", lifespan=lifespan)

# RequestLoggingMiddleware must be added before CORS so request_id is set early
app.add_middleware(RequestLoggingMiddleware)
_cors_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://nifty-options-bot.vercel.app",
]
_extra = os.environ.get("CORS_EXTRA_ORIGINS", "")
if _extra:
    _cors_origins += [o.strip() for o in _extra.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://nifty-options-bot.*\.vercel\.app",  # preview deploys
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(ws_router)   # WebSocket at /ws/live (no /api prefix)


@app.get("/health")
async def health():
    return {"status": "ok", "env": "development"}
