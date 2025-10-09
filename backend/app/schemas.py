from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TenderStatus(str, Enum):
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class UploadLimits(BaseModel):
    max_file_size_bytes: int = Field(..., description="Maximum allowed file size per upload in bytes.")
    allowed_mime_types: list[str] = Field(..., description="List of permitted MIME types.")
    max_files: Optional[int] = Field(
        None, description="Optional cap on number of files per tender session (None means unlimited)."
    )


class FileRecord(BaseModel):
    file_id: UUID
    original_name: str
    stored_name: str
    content_type: str
    size_bytes: int
    storage_uri: Optional[str] = Field(
        None, description="gs:// URI where the file is stored once upload completes."
    )
    status: Literal["pending", "uploading", "uploaded", "failed"] = "pending"
    uploaded_at: Optional[datetime] = None
    error: Optional[str] = None


class ParseMetadata(BaseModel):
    operation_name: Optional[str] = Field(default=None, alias="operationName")
    input_prefix: Optional[str] = Field(default=None, alias="inputPrefix")
    output_prefix: Optional[str] = Field(default=None, alias="outputPrefix")
    output_uri: Optional[str] = Field(default=None, alias="outputUri")
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    completed_at: Optional[datetime] = Field(default=None, alias="completedAt")
    last_checked_at: Optional[datetime] = Field(default=None, alias="lastCheckedAt")
    error: Optional[str] = None

    class Config:
        populate_by_name = True


class TenderSession(BaseModel):
    tender_id: UUID
    status: TenderStatus
    created_at: datetime
    created_by: Optional[str] = None
    files: list[FileRecord] = Field(default_factory=list)
    parse: ParseMetadata = Field(default_factory=ParseMetadata)


class CreateTenderResponse(BaseModel):
    tender_id: UUID = Field(..., serialization_alias="tenderId")
    status: TenderStatus
    upload_limits: UploadLimits = Field(..., alias="uploadLimits")

    class Config:
        populate_by_name = True


class CreateTenderRequest(BaseModel):
    created_by: Optional[str] = Field(default=None, alias="createdBy")

    class Config:
        populate_by_name = True


class TenderStatusResponse(BaseModel):
    tender_id: UUID = Field(..., serialization_alias="tenderId")
    status: TenderStatus
    files: list[FileRecord]
    created_at: datetime = Field(..., alias="createdAt")
    parse: ParseMetadata

    class Config:
        populate_by_name = True


class UploadInitRequest(BaseModel):
    filename: str
    size_bytes: int = Field(..., alias="sizeBytes", gt=0)
    content_type: str = Field(..., alias="contentType")

    class Config:
        populate_by_name = True


class UploadInitResponse(BaseModel):
    file_id: UUID = Field(..., alias="fileId")
    upload_url: str = Field(..., alias="uploadUrl")
    required_headers: dict[str, str] = Field(default_factory=dict, alias="requiredHeaders")
    storage_path: str = Field(..., alias="storagePath")
    storage_uri: str = Field(..., alias="storageUri")

    class Config:
        populate_by_name = True


class UploadCompletionRequest(BaseModel):
    status: Literal["uploaded", "failed"] = "uploaded"
    error: Optional[str] = None
