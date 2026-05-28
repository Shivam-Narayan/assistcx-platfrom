# Default libraries
from datetime import datetime
from typing import Optional, Dict, Any, Union, Literal
from uuid import UUID
from typing_extensions import Annotated

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, Field, field_validator

# Custom libraries
from schemas.agent_schema import AgentDetail
from schemas.data_template_schema import DataTemplateDetail
from schemas.class_group_schema import ClassGroupDetail


# Discriminated union configs for each entity type
class AgentConfig(BaseModel):
    entity_type: Literal["agent"] = "agent"
    config_data: AgentDetail

    model_config = ConfigDict(from_attributes=True)

class ClassGroupConfig(BaseModel):
    entity_type: Literal["class_group"] = "class_group"
    config_data: ClassGroupDetail

    model_config = ConfigDict(from_attributes=True)



class DataTemplateConfig(BaseModel):
    entity_type: Literal["data_template"] = "data_template"
    config_data: DataTemplateDetail

    model_config = ConfigDict(from_attributes=True)


class GenericConfig(BaseModel):
    entity_type: str
    config_data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


# Union type for all config types
ConfigUnion = Annotated[
    Union[AgentConfig, ClassGroupConfig, DataTemplateConfig, GenericConfig],
    Field(discriminator="entity_type")
]


class VersionHistoryBase(BaseModel):
    entity_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]
    entity_id: UUID
    user_id: UUID
    config_data: Optional[Union[AgentDetail, DataTemplateDetail, Dict[str, Any]]] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    @field_validator("config_data", mode="before")
    @classmethod
    def parse_config_data(cls, v, info):
        """Parse config_data through appropriate schema based on entity_type"""
        if v is None or not isinstance(v, dict):
            return v

        # Get entity_type from validation context
        entity_type = info.data.get("entity_type")

        if entity_type == "agent":
            # Parse through AgentBase to maintain field order
            from schemas.agent_schema import AgentBase
            return AgentBase.model_validate(v).model_dump()
        elif entity_type == "class_group":
            # Parse through ClassGroupBase to maintain field order
            from schemas.class_group_schema import ClassGroupBase
            return ClassGroupBase.model_validate(v).model_dump()
        elif entity_type == "data_template":
            # Parse through DataTemplateBase to maintain field order
            from schemas.data_template_schema import DataTemplateBase
            return DataTemplateBase.model_validate(v).model_dump()

        # Return as-is for unknown entity types
        return v


class VersionHistoryDetail(VersionHistoryBase):
    id: UUID
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    version_number: Optional[int] = None
    created_at: Optional[datetime] = None
