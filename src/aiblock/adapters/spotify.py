"""Spotify adapter using spotdl.

spotdl resolves Spotify track metadata and sources audio from YouTube,
so no Spotify API credentials are required.
"""

import subprocess
from pathlib import Path

from aiblock.adapters.base import PlatformAdapter


class SpotifyAdapter(PlatformAdapter):
    """Download audio for a Spotify track/album/playlist URL via spotdl."""

    def fetch(self, url: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [
                "spotdl",
                "download",
                url,
                "--output", str(output_dir / "{title}"),
                "--format", "mp3",
                "--bitrate", "192k",
            ],
            capture_output=True,
            text=True,
            cwd=str(output_dir),
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"spotdl failed (exit {result.returncode}):\n{result.stderr}"
            )

        mp3_files = sorted(output_dir.glob("*.mp3"))
        if not mp3_files:
            raise FileNotFoundError(
                f"spotdl ran successfully but no .mp3 found in {output_dir}.\n"
                f"spotdl output:\n{result.stdout}"
            )

        return mp3_files[0]

    def get_metadata(self, url: str) -> dict:
        """Extract Spotify track metadata without downloading audio.

        Uses spotdl's Python API to resolve track info from Spotify.
        Falls back to empty dict on any failure.
        """
        try:
            from spotdl.utils.spotify import SpotifyClient
            from spotdl import Song

            # SpotifyClient.init is idempotent — safe to call multiple times
            SpotifyClient.init(
                client_id="",
                client_secret="",
                user_auth=False,
                no_cache=True,
            )
            song = Song.from_url(url)
            return {
                "title": song.name or "",
                "uploader": song.artist or "",
                "description": f"Album: {song.album_name}" if song.album_name else "",
                "duration": song.duration,
            }
        except Exception:
            return {}
