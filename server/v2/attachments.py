from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response

from server.modules.attachments import (
    AttachmentLinkIn,
    AttachmentPatch,
    attachment_events,
    attachment_file,
    create_attachment_link,
    delete_attachment,
    delete_attachment_link,
    export_attachments_csv,
    get_attachment,
    list_attachments,
    patch_attachment,
    restore_attachment,
    upload_attachment,
)
from server.modules.auth import AuthContext, request_context


router = APIRouter(prefix="/attachments", tags=["v2-attachments"])


@router.get("")
def attachment_ledger(
    q: str = Query(default=""), category: str = Query(default=""),
    entity_type: str = Query(default="", alias="entityType"),
    entity_id: str = Query(default="", alias="entityId"),
    include_deleted: bool = Query(default=False, alias="includeDeleted"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(request_context),
):
    return list_attachments(q=q, category=category, entity_type=entity_type, entity_id=entity_id, include_deleted=include_deleted, limit=limit, offset=offset, context=context)


@router.get("/export.csv")
def export_attachment_ledger(context: AuthContext = Depends(request_context)) -> Response:
    return Response(content=export_attachments_csv(context), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=attachments.csv"})


@router.post("")
async def create_attachment(
    file: UploadFile = File(...), category: str = Form(default="document"),
    description: str = Form(default=""), context: AuthContext = Depends(request_context),
):
    return await upload_attachment(file, category, description, context)


@router.post("/links")
def link_attachment(payload: AttachmentLinkIn, context: AuthContext = Depends(request_context)):
    return create_attachment_link(payload, context)


@router.delete("/links/{link_id}")
def unlink_attachment(link_id: str, context: AuthContext = Depends(request_context)):
    return delete_attachment_link(link_id, context)


@router.get("/{attachment_id}")
def attachment_detail(attachment_id: str, context: AuthContext = Depends(request_context)):
    return get_attachment(attachment_id, context, include_deleted=True)


@router.patch("/{attachment_id}")
def update_attachment(attachment_id: str, payload: AttachmentPatch, context: AuthContext = Depends(request_context)):
    return patch_attachment(attachment_id, payload, context)


@router.delete("/{attachment_id}")
def remove_attachment(attachment_id: str, context: AuthContext = Depends(request_context)):
    return delete_attachment(attachment_id, context)


@router.post("/{attachment_id}/restore")
def restore_deleted_attachment(attachment_id: str, context: AuthContext = Depends(request_context)):
    return restore_attachment(attachment_id, context)


@router.get("/{attachment_id}/events")
def attachment_event_ledger(attachment_id: str, context: AuthContext = Depends(request_context)):
    return attachment_events(attachment_id, context)


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: str, context: AuthContext = Depends(request_context)) -> FileResponse:
    path, record = attachment_file(attachment_id, context)
    return FileResponse(path, media_type=record.get("contentType") or "application/octet-stream", filename=record["originalName"])
