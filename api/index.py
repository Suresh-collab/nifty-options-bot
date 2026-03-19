import sys
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Nifty Options Bot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Test what packages are available
_pkg_status = {}
for pkg in ["numpy", "pandas", "yfinance", "httpx", "aiosqlite"]:
    try:
        __import__(pkg)
        _pkg_status[pkg] = "ok"
    except Exception as e:
        _pkg_status[pkg] = str(e)

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "packages": _pkg_status,
        "backend_dir_exists": os.path.isdir(backend_dir),
        "routes_exists": os.path.isfile(os.path.join(backend_dir, "api", "routes.py")),
    }
