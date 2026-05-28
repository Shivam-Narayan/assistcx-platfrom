# Default libraries
from typing import List, Optional
from typing_extensions import Annotated

# Installed libraries
from pydantic import BaseModel, StringConstraints


class UserProfileEdit(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    user_id: Optional[str] = None


class UserPasswordUpdate(BaseModel):
    current_password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)] = None  # type: ignore
    new_password: Annotated[str, StringConstraints(strip_whitespace=True, min_length=6)] = None  # type: ignore


class Office365UserProfileDetail(BaseModel):
    id: str
    display_name: Optional[str] = None
    given_name: Optional[str] = None
    surname: Optional[str] = None
    user_principal_name: Optional[str] = None
    job_title: Optional[str] = None
    mail: Optional[str] = None
    mobile_phone: Optional[str] = None
    business_phones: Optional[List[str]] = []
    office_location: Optional[str] = None
    preferred_language: Optional[str] = None
    company_name: Optional[str] = None
    department: Optional[str] = None
    usage_location: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
