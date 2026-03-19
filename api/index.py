import sys
import os
import importlib

# Add the backend directory to the Python path so all backend imports resolve
backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, backend_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the router from backend/api/routes.py
# Use importlib to avoid conflict with this api/ directory
routes_mod = importlib.import_module('api.routes')
router = routes_mod.router

app = FastAPI(title="Nifty Options Bot", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

@app.get("/api/health")
async def health():
    return {"status": "ok", "env": "vercel"}
