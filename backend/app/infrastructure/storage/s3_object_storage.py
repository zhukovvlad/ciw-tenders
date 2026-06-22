"""Адаптер ObjectStorage на boto3 (S3-совместимый, MinIO через endpoint_url)."""

from __future__ import annotations

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.domain.errors import StorageError
from app.domain.ports import ObjectStorage

_S3_ERRORS = (BotoCoreError, ClientError)


class S3ObjectStorage(ObjectStorage):
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        # boto3.client сети НЕ дёргает — конструирование без обращения к MinIO, поэтому
        # __init__ (вызывается в DI до try/except роута) не может уронить 500 на MinIO-down.
        self._bucket = bucket
        self._bucket_ready = False
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

    def _ensure_bucket(self) -> None:
        # Лениво и идемпотентно; вызывается ВНУТРИ put (request-путь, под общим
        # except _S3_ERRORS). head_bucket при обрыве соединения кидает EndpointConnectionError
        # (BotoCoreError) — НЕ ловится тут, уходит в put → StorageError → 503 (а не 500 из DI).
        if self._bucket_ready:
            return
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:  # бакета нет/нет доступа (НЕ обрыв соединения) → создаём
            self._client.create_bucket(Bucket=self._bucket)
        self._bucket_ready = True

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._ensure_bucket()  # ленивая проверка бакета — здесь, не в __init__
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except _S3_ERRORS as exc:  # граница: ошибки boto3 → доменный StorageError
            raise StorageError(f"put {key}: {exc}") from exc

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except _S3_ERRORS as exc:
            raise StorageError(f"get {key}: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except _S3_ERRORS as exc:
            raise StorageError(f"delete {key}: {exc}") from exc
