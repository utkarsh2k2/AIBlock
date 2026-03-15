"""Minimal server for testing without DB/Redis."""
import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.aiblock.api.deezer_preview import router

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

@app.get("/home")
async def read_root():
    return FileResponse("static/ai-or-not.html")
@app.get("/game", include_in_schema=False)
async def game():
    return FileResponse(_static_dir / "fake-or-real.html")
