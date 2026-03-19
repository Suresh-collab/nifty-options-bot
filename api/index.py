import sys
import os
import importlib.util
import traceback

# Add the backend directory to the Python path for sub-imports (data, indicators, etc.)
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, backend_dir)

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

# Try to load backend routes — capture any errors
_load_error = None
try:
    spec = importlib.util.spec_from_file_location(
        "backend_routes",
        os.path.join(backend_dir, "api", "routes.py")
    )
    routes_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes_mod)
    app.include_router(routes_mod.router, prefix="/api")
except Exception as e:
    _load_error = traceback.format_exc()


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "env": "vercel",
        "backend_dir_exists": os.path.isdir(backend_dir),
        "routes_file_exists": os.path.isfile(os.path.join(backend_dir, "api", "routes.py")),
        "router_error": _load_error,
    }
