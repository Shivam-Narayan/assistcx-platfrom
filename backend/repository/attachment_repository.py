# Custom libraries
from logger import configure_logging
from schemas.attachment_schema import (
    AttachmentDetail,
    AttachmentPreview,
    AttachmentPreviewResponse,
    AttachmentView,
)

# Database modules
from models.attachment import Attachment

# Default libraries
from typing import Optional, Union, Dict, List
from uuid import UUID

# Installed libraries
from fastapi import HTTPException, status
from sqlalchemy import func, asc, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


logger = configure_logging(__name__)


class AttachmentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_attachment(self, attachment_data: dict) -> Optional[Attachment]:
        new_attachment = Attachment(**attachment_data)
        try:
            self.db.add(new_attachment)
            self.db.commit()
            self.db.refresh(new_attachment)
            return new_attachment
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def update_attachment(
        self, identifier: Union[UUID, str], update_data: dict
    ) -> Optional[Attachment]:
        query_filter = (
            Attachment.id == identifier
            if isinstance(identifier, UUID)
            else Attachment.external_id == identifier
        )
        attachment = self.db.query(Attachment).filter(query_filter).first()
        if not attachment:
            return None

        try:
            for key, value in update_data.items():
                if hasattr(attachment, key):
                    setattr(attachment, key, value)
            self.db.commit()
            self.db.refresh(attachment)
            return attachment
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def create_or_update_attachment(self, data: dict) -> Optional[Attachment]:
        identifier = data.get("id") or data.get("external_id")
        if not identifier:
            raise ValueError(
                "Either UUID or external_id is required for attachment operations"
            )

        # Determine the type of identifier and construct the appropriate query filter
        query_filter = (
            Attachment.id == identifier
            if isinstance(identifier, UUID)
            else Attachment.external_id == identifier
        )

        try:
            existing_attachment = self.db.query(Attachment).filter(query_filter).first()
            if existing_attachment:
                return self.update_attachment(identifier, data)
            else:
                return self.create_attachment(data)
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_attachment_by_id(
        self, identifier: Union[UUID, str]
    ) -> Optional[Attachment]:
        query_filter = (
            Attachment.id == identifier
            if isinstance(identifier, UUID)
            else Attachment.external_id == identifier
        )
        try:
            return self.db.query(Attachment).filter(query_filter).first()
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_attachment_details_by_id(
        self, identifier: Union[UUID, str]
    ) -> Optional[AttachmentView]:
        query_filter = (
            Attachment.id == identifier
            if isinstance(identifier, UUID)
            else Attachment.external_id == identifier
        )
        try:
            return (
                self.db.query(
                    Attachment.id,
                    Attachment.email_data_id,
                    Attachment.external_id,
                    Attachment.message_id,
                    Attachment.conversation_id,
                    Attachment.file_name,
                    Attachment.file_type,
                    Attachment.size,
                    Attachment.remote_url,
                    Attachment.content,
                    # Attachment.ocr_content,
                    Attachment.template_class,
                    Attachment.structured_output,
                    Attachment.attachment_metadata,
                    # Attachment.ai_output,
                    Attachment.created_at,
                    Attachment.updated_at,
                )
                .filter(query_filter)
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def get_attachment_preview_by_id(self, attachment_id: UUID) -> AttachmentPreview:
        try:
            attachment = (
                self.db.query(Attachment).filter(Attachment.id == attachment_id).first()
            )

            if not attachment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Attachment with ID {attachment_id} not found. Please check and retry.",
                )
            return AttachmentPreview.model_validate(attachment)

        except SQLAlchemyError as e:
            logger.error(
                f"Database error while fetching attachment {attachment_id}: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred while fetching attachment preview.",
            )

        except Exception as e:
            logger.error(f"Unexpected error in get_attachment_preview_by_id: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unexpected error occurred while fetching attachment preview.",
            )

    def get_attachments_preview_by_ids(
        self, attachment_ids: List[UUID]
    ) -> Dict[UUID, AttachmentPreview]:
        """
        OPTIMIZED: Batch fetch attachment previews for multiple attachment IDs.

        Performance: For N attachments:
        - Before: N queries (1 per attachment)
        - After: 1 query total

        Args:
            attachment_ids: List of attachment UUIDs to fetch

        Returns:
            Dictionary mapping attachment_id to AttachmentPreview
        """
        if not attachment_ids:
            return {}

        try:
            # Batch fetch all attachments (1 query)
            attachments = (
                self.db.query(Attachment)
                .filter(Attachment.id.in_(attachment_ids))
                .all()
            )

            # Convert to AttachmentPreview and create lookup map
            result = {}
            for attachment in attachments:
                try:
                    result[attachment.id] = AttachmentPreview.model_validate(attachment)
                except Exception as e:
                    logger.warning(
                        f"Failed to validate attachment {attachment.id}: {e}"
                    )
                    # Skip invalid attachments instead of failing the entire operation
                    continue

            return result

        except SQLAlchemyError as e:
            logger.error(f"Database error in get_attachments_preview_by_ids: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error in get_attachments_preview_by_ids: {e}")
            return {}

    def get_attachment_by_email(
        self,
        email_data_id: UUID,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> List[AttachmentDetail]:
        query = self.db.query(Attachment)

        # Fetch data for specific email
        query = query.filter(Attachment.email_data_id == email_data_id)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Attachment, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(Attachment, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Attachment, key) == values)

        # Apply sorting
        if hasattr(Attachment, sort_by):
            order = (
                asc(getattr(Attachment, sort_by))
                if sort_order == "asc"
                else desc(getattr(Attachment, sort_by))
            )
            query = query.order_by(order)

        try:
            attachments = query.all()
            return attachments
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    def list_attachment_by_email(
        self,
        email_data_id: UUID,
        filters: Optional[Dict[str, any]] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> AttachmentPreviewResponse:
        """
        For future reference to return optimized version of attachment listing.
        """
        query = self.db.query(
            Attachment.id,
            Attachment.email_data_id,
            Attachment.external_id,
            Attachment.message_id,
            Attachment.conversation_id,
            Attachment.file_name,
            Attachment.file_type,
            Attachment.size,
            Attachment.remote_url,
            Attachment.created_at,
            Attachment.updated_at,
        )

        # Fetch data for specific email
        query = query.filter(Attachment.email_data_id == email_data_id)

        # Apply filters
        if filters:
            for key, values in filters.items():
                if hasattr(Attachment, key):
                    if isinstance(values, list):
                        # Handle multiple values for the same filter key
                        condition = or_(
                            *(getattr(Attachment, key) == value for value in values)
                        )
                        query = query.filter(condition)
                    else:
                        query = query.filter(getattr(Attachment, key) == values)

        # Apply sorting
        if hasattr(Attachment, sort_by):
            order = (
                asc(getattr(Attachment, sort_by))
                if sort_order == "asc"
                else desc(getattr(Attachment, sort_by))
            )
            query = query.order_by(order)

        try:
            attachments = query.all()
            total = query.count()
            return {"attachments": attachments, "total": total}
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return None

    def list_attachments_by_email_ids(
        self, email_ids: List[UUID]
    ) -> Dict[UUID, Dict[str, any]]:
        """
        Batch fetch attachments for multiple emails at once.

        OPTIMIZED: Single query with IN clause instead of N separate queries.
        Used by get_all_emails() to eliminate N+1 query problem.

        Args:
            email_ids: List of email UUIDs

        Returns:
            Dict mapping email_id -> attachment data dict
            Example: {
                UUID('...'): {"attachments": [...], "total": 3},
                ...
            }
        """
        if not email_ids:
            return {}

        try:
            # Single query to fetch all attachments for all emails
            attachments = (
                self.db.query(
                    Attachment.id,
                    Attachment.email_data_id,
                    Attachment.external_id,
                    Attachment.message_id,
                    Attachment.conversation_id,
                    Attachment.file_name,
                    Attachment.file_type,
                    Attachment.size,
                    Attachment.remote_url,
                    Attachment.created_at,
                    Attachment.updated_at,
                )
                .filter(Attachment.email_data_id.in_(email_ids))
                .order_by(desc(Attachment.updated_at))
                .all()
            )

            # Group attachments by email_id
            attachments_by_email = {}
            for attachment in attachments:
                email_id = attachment.email_data_id
                if email_id not in attachments_by_email:
                    attachments_by_email[email_id] = []
                attachments_by_email[email_id].append(attachment)

            # Build result dict with same structure as list_attachment_by_email
            result = {}
            for email_id in email_ids:
                email_attachments = attachments_by_email.get(email_id, [])
                result[email_id] = {
                    "attachments": email_attachments,
                    "total": len(email_attachments),
                }

            return result

        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error in list_attachments_by_email_ids: {e}")
            # Return empty attachments for all emails
            return {email_id: {"attachments": [], "total": 0} for email_id in email_ids}

    def get_single_attachment(self, email_data_id: UUID) -> List[Attachment]:
        try:
            return (
                self.db.query(Attachment)
                .filter(Attachment.email_data_id == email_data_id)
                .order_by(func.length(Attachment.content[0]).desc())
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"SQLAlchemy Error: {e}")
            return []

    # def update_ai_content(
    #     self, message_id: str, ai_content: str
    # ) -> Optional[Attachment]:
    #     try:
    #         # Find the attachment by message_id
    #         attachment = (
    #             self.db.query(Attachment)
    #             .filter(Attachment.message_id == message_id)
    #             .one()
    #         )
    #     except SQLAlchemyError as e:
    #         logger.error(f"SQLAlchemy Error while querying: {e}")
    #         return None

    #     # Update the ai_content field
    #     try:
    #         attachment.ai_content = ai_content
    #         self.db.commit()
    #         self.db.refresh(attachment)
    #         return attachment
    #     except SQLAlchemyError as e:
    #         self.db.rollback()
    #         logger.error(f"SQLAlchemy Error while updating: {e}")
    #         return None
