"""MinIO object storage client.

Wraps the synchronous ``minio.Minio`` client and provides ``ensure_bucket``
which is called during application startup to guarantee the configured
bucket exists before serving traffic.
"""

from minio import Minio

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_minio_client() -> Minio:
    """Construct and return a configured MinIO client."""
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


# A module-level client reused across the application.
minio_client: Minio = get_minio_client()


def ensure_bucket() -> None:
    """Create the configured bucket if it does not already exist.

    This is invoked from the FastAPI lifespan on startup. It is safe to call
    repeatedly because existence is checked first.
    """
    try:
        if not minio_client.bucket_exists(settings.MINIO_BUCKET):
            minio_client.make_bucket(settings.MINIO_BUCKET)
            logger.info("Created MinIO bucket: %s", settings.MINIO_BUCKET)
        else:
            logger.debug("MinIO bucket already exists: %s", settings.MINIO_BUCKET)
    except Exception as exc:  # noqa: BLE001 - surface any storage init failure
        logger.error("Failed to ensure MinIO bucket %s: %s", settings.MINIO_BUCKET, exc)
        # Re-raise so the lifespan clearly reports startup failure.
        raise
