"""Minimal server for testing without DB/Redis."""
import os
import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from aiblock.api.deezer_preview import router

_static_dir = pathlib.Path(__file__).parent / "src/aiblock/static"

app = FastAPI(title="AIBlock - Deezer Preview")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

_HEALTH = {"status": "ok", "app": "AI or Not"}

@app.get("/")
async def root():
    return _HEALTH

@app.get("/health")
async def health():
    return _HEALTH

@app.get("/home", include_in_schema=False)
async def home():
    return FileResponse(_static_dir / "fake-or-real.html")

@app.get("/game", include_in_schema=False)
async def game():
    return FileResponse(_static_dir / "fake-or-real.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
