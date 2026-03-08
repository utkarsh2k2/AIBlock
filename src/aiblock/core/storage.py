"""S3-compatible object storage for audio files.

Uses boto3. Compatible with AWS S3, Cloudflare R2, and MinIO.
Set S3_ENDPOINT_URL in environment for non-AWS providers.

Files are stored at: aiblock-audio/{platform}/{url_hash}.mp3
TTL enforcement is done via S3 lifecycle rules (set them once in the console).
"""

import hashlib
from pathlib import Path
from typing import Optional

from aiblock.settings import get_settings


def _url_key(url: str, platform: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:32]
    return f"{platform}/{digest}.mp3"


def _get_client():
    import boto3

    settings = get_settings()
    kwargs: dict = {
        "region_name": settings.s3_region,
    }
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url

    return boto3.client("s3", **kwargs)


def upload_audio(local_path: Path, url: str, platform: str) -> str:
    """Upload audio file to S3. Returns the S3 key."""
    settings = get_settings()
    key = _url_key(url, platform)
    _get_client().upload_file(
        str(local_path),
        settings.s3_bucket,
        key,
        ExtraArgs={"ContentType": "audio/mpeg"},
    )
    return key


def download_audio(url: str, platform: str, dest: Path) -> Optional[Path]:
    """Download audio from S3 to `dest`. Returns path on success, None if not found."""
    settings = get_settings()
    key = _url_key(url, platform)
    dest_path = dest / Path(key).name
    try:
        _get_client().download_file(settings.s3_bucket, key, str(dest_path))
        return dest_path
    except Exception:
        return None


def audio_exists(url: str, platform: str) -> bool:
    """Check whether audio for this URL is already cached in S3."""
    settings = get_settings()
    key = _url_key(url, platform)
    try:
        _get_client().head_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except Exception:
        return False
