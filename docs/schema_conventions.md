# Schema Naming Conventions

This reference document provides a detailed explanation of schema naming conventions and their structure. It serves as a guideline for maintaining consistency and clarity while designing new schemas in the codebase.

## Basic Schemas
Basic Schemas can be defined as a BaseModel serving as reusable building blocks for data validation and parsing. These schemas can either be standalone or integrated into other schemas to  to enhance modularity and control. By creating individual components, you can enhance flexibility, maintainability, and code reusability.

    class RolePermission(BaseModel):
        module: str
        feature: str
        enabled: bool

## Base Schemas
Base schemas define common fields and validation rules that can be reused or extended across multiple schemas. These schemas serve as foundational data structures, ensuring consistency, and they make the data structure easier to validate and manipulate.

    class UserRoleBase(BaseModel):
        name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
        role_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4)]  # type: ignore
        description: Optional[str] = None
        default_role: Optional[bool] = False
        role_permissions: Optional[List[RolePermission]] = None

## Default Schemas
Default schemas define the data structure for creating and updating default entities with predefined values or configurations. These schemas extend base schemas and ensure consistency when initializing entities with standard settings during platform setup.

    class DefaultUserRole(UserRoleBase):
        role_permissions: Optional[List[str]]

## Create Schemas
Create schemas define the structure of data required when creating a new entity. These schemas typically include fields from the base schema, sometimes with additional modifications to tailor the creation process.

    class UserRoleCreate(UserRoleBase):
        pass

## Update Schemas
Update schemas define the data structure required to update an existing entity. They usually include the same fields as the base schema but may allow for partial updates or adjustments to specific fields.

    class UserRoleUpdate(UserRoleBase):
        pass

## Detail Schemas
Detail schemas represent the full set of data for an entity, including additional metadata and related attributes. These schemas are used for retrieving complete entity details.

    class UserRoleDetail(UserRoleBase):
        id: UUID
        role_access: Optional[List[str]] = None
        created_at: Optional[datetime] = None
        updated_at: Optional[datetime] = None

        model_config = ConfigDict(from_attributes=True, protected_namespaces=())

## Response Schemas
Response schemas define the structure of responses, often including lists of entities and metadata like total counts. They are particularly useful for paginated or filtered data, ensuring consistent and clear representation of results when returning data.

    class UserRoleResponse(BaseModel):
        user_roles: List[UserRoleDetail]
        total: int

        @classmethod
        def from_user_roles(cls, user_roles: List[UserRoleDetail], total: int):
            # Filter out user roles with name "ROOT"
            filtered_user_roles = [ur for ur in user_roles if ur.name != "ROOT"]
            total_count = total - sum(1 for ur in user_roles if ur.name == "ROOT")
            return cls(user_roles=filtered_user_roles, total=total_count)