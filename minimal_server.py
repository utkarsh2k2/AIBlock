"""Minimal server for testing without DB/Redis."""
import logging
import os
import pathlib
import sys
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Log to stderr so Railway captures it in Deploy Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("aiblock")

from src.aiblock.api.deezer_preview import router

_static_dir = (pathlib.Path(__file__).resolve().parent / "src" / "aiblock" / "static").resolve()

# Startup: log static dir and key files (visible in Railway Deploy Logs)
log.info("static_dir=%s exists=%s", _static_dir, _static_dir.is_dir())
for name in ("mark3.html", "ai-or-not.html", "fake-or-real.html"):
    p = _static_dir / name
    log.info("  %s: exists=%s", name, p.is_file())


def _static_file(name: str):
    """Return FileResponse for a file under _static_dir, or 404 if missing."""
    path = _static_dir / name
    if not path.is_file():
        log.warning("static file missing: %s (dir=%s)", name, _static_dir)
        raise HTTPException(status_code=404, detail=f"Static file not found: {name}")
    return FileResponse(path)

app = FastAPI(title="AIBlock - Deezer Preview")


@app.on_event("startup")
def _on_startup():
    port = int(os.environ.get("PORT", "8000"))
    log.info("AIBlock server starting on 0.0.0.0:%s", port)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _log_requests(request, call_next):
    """Log every request and response for debugging in Railway HTTP/Deploy logs."""
    method = request.method
    path = request.url.path
    try:
        response = await call_next(request)
        log.info("%s %s -> %s", method, path, response.status_code)
        return response
    except Exception as e:
        log.exception("%s %s -> error: %s", method, path, e)
        raise

app.include_router(router)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

_HEALTH = {"status": "ok", "app": "AI or Not"}

@app.get("/")
async def root():
    return _HEALTH

@app.get("/health")
async def health():
    return _HEALTH

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

@app.get("/home", include_in_schema=False)
async def home():
    return _static_file("mark3.html")

@app.get("/game", include_in_schema=False)
async def game():
    return _static_file("fake-or-real.html")

@app.get("/mark2", include_in_schema=False)
async def mark2():
    return _static_file("mark2.html")

@app.get("/mark3", include_in_schema=False)
async def mark3():
    return _static_file("mark3.html")


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
