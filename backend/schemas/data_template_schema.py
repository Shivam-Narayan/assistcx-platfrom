# Default libraries
from datetime import datetime
from typing import Optional, List
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


class DataSchema(BaseModel):
    name: str
    data_type: Optional[str] = "string"
    keywords: Optional[List[str]] = []
    description: str
    field_schema: Optional[List[dict]] = []


class DataTemplateBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    template_class: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: Optional[str] = None
    document_instructions: Optional[List[str]] = None
    data_schema: Optional[List[DataSchema]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    @field_validator("name", "template_class")
    def validate_name(cls, v):
        # Check if contains only letters, numbers, underscores, hyphens, and periods
        if v and not all(c.isalnum() or c in ("_", "-", ".", " ") for c in v):
            raise ValueError(
                "Name can only contain letters, numbers, underscores, hyphens, and periods"
            )
        return v


class DataTemplateCreate(DataTemplateBase):
    pass


class DataTemplateUpdate(DataTemplateBase):
    template_class: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore

    @field_validator("template_class", mode="before")
    def force_template_class_none(cls, v):
        # Always set template_class to None to avoid updating it
        return None


class DataTemplateDetail(DataTemplateBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DataTemplateResponse(BaseModel):
    data_templates: List[DataTemplateDetail]
    total: int


class DataSchemaBuilder(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: str
    previous_schema: Optional[List[DataSchema]] = None
    user_instructions: Optional[str] = None

    @field_validator("name")
    def validate_name(cls, v):
        if v and not all(c.isalnum() or c in ("_", "-", ".", " ") for c in v):
            raise ValueError(
                "Name can only contain letters, numbers, underscores, hyphens, and periods"
            )
        return v


class DataSchemaBuilderDetail(BaseModel):
    name: str
    description: str
    data_schema: List[DataSchema]
