import os
import sys

# Ensure backend/ is on sys.path so short imports (config.*, db.*, middleware.*)
# work when uvicorn is started from the backend/ directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.ws import ws_router, start_pnl_poller
from config.settings import get_settings
from middleware.logging import RequestLoggingMiddleware, setup_logging

_settings = get_settings()
setup_logging(_settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P&L poller — broadcasts paper-trade state to connected WS clients.
    task = await start_pnl_poller(interval=1.0)
    # APScheduler — daily P&L summary at 3:30 PM IST (10:00 UTC).
    from scheduler.jobs import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()
    yield
    task.cancel()
    scheduler.shutdown(wait=False)


app = FastAPI(title="Nifty Options Bot", version="1.0.0", lifespan=lifespan)

# RequestLoggingMiddleware must be added before CORS so request_id is set early
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(ws_router)   # WebSocket at /ws/live (no /api prefix)


@app.get("/health")
async def health():
    return {"status": "ok", "env": "development"}
