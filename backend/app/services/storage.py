from __future__ import annotations

from datetime import timedelta

from google.cloud import exceptions as gcs_exceptions
from google.auth import exceptions as auth_exceptions
from google.cloud import storage


class StorageServiceError(RuntimeError):
    """Base error for storage service issues."""


class StorageService:
    def __init__(self) -> None:
        self._client: storage.Client | None = None

    def _get_client(self) -> storage.Client:
        if self._client is None:
            try:
                self._client = storage.Client()
            except auth_exceptions.DefaultCredentialsError as exc:
                raise StorageServiceError(
                    "Failed to initialize Google Cloud Storage client. "
                    "Ensure application default credentials are configured."
                ) from exc
        return self._client

    def generate_upload_signed_url(
        self,
        bucket_name: str,
        object_name: str,
        content_type: str,
        expiration_seconds: int,
    ) -> str:
        client = self._get_client()
        try:
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(object_name)
            return blob.generate_signed_url(
                version="v4",
                expiration=timedelta(seconds=expiration_seconds),
                method="PUT",
                content_type=content_type,
            )
        except gcs_exceptions.GoogleCloudError as exc:
            raise StorageServiceError(
                f"Failed to generate signed URL for {bucket_name}/{object_name}: {exc}"
            ) from exc


storage_service = StorageService()
