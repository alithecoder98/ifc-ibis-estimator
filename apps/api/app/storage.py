"""S3-compatible object storage client.

Garage locally; swap S3_ENDPOINT_URL/credentials for a real EU provider in staging/
prod — same boto3 client code either way, that's the point of an S3-compatible API.
"""

import io
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.client import Config

from app.core.config import get_settings


def get_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def upload_fileobj(fileobj: BinaryIO, key: str) -> None:
    settings = get_settings()
    get_s3_client().upload_fileobj(fileobj, settings.s3_bucket, key)


def download_to_path(key: str, path: Path) -> None:
    settings = get_settings()
    get_s3_client().download_file(settings.s3_bucket, key, str(path))


def upload_bytes(data: bytes, key: str) -> None:
    upload_fileobj(io.BytesIO(data), key)


def download_bytes(key: str) -> bytes:
    settings = get_settings()
    buffer = io.BytesIO()
    get_s3_client().download_fileobj(settings.s3_bucket, key, buffer)
    return buffer.getvalue()
