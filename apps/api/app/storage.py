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
        config=Config(
            signature_version="s3v4",
            # botocore 1.36+ defaults to opportunistically validating S3
            # response checksums whenever the server advertises support.
            # Garage (and other S3-compatible backends - MinIO, Ceph, etc.)
            # compute checksums for multipart-uploaded objects differently
            # than real AWS S3, so botocore's own recomputed checksum never
            # matches and every object above boto3's default ~8MB multipart
            # threshold fails to download with a ChecksumError - confirmed
            # live: every real-world IFC file over 8MB failed this way,
            # every file under it succeeded. "when_required" restores the
            # pre-1.36 behavior (only validate when an operation explicitly
            # requires it), which is AWS's own documented fix for non-AWS
            # S3-compatible endpoints.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
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
