from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, UploadFile

from aimg.api.dependencies import get_current_user, get_db_pool, get_s3_client, get_settings
from aimg.api.envelope import ApiResponse
from aimg.api.errors import ForbiddenError, InvalidFileError, NotFoundError
from aimg.common.logging import request_id_var
from aimg.common.settings import Settings
from aimg.db.models import User
from aimg.db.repos.files import FileRepo

router = APIRouter(prefix="/v1/files", tags=["files"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("", status_code=201)
async def upload_file(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    s3_client: object = Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    content = await file.read()
    size = len(content)
    if size == 0:
        raise InvalidFileError("Empty file")
    if size > MAX_FILE_SIZE:
        raise InvalidFileError(f"File too large: {size} bytes (max {MAX_FILE_SIZE})")

    content_type = file.content_type or "application/octet-stream"
    original_filename = file.filename or "upload"

    s3_key = (
        f"{user.integration_id}/uploads/{original_filename}"
    )

    await s3_client.put_object(
        Bucket=settings.s3_bucket,
        Key=s3_key,
        Body=content,
        ContentType=content_type,
    )

    file_repo = FileRepo(db_pool)
    file_record = await file_repo.create(
        integration_id=user.integration_id,
        user_id=user.id,
        s3_bucket=settings.s3_bucket,
        s3_key=s3_key,
        content_type=content_type,
        size_bytes=size,
        purpose="input",
        original_filename=original_filename,
    )

    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data={
            "file_id": str(file_record.id),
            "original_filename": file_record.original_filename,
            "content_type": file_record.content_type,
            "size_bytes": file_record.size_bytes,
        },
    ).model_dump(mode="json")


@router.get("/{file_id}")
async def get_file(
    file_id: UUID,
    user: User = Depends(get_current_user),
    db_pool: asyncpg.Pool = Depends(get_db_pool),
    s3_client: object = Depends(get_s3_client),
    settings: Settings = Depends(get_settings),
) -> dict:
    file_repo = FileRepo(db_pool)
    file_record = await file_repo.get_by_id(file_id)
    if not file_record:
        raise NotFoundError("File not found")
    if file_record.integration_id != user.integration_id:
        raise ForbiddenError("Access denied to this file")

    download_url = await s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": file_record.s3_bucket, "Key": file_record.s3_key},
        ExpiresIn=settings.s3_presign_ttl,
    )

    expires_at = datetime.now(UTC) + timedelta(seconds=settings.s3_presign_ttl)

    rid = request_id_var.get() or ""
    return ApiResponse(
        request_id=rid,
        success=True,
        data={
            "file_id": str(file_record.id),
            "download_url": download_url,
            "content_type": file_record.content_type,
            "original_filename": file_record.original_filename,
            "size_bytes": file_record.size_bytes,
            "expires_at": expires_at.isoformat(),
        },
    ).model_dump(mode="json")
