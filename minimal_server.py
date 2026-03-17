"""Minimal server for testing without DB/Redis."""
import pathlib
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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


# Known sample paths used by work1/other UIs -> Deezer 30s preview URL
_PREVIEW_SAMPLE_URLS = {
    "acdc/backinblack-sample.mp3": "https://cdns-preview-d.dzcdn.net/stream/c-deda7fa9316d9e9e880d2c6207e92260-5.mp3",
    "acdc/back-in-black-sample.mp3": "https://cdns-preview-d.dzcdn.net/stream/c-deda7fa9316d9e9e880d2c6207e92260-5.mp3",
}


@app.get("/v1/audio/preview/{path:path}", include_in_schema=False)
async def preview_sample(path: str):
    """Serve known sample paths (e.g. acdc/backinblack-sample.mp3) by streaming Deezer preview."""
    url = _PREVIEW_SAMPLE_URLS.get(path) or _PREVIEW_SAMPLE_URLS.get(path.lower())
    if not url:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown preview: {path}")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "audio/mpeg")
        return StreamingResponse(
            r.aiter_bytes(),
            media_type=content_type,
            headers={"Accept-Ranges": "bytes"},
        )


@app.get("/v1/audio/proxy", include_in_schema=False)
async def audio_proxy(url: str = Query(..., description="Audio URL to stream")):
    """Stream audio from an external URL (e.g. Deezer) to avoid CORS."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid url")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        content_type = r.headers.get("content-type", "audio/mpeg")
        return StreamingResponse(
            r.aiter_bytes(),
            media_type=content_type,
            headers={"Accept-Ranges": "bytes"},
        )

@app.get("/home")
async def read_root():
    return FileResponse(_static_dir / "ai-or-not.html")


@app.get("/game", include_in_schema=False)
async def game():
    return FileResponse(_static_dir / "fake-or-real.html")


@app.get("/mark2", include_in_schema=False)
async def mark2():
    return FileResponse(_static_dir / "mark2.html")


@app.get("/mark3", include_in_schema=False)
async def mark3():
    return FileResponse(_static_dir / "mark3.html")
