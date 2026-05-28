# Custom libraries
from logger import configure_logging
from integrations.office_365.attachment import Attachment
from parsers.vision_parser import VisionParser
from schemas.attachment_schema import (
    AttachmentDetail,
    AttachmentDownload,
    AttachmentReprocess,
    AttachmentResponse,
    AttachmentView,
)
from utils.common_utils import parse_identifier
from utils.document_file import DocumentFile
from utils.schema_utils import get_current_schema, get_schema_db

# Database modules
from repository.attachment_repository import AttachmentRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, Union
from uuid import UUID
import asyncio
import base64
import io
import json
import mimetypes
import os
import tempfile

# Installed libraries
from asgiref.sync import sync_to_async
from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse


load_dotenv()

logger = configure_logging(__name__)

attachment_router = APIRouter(tags=["Attachments"])


@attachment_router.get(
    "/emails/{email_uuid}/attachments", response_model=AttachmentResponse
)
def get_attachments_by_email(
    email_uuid: UUID,
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("asc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves attachment information for a specific email based on specified criteria.
    """
    try:
        attachment_repository = AttachmentRepository(db)

        filters = request.state.filters

        # Fetch all attachments for an email
        email_attachments = attachment_repository.list_attachment_by_email(
            email_data_id=email_uuid,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        if email_attachments:
            return AttachmentResponse(
                attachments=email_attachments["attachments"],
                total=email_attachments["total"],
            )
        else:
            # Specail case where we are returning emtpy list instead of 404.
            return AttachmentResponse(attachments=[], total=0)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@attachment_router.get(
    "/attachments/{attachment_identifier}", response_model=AttachmentView
)
def get_attachment(
    attachment_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves attachment information based on attachment_identifier.
    """
    try:
        attachment_repository = AttachmentRepository(db)

        attachment = attachment_repository.get_attachment_details_by_id(
            parse_identifier(attachment_identifier)
        )

        if not attachment:
            raise HTTPException(
                status_code=404,
                detail="Attachment not found. Please check and retry.",
            )

        return AttachmentView.model_validate(attachment)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@attachment_router.get(
    "/attachments/{attachment_identifier}/view", response_model=AttachmentDetail
)
def view_attachment(
    attachment_identifier: Union[UUID, str],
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves attachment information, downloads the file, stores it, and converts PDF to base64 string.
    """
    try:

        attachment_instance = Attachment(db)
        return attachment_instance.get_attachment_details(
            db=db, attachment_identifier=parse_identifier(attachment_identifier)
        )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@attachment_router.get(
    "/attachments/{attachment_identifier}/view-images",
)
async def view_attachment_images(
    attachment_identifier: Union[UUID, str],
    db: Session = Depends(get_schema_db),
) -> StreamingResponse:
    """
    Streams attachment pages if PDF as base64 encoded images based on attachment_identifier.
    """
    attachment_repository = AttachmentRepository(db)

    attachment = await sync_to_async(attachment_repository.get_attachment_by_id)(
        parse_identifier(attachment_identifier)
    )

    if not attachment:
        raise HTTPException(
            status_code=400,
            detail="Attachment not found. Please check and retry.",
        )

    if attachment.file_type != "pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF Attachments are supported for streaming. Please check and retry.",
        )

    file_content = None
    if attachment.remote_url:
        attachment_instance = Attachment(db)
        file_content = await sync_to_async(
            attachment_instance.document_file.download_file
        )(file_path=attachment.remote_url)

    if not file_content:
        raise HTTPException(
            status_code=500,
            detail="Failed to download Attachment. Please check and retry.",
        )

    async def event_generator():
        try:
            async for page_data in attachment_instance.stream_pdf_pages(file_content):
                page_data["file_name"] = attachment.file_name
                page_data["mime_type"] = "application/pdf"
                chunk = json.dumps(page_data)
                yield f"data: {chunk}\n\n".encode("utf-8")

        except asyncio.CancelledError:
            logger.info(
                f"Client disconnected from attachment stream: {attachment_identifier}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Error while streaming attachment {attachment_identifier}: {e}"
            )
            error_event = {
                "error": str(e),
                "attachment_id": attachment_identifier,
                "type": "error",
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@attachment_router.get(
    "/attachments/{attachment_identifier}/download", response_model=AttachmentDownload
)
def download_attachment(
    attachment_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Download files when S3 bucket is mounted.
    Generates presigned_url based on attachment_identifier when S3 bucket is not mounted.
    """
    try:
        attachment_repository = AttachmentRepository(db)

        existing_attachment = attachment_repository.get_attachment_by_id(
            parse_identifier(attachment_identifier)
        )
        if not existing_attachment:
            raise HTTPException(
                status_code=404,
                detail="Attachment not found. Please check and retry.",
            )

        organization_schema = get_current_schema(db)

        document_file = DocumentFile(organization_schema=organization_schema)
        file_content = document_file.download_file(
            file_path=existing_attachment.remote_url
        )

        if file_content:
            mime_type, _ = mimetypes.guess_type(existing_attachment.file_name)
            return {
                "mime_type": mime_type or "application/octet-stream",
                "file_name": existing_attachment.file_name,
                "content": base64.b64encode(file_content).decode(),
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to download Attachment. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@attachment_router.post(
    "/attachments/{attachment_uuid}/reprocess", response_model=AttachmentDetail
)
@attachment_router.post(
    "/task-api/attachments/{attachment_uuid}/reprocess", response_model=AttachmentDetail
)
def reprocess_attachment(
    attachment_uuid: UUID,
    reprocess_data: AttachmentReprocess = Body(None),
    db: Session = Depends(get_schema_db),
):
    """
    Reprocesses an existing attachment to extract it's ocr content based on attachment_uuid.
    Sets is_reprocessing flag in attachment_metadata for frontend polling.
    """
    attachment_repository = AttachmentRepository(db)
    existing_attachment = None
    attachment_metadata = {}

    try:
        existing_attachment = attachment_repository.get_attachment_by_id(
            attachment_uuid
        )
        if not existing_attachment:
            raise HTTPException(
                status_code=404,
                detail="Attachment not found. Please check and retry.",
            )

        if existing_attachment.file_type and existing_attachment.file_type.lower() != "pdf":
            raise HTTPException(
                status_code=400,
                detail="Reprocessing is only supported for PDF files.",
            )

        # Set is_reprocessing to true at the start
        attachment_metadata = dict(existing_attachment.attachment_metadata or {})
        attachment_metadata["is_reprocessing"] = True
        attachment_repository.update_attachment(
            identifier=existing_attachment.id,
            update_data={"attachment_metadata": attachment_metadata},
        )

        organization_schema = get_current_schema(db)

        document_file = DocumentFile(organization_schema=organization_schema)
        file_content = document_file.download_file(
            file_path=existing_attachment.remote_url
        )

        if not file_content:
            raise HTTPException(
                status_code=500,
                detail="Failed to download Attachment for reprocessing. Please check and retry.",
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file_path = os.path.join(temp_dir, existing_attachment.file_name)
            with open(temp_file_path, "wb") as f:
                f.write(file_content)
            logger.info(f"Downloaded file to: {temp_file_path}")

            vision_parser = VisionParser(
                organization_schema=organization_schema, db=db, mode="parsing"
            )
            parser_output = asyncio.run(
                vision_parser.parse_file(
                    file_path=temp_file_path,
                    instructions=(
                        reprocess_data.instructions
                        if reprocess_data and reprocess_data.instructions
                        else None
                    ),
                )
            )

            if not parser_output:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to reprocess Attachment. Please check and retry.",
                )

            if parser_output.extracted_data:
                logger.info(
                    f"DEBUG - First 500 chars of extracted_data[0]: {repr(parser_output.extracted_data[0][:500])}"
                )

            attachment_metadata["is_reprocessing"] = False
            result_attachment = attachment_repository.update_attachment(
                identifier=existing_attachment.id,
                update_data={
                    "content": parser_output.extracted_data,
                    "attachment_metadata": attachment_metadata,
                },
            )
            return AttachmentDetail.model_validate(result_attachment)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        if existing_attachment and attachment_metadata.get("is_reprocessing"):
            attachment_metadata["is_reprocessing"] = False
            attachment_repository.update_attachment(
                identifier=existing_attachment.id,
                update_data={"attachment_metadata": attachment_metadata},
            )
        raise http_error

    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        if existing_attachment and attachment_metadata.get("is_reprocessing"):
            attachment_metadata["is_reprocessing"] = False
            attachment_repository.update_attachment(
                identifier=existing_attachment.id,
                update_data={"attachment_metadata": attachment_metadata},
            )
        raise HTTPException(
            status_code=500, detail=f"An error occurred in reprocess_attachment: {e}"
        )
