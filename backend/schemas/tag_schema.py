# Default libraries
from datetime import datetime
from typing import Optional, Dict, Any
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints


class TagBase(BaseModel):
    name: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, pattern=r"^[a-zA-Z0-9 ]+$"
        ),
    ]
    description: Optional[str] = None
    color: Optional[str] = None  # hex color like "#FFFFFF"
    tag_metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class TagCreate(TagBase):
    pass


class TagUpdate(TagBase):
    name: Optional[
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True, min_length=1, pattern=r"^[a-zA-Z0-9 ]+$"
            ),
        ]
    ] = None


class TagDetail(TagBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
