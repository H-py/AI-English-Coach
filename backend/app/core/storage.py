"""MinIO 对象存储客户端。

封装同步的 ``minio.Minio`` 客户端，并提供 ``ensure_bucket``（在应用启动时
确保存储桶存在且头像可公开读取）以及头像上传/URL 生成助手。
"""

import io
import json
import uuid

from minio import Minio

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 头像对象的存储前缀。
_AVATAR_PREFIX = "avatars"


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


def _avatar_public_read_policy() -> str:
    """返回允许匿名读取 ``avatars/*`` 对象的 bucket policy（JSON 字符串）。"""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [
                    f"arn:aws:s3:::{settings.MINIO_BUCKET}/{_AVATAR_PREFIX}/*"
                ],
            }
        ],
    }
    return json.dumps(policy)


def ensure_bucket() -> None:
    """如果配置的存储桶尚不存在，则创建它，并确保头像可公开读取。

    此函数在启动时由 FastAPI lifespan 调用。由于会先检查存在性，因此可
    安全地重复调用。
    """
    try:
        if not minio_client.bucket_exists(settings.MINIO_BUCKET):
            minio_client.make_bucket(settings.MINIO_BUCKET)
            logger.info("Created MinIO bucket: %s", settings.MINIO_BUCKET)
        # 允许匿名读取 avatars/* 对象，使头像 URL 可直接被浏览器访问。
        minio_client.set_bucket_policy(
            settings.MINIO_BUCKET, _avatar_public_read_policy()
        )
    except Exception as exc:  # noqa: BLE001 - 暴露任何存储初始化失败
        logger.error("Failed to ensure MinIO bucket %s: %s", settings.MINIO_BUCKET, exc)
        # 重新抛出，使 lifespan 能够明确报告启动失败。
        raise


def upload_avatar(user_id: int, content: bytes, content_type: str, ext: str) -> str:
    """将头像字节上传到 MinIO，返回对象的访问 URL。

    Args:
        user_id: 用户主键（用于对象名前缀，避免不同用户冲突）。
        content: 头像图片的原始字节。
        content_type: 图片 MIME 类型（如 ``image/png``）。
        ext: 文件扩展名（不含点，如 ``png``）。

    Returns:
        可直接在浏览器中访问的头像 URL。
    """
    object_name = f"{_AVATAR_PREFIX}/{user_id}_{uuid.uuid4().hex}.{ext}"
    minio_client.put_object(
        settings.MINIO_BUCKET,
        object_name,
        io.BytesIO(content),
        len(content),
        content_type=content_type,
    )
    scheme = "https" if settings.MINIO_SECURE else "http"
    return f"{scheme}://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET}/{object_name}"
