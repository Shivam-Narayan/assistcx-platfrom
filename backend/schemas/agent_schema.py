# Custom libraries
# from schemas.intent_schema import IntentBase  # intent_schema.py commented out — use Dict for import/export payload
from schemas.data_template_schema import DataTemplateBase

# Default libraries
from datetime import datetime
from typing import Optional, Any, Dict, List, Literal, Union
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


class Tool(BaseModel):
    name: str
    action: str
    description: Optional[str] = None
    integration_key: Optional[str] = None
    is_default: Optional[bool] = False
    icon: Optional[str] = None
    human_review: Optional[bool] = False
    review_rules: Optional[List[str]] = None


class Plan(BaseModel):
    id: int
    step_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]
    condition: str = ""
    action: Union[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)],
        List[str],
    ]
    rules: Optional[List[str]] = None
    tool: Optional[Union[str, List[str]]] = None


class Knowledge(BaseModel):
    collection_id: str
    name: str
    index_name: str


class DataStore(BaseModel):
    storage_type: Annotated[str, StringConstraints(strip_whitespace=True)]
    storage_bucket: Annotated[str, StringConstraints(strip_whitespace=True)]
    storage_folder: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True)]
    ] = "files"
    storage_region: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True)]
    ] = ""


class AgentBase(BaseModel):
    icon: Optional[str] = "shapes"
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    goal: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10)]  # type: ignore
    style: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10)]  # type: ignore
    instructions: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10)]  # type: ignore
    rules: Optional[List[str]] = None
    success_criteria: Optional[str] = None
    tools: List[Tool]
    plan: Optional[List[Plan]] = None
    knowledge_base: Optional[List[Knowledge]] = None
    response_schema: Optional[List[Dict[str, Any]]] = None
    data_templates: Optional[List[str]] = None
    skills: Optional[List[Dict[str, Any]]] = None
    class_groups: Optional[List[str]] = None
    data_store: Optional[DataStore] = None
    examples: Optional[List[str]] = None
    agent_mailbox: Optional[str] = None
    # intent_class: Optional[str] = None
    agent_llm: Optional[str] = None
    agent_config: Optional[Dict[str, Any]] = None
    reviewers: Optional[List[str]] = None
    status: Optional[str] = "ACTIVE"

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    @field_validator("name")
    def validate_name(cls, v):
        # Check if contains only letters, numbers, underscores, hyphens, and periods
        if v and not all(c.isalnum() or c in ("_", "-", ".", " ") for c in v):
            raise ValueError(
                "Name can only contain letters, numbers, underscores, hyphens, and periods"
            )
        return v


class AgentCreate(AgentBase):
    pass


class AgentUpdate(AgentBase):
    pass


class AgentDetail(AgentBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentResponse(BaseModel):
    agents: List[AgentDetail]
    total: int


class AgentPreview(BaseModel):
    id: UUID
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10)]  # type: ignore
    goal: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10)]  # type: ignore
    instructions: str
    rules: List[str]
    tools: List[Tool]
    plan: Optional[List[Plan]] = None
    icon: Optional[str] = None
    agent_config: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class AgentPreviewResponse(BaseModel):
    agent_previews: List[AgentPreview]
    total: int


class AgentExportBase(AgentBase):
    data_store: Optional[DataStore] = None

    @field_validator(
        "agent_mailbox", "agent_config", "data_store", "knowledge_base", mode="before"
    )
    def set_null_fields(cls, _, info):
        return None  # None for agent_mailbox, agent_config, data_store


class AgentExport(BaseModel):
    agent: AgentExportBase
    # intent: Optional[IntentBase] = None
    data_templates: Optional[List[DataTemplateBase]] = None


class AgentImport(BaseModel):
    agent: AgentBase
    # intent: Optional[IntentBase] = None
    data_templates: Optional[List[DataTemplateBase]] = None


class AgentBuilder(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    business_usecase: str
    tools: List[Tool]
    previous_config: Optional[Dict[str, Any]] = None
    user_instructions: Optional[str] = None

    @field_validator("name")
    def validate_name(cls, v):
        # Check if contains only letters, numbers, underscores, hyphens, and periods
        if v and not all(c.isalnum() or c in ("_", "-", ".", " ") for c in v):
            raise ValueError(
                "Name can only contain letters, numbers, underscores, hyphens, and periods"
            )
        return v


class AgentBuilderDetail(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: str
    style: Literal[
        "formal", "informal", "friendly", "empathetic", "creative", "analytical"
    ]
    goal: str
    instructions: str
    rules: List[str]
    success_criteria: str
    tools: Optional[List[Tool]] = None
    plan: Optional[List[Plan]] = None
    response_schema: Optional[List[Dict[str, Any]]] = None

    @field_validator("name")
    def validate_name(cls, v):
        # Check if contains only letters, numbers, underscores, hyphens, and periods
        if v and not all(c.isalnum() or c in ("_", "-", ".", " ") for c in v):
            raise ValueError(
                "Name can only contain letters, numbers, underscores, hyphens, and periods"
            )
        return v


class AgentArchive(BaseModel):
    agent_ids: List[UUID]
