# # Default libraries
# from datetime import datetime
# from typing import Optional, List
# from typing_extensions import Annotated
# from uuid import UUID

# # Installed libraries
# from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator


# class IntentBase(BaseModel):
#     name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
#     intent_class: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
#     description: Optional[str] = None

#     model_config = ConfigDict(from_attributes=True, protected_namespaces=())

#     @field_validator("name", "intent_class")
#     def validate_name(cls, v):
#         # Check if contains only letters, numbers, underscores, hyphens, and periods
#         if v and not all(c.isalnum() or c in ("_", "-", ".", " ") for c in v):
#             raise ValueError(
#                 "Name can only contain letters, numbers, underscores, hyphens, and periods"
#             )
#         return v


# class IntentCreate(IntentBase):
#     pass


# class IntentUpdate(IntentBase):
#     name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore
#     intent_class: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]] = None  # type: ignore

#     @field_validator("intent_class", mode="before")
#     def force_intent_class_none(cls, v):
#         # Always set intent_class to None to avoid updating it
#         return None


# class IntentDetail(IntentBase):
#     id: UUID
#     created_at: Optional[datetime] = None
#     updated_at: Optional[datetime] = None


# class IntentResponse(BaseModel):
#     intents: List[IntentDetail]
#     total: int
