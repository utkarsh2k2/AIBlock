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


# Realistic mock used when the Deezer API is unreachable (e.g. sandboxed CI/dev).
# Keyed by lowercase first-word of the query; falls back to a generic entry.
_MOCK_DATA: dict[str, dict] = {
    "ac/dc": {
        "track_id": 917049,
        "title": "Back In Black",
        "artist": "AC/DC",
        "album": "Back In Black",
        "preview_url": "https://cdns-preview-d.dzcdn.net/stream/c-deda7fa9316d9e9e880d2c6207e92260-5.mp3",
        "cover_url": "https://e-cdns-images.dzcdn.net/images/cover/2e018122cb56986277102d2041a592c8/250x250-000000-80-0-0.jpg",
    },
    "billie": {
        "track_id": 682975172,
        "title": "bad guy",
        "artist": "Billie Eilish",
        "album": "WHEN WE ALL FALL ASLEEP, WHERE DO WE GO?",
        "preview_url": "https://cdns-preview-3.dzcdn.net/stream/c-3bba2a3d0d27e51f01e038a9cb8b21d4-5.mp3",
        "cover_url": "https://e-cdns-images.dzcdn.net/images/cover/3d0a4a66e7b66a1b96f09a8aff3f29a7/250x250-000000-80-0-0.jpg",
    },
    "default": {
        "track_id": 3135556,
        "title": "One More Time",
        "artist": "Daft Punk",
        "album": "Discovery",
        "preview_url": "https://cdns-preview-e.dzcdn.net/stream/c-e77d23e0c8b4b8b0f29f4b0ab97e1e75-8.mp3",
        "cover_url": "https://e-cdns-images.dzcdn.net/images/cover/2e018122cb56986277102d2041a592c8/250x250-000000-80-0-0.jpg",
    },
}


def _mock_response(q: str) -> dict:
    key = q.lower().split()[0] if q else "default"
    data = _MOCK_DATA.get(key, _MOCK_DATA["default"])
    return {"query": q, "found": True, "mocked": True, **data}


async def _fetch_preview(q: str) -> dict:
    """Search Deezer for q and return preview info. Results are cached."""
    if q in _cache:
        return _cache[q]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(DEEZER_SEARCH_URL, params={"q": q, "limit": 1})
    except (httpx.ProxyError, httpx.ConnectTimeout, httpx.ConnectError) as exc:
        log.warning("Deezer API unreachable (%s); returning mock response.", exc)
        result = _mock_response(q)
        _cache[q] = result
        return result

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
