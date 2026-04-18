"""
Async S3 client for Live Guide audio storage.

No existing S3 client in project — created fresh using aioboto3.

Key layout:
  guide/audio/{zone_id}/{point_id}/{voice_id}/{language}/{detail_level}/{content_type}_{variant_index}.mp3
  guide/preview/{block_id}.mp3

CDN URL = settings.aws_cdn_base_url + "/" + key
"""
import logging

import aioboto3

from src.config import settings

logger = logging.getLogger(__name__)


class GuideS3Client:
    """Thin async S3 client for guide audio files."""

    def __init__(self) -> None:
        self._session = aioboto3.Session(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self._bucket = settings.aws_s3_bucket
        self._cdn_base = settings.aws_cdn_base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Upload / Delete
    # ------------------------------------------------------------------

    async def upload_audio(
        self,
        key: str,
        data: bytes,
        content_type: str = "audio/mpeg",
    ) -> str:
        """Upload audio bytes to S3, return public CDN URL."""
        async with self._session.client("s3") as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                CacheControl="public, max-age=31536000",  # 1 year — content is immutable
            )
        cdn_url = f"{self._cdn_base}/{key}"
        logger.debug("Uploaded %d bytes → %s", len(data), cdn_url)
        return cdn_url

    async def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a time-limited presigned GET URL (for private preview access)."""
        async with self._session.client("s3") as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )

    async def delete_audio(self, key: str) -> None:
        """Delete a single audio file from S3."""
        async with self._session.client("s3") as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)
        logger.debug("Deleted S3 key: %s", key)

    # ------------------------------------------------------------------
    # Key builders
    # ------------------------------------------------------------------

    @staticmethod
    def build_content_audio_key(
        zone_id: str,
        point_id: str,
        voice_id: str,
        language: str,
        content_type: str,
        variant_index: int,
        detail_level: str = "standard",
    ) -> str:
        """Build S3 key for a pre-recorded content block.

        Format: guide/audio/{zone_id}/{point_id}/{voice_id}/{language}/{detail_level}/{content_type}_{variant_index}.mp3

        detail_level is part of the path so brief/standard variants never clash.
        """
        return (
            f"guide/audio/{zone_id}/{point_id}/{voice_id}"
            f"/{language}/{detail_level}/{content_type}_{variant_index}.mp3"
        )

    @staticmethod
    def build_preview_key(block_id: str) -> str:
        """Build S3 key for a short preview/sample audio clip."""
        return f"guide/preview/{block_id}.mp3"
