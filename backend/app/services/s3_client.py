"""Shared boto3 S3 client factory.

Built once and reused — never constructed per-request. Credentials always
come from boto3's standard provider chain (environment, shared config,
instance/container metadata, and — in ECS/Fargate, Fase 4B — the task's IAM
role). This module never accepts or reads an access key/secret key; there is
intentionally no such setting in `app.core.config.Settings`.
"""

from functools import lru_cache

from app.core.config import settings


@lru_cache
def get_s3_client():
    import boto3
    from botocore.config import Config

    config = Config(
        connect_timeout=settings.s3_connect_timeout_seconds,
        read_timeout=settings.s3_read_timeout_seconds,
        retries={"max_attempts": settings.s3_max_attempts, "mode": "standard"},
        s3={"addressing_style": "virtual"},
        # SigV4 explicitly: the region-implicit default can fall back to the
        # legacy SigV2 signer for us-east-1, which cannot presign
        # SSE-KMS-encrypted objects and produces different (undocumented)
        # query params than the rest of AWS's regions — never rely on it.
        signature_version="s3v4",
    )
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.s3_endpoint_url or None,
        config=config,
    )
