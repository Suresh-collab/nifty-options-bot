import sys
import os
import importlib.util
import traceback

# Add the backend directory to the Python path for sub-imports (data, indicators, etc.)
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, backend_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Nifty Options Bot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "env": "vercel"}


# Try to load backend routes — if it fails, return diagnostic info
_router_loaded = False
_load_error = None

try:
    spec = importlib.util.spec_from_file_location(
        "backend_routes",
        os.path.join(backend_dir, "api", "routes.py")
    )
    routes_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes_mod)
    app.include_router(routes_mod.router, prefix="/api")
    _router_loaded = True
except Exception as e:
    _load_error = traceback.format_exc()


@app.get("/api/debug")
async def debug():
    return {
        "router_loaded": _router_loaded,
        "error": _load_error,
        "backend_dir": backend_dir,
        "python_version": sys.version,
    }
