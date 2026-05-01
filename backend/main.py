import os
import sys

# Ensure backend/ is on sys.path so short imports (config.*, db.*, middleware.*)
# work when uvicorn is started from the backend/ directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config.settings import get_settings
from middleware.logging import RequestLoggingMiddleware, setup_logging

_settings = get_settings()
setup_logging(_settings.log_level)

app = FastAPI(title="Nifty Options Bot", version="1.0.0")

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


@app.get("/health")
async def health():
    return {"status": "ok", "env": "development"}
