from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import resolve_client_ip
from app.database import get_db
from app.dependencies import get_current_user
from app.schemas import UploadedAttachmentInput
from app.services import audit as audit_service
from app.services import upload as upload_service

router = APIRouter()


@router.post("/", response_model=UploadedAttachmentInput, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UploadedAttachmentInput:
    if not upload_service.is_allowed_content_type(file.content_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File type is not allowed")

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is too large")

    content, normalized_file_name, normalized_file_type = await upload_service.prepare_upload(
        file_name=file.filename or "",
        content_type=file.content_type,
        content=content,
    )

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    extension = Path(normalized_file_name).suffix
    file_name = f"{uuid4().hex}{extension}"
    target_path = upload_dir / file_name
    target_path.write_bytes(content)

    attachment = UploadedAttachmentInput(
        file_url=f"/uploads/{file_name}",
        file_name=normalized_file_name or file_name,
        file_type=normalized_file_type,
        file_size=len(content),
    )

    await audit_service.create_audit_log(
        session,
        action="upload_file",
        user_id=current_user.id,
        entity_type="file",
        details=file.filename,
        ip_address=resolve_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return attachment
