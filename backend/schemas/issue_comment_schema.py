# Default libraries
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints
from typing_extensions import Annotated


# ==================== Issue Comment Schemas ====================

class IssueCommentBase(BaseModel):
    comment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]  # type: ignore
    comment_metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class IssueCommentCreate(IssueCommentBase):
    issue_id: UUID


class IssueCommentUpdate(IssueCommentBase):
    comment: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = None  # type: ignore


class IssueCommentDetail(IssueCommentBase):
    id: UUID
    issue_id: UUID
    user_id: UUID
    user_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


