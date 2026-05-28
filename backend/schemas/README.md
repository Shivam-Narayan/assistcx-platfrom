# Schema Guidelines

Pydantic schemas for API request/response validation.

## File Naming

```
{entity}_schema.py  # e.g., user_schema.py, tag_schema.py
```

## Class Hierarchy

| Class | Purpose |
|-------|---------|
| `{Entity}Base` | Common fields shared across operations |
| `{Entity}Create` | Request body for POST (inherits Base) |
| `{Entity}Update` | Request body for PUT/PATCH (fields optional) |
| `{Entity}Detail` | Response with `id` + timestamps |
| `{Entity}Response` | Paginated list response |

## Import Structure

```python
# Default libraries
from datetime import datetime
from typing import Optional, List, Dict, Any
from typing_extensions import Annotated
from uuid import UUID

# Installed libraries
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
```

## Example: `product_schema.py`

```python
from datetime import datetime
from typing import Optional, List
from typing_extensions import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints


class ProductBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2)]  # type: ignore
    description: Optional[str] = None
    price: float
    is_active: Optional[bool] = True

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    name: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=2)]] = None  # type: ignore
    price: Optional[float] = None  # type: ignore


class ProductDetail(ProductBase):
    id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProductResponse(BaseModel):
    products: List[ProductDetail]
    total: int
```

## Key Conventions

1. **ConfigDict** - Add `model_config = ConfigDict(from_attributes=True, protected_namespaces=())` for ORM compatibility

2. **String validation** - Use `Annotated[str, StringConstraints(...)]` with `# type: ignore`

3. **Update schema** - Override required fields as `Optional` with `= None`

4. **Detail schema** - Always include `id: UUID` and optional timestamps

5. **Response schema** - Plural field name (`products`) + `total: int`

## Optional: Field Validators

```python
from pydantic import field_validator

class UserBase(BaseModel):
    email: str

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        return v.strip().lower() if v else v
```

## Optional: Nested Schemas

```python
class AddressInfo(BaseModel):
    street: str
    city: str

class CompanyBase(BaseModel):
    name: str
    address: Optional[AddressInfo] = None
```
