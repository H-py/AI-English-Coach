"""MinIO 对象存储客户端。

封装同步的 ``minio.Minio`` 客户端，并提供 ``ensure_bucket``，该函数在
应用启动时被调用，以确保配置的存储桶在服务流量之前已经存在。
"""

from minio import Minio

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_minio_client() -> Minio:
    """构造并返回一个配置好的 MinIO 客户端。"""
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


# 在应用范围内复用的模块级客户端。
minio_client: Minio = get_minio_client()


def ensure_bucket() -> None:
    """如果配置的存储桶尚不存在，则创建它。

    此函数在启动时由 FastAPI lifespan 调用。由于会先检查存在性，因此可
    安全地重复调用。
    """
    try:
        if not minio_client.bucket_exists(settings.MINIO_BUCKET):
            minio_client.make_bucket(settings.MINIO_BUCKET)
            logger.info("Created MinIO bucket: %s", settings.MINIO_BUCKET)
        else:
            logger.debug("MinIO bucket already exists: %s", settings.MINIO_BUCKET)
    except Exception as exc:  # noqa: BLE001 - 暴露任何存储初始化失败
        logger.error("Failed to ensure MinIO bucket %s: %s", settings.MINIO_BUCKET, exc)
        # 重新抛出，使 lifespan 能够明确报告启动失败。
        raise
