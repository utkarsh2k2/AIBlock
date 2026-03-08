"""YouTube adapter using yt-dlp."""

from pathlib import Path

from aiblock.adapters.base import PlatformAdapter


class YouTubeAdapter(PlatformAdapter):
    """Download best-quality audio from a YouTube URL via yt-dlp."""

    def fetch(self, url: str, output_dir: Path) -> Path:
        try:
            import yt_dlp
        except ImportError as e:
            raise ImportError("yt-dlp is required: pip install yt-dlp") from e

        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / "%(id)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id", "audio")

        output_path = output_dir / f"{video_id}.mp3"
        if not output_path.exists():
            candidates = sorted(output_dir.glob(f"{video_id}.*"))
            if not candidates:
                raise FileNotFoundError(f"Downloaded file not found in {output_dir}")
            output_path = candidates[0]

        return output_path

    def get_metadata(self, url: str) -> dict:
        """Extract YouTube video metadata without downloading audio.

        Uses yt-dlp's extract_info with download=False — no audio is fetched.
        yt-dlp handles YouTube's JS rendering correctly; raw HTTP fetch does not.
        """
        try:
            import yt_dlp
        except ImportError:
            return {}

        ydl_opts = {"quiet": True, "no_warnings": True}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", ""),
                "uploader": info.get("uploader", ""),
                "description": (info.get("description") or "")[:500],
                "duration": info.get("duration"),
                "view_count": info.get("view_count"),
                "upload_date": info.get("upload_date"),
            }
        except Exception:
            return {}
