"""Deezer audio preview endpoints.

GET /v1/audio/preview        — search Deezer and return 30-second preview URL
GET /v1/audio/preview/batch  — batch search, comma-separated queries
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/audio", tags=["audio-preview"])

DEEZER_SEARCH_URL = "https://api.deezer.com/search"

# Simple in-memory cache: query -> preview result dict
_cache: dict[str, dict] = {}


async def _fetch_preview(q: str) -> dict:
    """Search Deezer for q and return preview info. Results are cached."""
    if q in _cache:
        return _cache[q]

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(DEEZER_SEARCH_URL, params={"q": q, "limit": 1})

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Deezer API returned {resp.status_code}",
        )

    data = resp.json()
    tracks = data.get("data", [])

    if not tracks:
        result = {"query": q, "found": False, "preview_url": None}
        _cache[q] = result
        return result

    track = tracks[0]
    result = {
        "query": q,
        "found": True,
        "preview_url": track.get("preview"),
        "title": track.get("title"),
        "artist": track.get("artist", {}).get("name"),
        "album": track.get("album", {}).get("title"),
        "track_id": track.get("id"),
        "cover_url": track.get("album", {}).get("cover_medium"),
    }
    _cache[q] = result
    return result


@router.get("/preview")
async def get_preview(q: str = Query(..., description="Search query, e.g. 'AC/DC Back in Black'")):
    """Search Deezer and return the 30-second preview MP3 URL for the top result."""
    return await _fetch_preview(q)


@router.get("/preview/batch")
async def get_preview_batch(
    queries: str = Query(..., alias="q", description="Comma-separated search queries"),
):
    """Batch preview lookup — returns previews for all comma-separated queries."""
    query_list = [q.strip() for q in queries.split(",") if q.strip()]
    if not query_list:
        raise HTTPException(status_code=400, detail="No queries provided.")

    import asyncio
    results = await asyncio.gather(*[_fetch_preview(q) for q in query_list])
    return {"results": list(results)}
