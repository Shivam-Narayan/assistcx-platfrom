# Default libraries
from typing import List, Literal
from typing_extensions import Annotated

# Installed libraries
from pydantic import BaseModel, StringConstraints, field_validator


class SmartField(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
    description: str
    keywords: List[str] = []
    data_type: Literal["text", "number", "boolean", "date", "list"] = "text"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate that name is lowercase and contains no spaces"""
        if " " in v:
            raise ValueError("Name cannot contain spaces")
        if v != v.lower():
            raise ValueError("Name must be lowercase")
        return v
