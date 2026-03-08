"""AIBlock MCP server.

Exposes three tools for AI agents:
  detect_audio   — detect whether audio at a URL is AI-generated
  get_metadata   — get track metadata (title, artist, duration) without downloading
  list_platforms — list supported platforms

Run:
  aiblock-mcp                      # stdio transport (Claude Desktop / Claude Code)

Register with Claude Code:
  claude mcp add --transport stdio aiblock -- aiblock-mcp

Or add to .mcp.json (project-scoped):
  {
    "mcpServers": {
      "aiblock": { "type": "stdio", "command": "aiblock-mcp" }
    }
  }

Design notes:
  - All tool handlers are async; sync pipeline work runs in a thread pool via
    run_in_executor to avoid blocking the asyncio event loop.
  - MCP fetch is NOT used for metadata — yt-dlp's extract_info handles YouTube's
    JS-rendering correctly, and spotdl handles Spotify. Raw HTTP fetch fails both.
  - The server talks directly to the local pipeline (no API key required).
    For multi-tenant production access, point agents at the REST API instead.
"""

import asyncio
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

log = logging.getLogger(__name__)

mcp = FastMCP(
    "aiblock",
    instructions=(
        "AIBlock detects AI-generated audio on YouTube and Spotify. "
        "Call detect_audio with a URL and platform to get a verdict. "
        "Supported platforms: youtube, spotify. "
        "Set use_model=true for wav2vec2 model analysis (more accurate, ~350 MB first-run download)."
    ),
)


def _build_pipeline(platform: str, use_model: bool):
    from aiblock.config import Config, DetectorConfig
    from aiblock.pipeline import build_pipeline
    from aiblock.settings import get_settings

    settings = get_settings()
    cfg = Config.from_yaml(Path(settings.default_config_path))
    if use_model:
        cfg.detectors["wav2vec2"] = DetectorConfig(
            model_id="Zeyadd-Mostafaa/Deepfake-Audio-Detection-v1",
            device="cpu",
            weight=3.0,
        )
    return build_pipeline(platform, cfg)


@mcp.tool()
async def detect_audio(url: str, platform: str, use_model: bool = False) -> dict:
    """Detect whether audio at a YouTube or Spotify URL is AI-generated.

    Args:
        url: Full YouTube or Spotify URL.
        platform: 'youtube' or 'spotify'.
        use_model: Set True to use the wav2vec2 deepfake model for higher accuracy.
                   Downloads ~350 MB on first run. Requires more time.
                   Default (False) uses spectral heuristics — fast, no download.

    Returns:
        verdict:    'AI' | 'Human' | 'Unknown'
        score:      float 0.0–1.0 (AI probability)
        confidence: float 0.0–1.0
        chunks:     number of 10-second chunks analysed
        title:      track/video title (if resolvable)
        uploader:   artist / channel name
        duration:   length in seconds
        url:        the submitted URL
        platform:   the submitted platform
    """
    from aiblock.pipeline import ADAPTER_REGISTRY

    platform = platform.lower()
    if platform not in ADAPTER_REGISTRY:
        return {"error": f"Unknown platform '{platform}'. Supported: {list(ADAPTER_REGISTRY)}"}

    loop = asyncio.get_event_loop()

    # Get metadata without downloading audio (fast, non-blocking)
    try:
        adapter = ADAPTER_REGISTRY[platform]()
        metadata = await loop.run_in_executor(None, adapter.get_metadata, url)
    except Exception:
        metadata = {}

    # Run detection pipeline in thread pool (blocking I/O + compute)
    try:
        pipeline = _build_pipeline(platform, use_model)
        result = await loop.run_in_executor(None, pipeline.run, url)
    except Exception as exc:
        log.exception("detect_audio failed for %s", url)
        return {"error": str(exc), "url": url, "platform": platform}

    return {
        **result,
        "url": url,
        "platform": platform,
        "use_model": use_model,
        **metadata,
    }


@mcp.tool()
async def get_metadata(url: str, platform: str) -> dict:
    """Get track metadata from a YouTube or Spotify URL without downloading audio.

    Useful for checking what a URL points to before running full detection.

    Args:
        url: Full YouTube or Spotify URL.
        platform: 'youtube' or 'spotify'.

    Returns:
        title:       track/video title
        uploader:    artist / channel name
        description: short description (truncated to 500 chars)
        duration:    length in seconds (None if unknown)
    """
    from aiblock.pipeline import ADAPTER_REGISTRY

    platform = platform.lower()
    if platform not in ADAPTER_REGISTRY:
        return {"error": f"Unknown platform '{platform}'. Supported: {list(ADAPTER_REGISTRY)}"}

    loop = asyncio.get_event_loop()
    adapter = ADAPTER_REGISTRY[platform]()
    try:
        return await loop.run_in_executor(None, adapter.get_metadata, url)
    except Exception as exc:
        return {"error": str(exc)}


@mcp.tool()
def list_platforms() -> list[str]:
    """List platforms supported by AIBlock for audio detection."""
    from aiblock.pipeline import ADAPTER_REGISTRY
    return list(ADAPTER_REGISTRY.keys())


def main() -> None:
    """Entry point for the aiblock-mcp command."""
    logging.basicConfig(level=logging.WARNING)
    mcp.run()  # stdio transport — works with Claude Desktop and Claude Code


if __name__ == "__main__":
    main()
