"""Azure Blob Storage — report persistence and SAS URL generation.

Uploads reports, briefs, and signal exports to Azure Blob Storage and
returns time-limited SAS URLs that can be embedded in chat responses.

Uses DefaultAzureCredential (managed identity in Azure, CLI locally)
and User Delegation Keys for SAS generation — no storage account keys
needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
)

logger = logging.getLogger(__name__)

# Content-type mapping for common report types
_CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".json": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain; charset=utf-8",
}


class BlobReportStore:
    """Upload reports to Azure Blob Storage and return SAS URLs."""

    def __init__(
        self,
        account_url: str,
        container_name: str = "reports",
        sas_expiry_hours: int = 48,
    ):
        self._account_url = account_url
        self._container_name = container_name
        self._sas_expiry_hours = sas_expiry_hours
        self._credential = DefaultAzureCredential()
        self._service_client = BlobServiceClient(
            account_url=account_url,
            credential=self._credential,
        )
        self._container_client = self._service_client.get_container_client(
            container_name
        )
        logger.info(
            "BlobReportStore initialised: %s/%s (SAS expiry: %dh)",
            account_url,
            container_name,
            sas_expiry_hours,
        )

    def upload_text(
        self,
        content: str,
        blob_name: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload text content and return a SAS URL.

        Args:
            content: The text content to upload.
            blob_name: Blob path, e.g. "briefs/brief_20260224.md".
            content_type: MIME type (auto-detected from extension if omitted).

        Returns:
            A time-limited SAS URL for the uploaded blob.
        """
        if content_type is None:
            ext = "." + blob_name.rsplit(".", 1)[-1] if "." in blob_name else ".txt"
            content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

        blob_client = self._container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            content.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        logger.info("Uploaded text blob: %s (%d chars)", blob_name, len(content))
        return self._generate_sas_url(blob_name)

    def upload_bytes(
        self,
        data: bytes,
        blob_name: str,
        content_type: Optional[str] = None,
    ) -> str:
        """Upload binary content and return a SAS URL.

        Args:
            data: The binary content to upload (e.g. PDF bytes).
            blob_name: Blob path, e.g. "reports/horizon_202602.pdf".
            content_type: MIME type (auto-detected from extension if omitted).

        Returns:
            A time-limited SAS URL for the uploaded blob.
        """
        if content_type is None:
            ext = "." + blob_name.rsplit(".", 1)[-1] if "." in blob_name else ""
            content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

        blob_client = self._container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        logger.info("Uploaded binary blob: %s (%d bytes)", blob_name, len(data))
        return self._generate_sas_url(blob_name)

    def _generate_sas_url(self, blob_name: str) -> str:
        """Generate a read-only SAS URL using a user delegation key."""
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=self._sas_expiry_hours)

        # Get a user delegation key (valid for the SAS lifetime)
        delegation_key = self._service_client.get_user_delegation_key(
            key_start_time=now - timedelta(minutes=5),
            key_expiry_time=expiry,
        )

        sas_token = generate_blob_sas(
            account_name=self._service_client.account_name,
            container_name=self._container_name,
            blob_name=blob_name,
            user_delegation_key=delegation_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
            start=now - timedelta(minutes=5),
        )

        url = f"{self._account_url.rstrip('/')}/{self._container_name}/{blob_name}?{sas_token}"
        logger.info("Generated SAS URL for %s (expires %s)", blob_name, expiry.isoformat())
        return url
