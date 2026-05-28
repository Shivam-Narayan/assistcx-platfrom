# Default libraries
from typing import Any, Dict, List, Optional

# Installed libraries
from pydantic import BaseModel, Field


class DataSchemaBuilderInput(BaseModel):
    """Input for generating the data schema of a data template."""

    name: str = Field(description="Name of the data template", min_length=4)
    description: str = Field(
        description="Description of the data template"
    )
    previous_schema: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Previous data schema to reference or improve upon",
    )
    user_instructions: Optional[str] = Field(
        default="",
        description="Additional instructions or constraints from the user",
    )


class DataSchemaField(BaseModel):
    """A single field in the generated data schema."""

    name: str = Field(description="Unique snake_case identifier for the field")
    data_type: Optional[str] = Field(
        default="string",
        description="Data type: string, integer, decimal, list, object, or list[object]",
    )
    description: str = Field(
        description="Detailed, actionable description guiding AI extraction"
    )
    keywords: Optional[List[str]] = Field(
        default=[],
        description="Alternate labels, synonyms, or abbreviations for the field",
    )
    field_schema: Optional[List[Dict[str, str]]] = Field(
        default=[],
        description="Sub-field definitions for object and list[object] type fields. Each entry must include name, data_type, and description",
    )


class GeneratedDataSchema(BaseModel):
    """Generated data schema for a data template, produced by the LLM."""

    data_schema: List[DataSchemaField] = Field(
        description="List of schema fields generated for the data template"
    )
