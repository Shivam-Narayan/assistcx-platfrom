# Role-Based Access Control (RBAC)

## Overview

The RBAC system uses **module-level access control** with a hierarchy of permission levels. Each user role defines a set of modules with an access level for each. The middleware resolves permissions in-memory using prefix matching against the request path — no database query is needed for route authorization.

### Key Concepts

- **Module**: A logical grouping of related API routes (e.g., `agents`, `task_inbox`, `knowledge`)
- **Access Level**: `none` < `view` < `edit` < `full` — higher levels include all lower levels
- **HTTP Method Convention**: The required access level is derived from the HTTP method automatically

## Access Level Hierarchy

| Level  | Value | HTTP Methods     | Description                        |
| :----- | :---: | :--------------- | :--------------------------------- |
| `none` |   0   | —                | No access to the module            |
| `view` |   1   | GET              | Read-only access                   |
| `edit` |   2   | POST, PUT, PATCH | Can create and modify resources    |
| `full` |   3   | DELETE           | Complete access including deletion |

Each level includes all lower levels. A user with `edit` can also perform `view` operations.

## Route Categories

All API routes fall into one of these categories, checked in order by the middleware:

| Category             |  Auth Required   | Who Can Access           | Example Routes                                  |
| :------------------- | :--------------: | :----------------------- | :---------------------------------------------- |
| **Open Routes**      |        No        | Anyone                   | `/health`, `/login`, `/docs`, `/token`          |
| **Root Only Routes** |    Yes (ROOT)    | ROOT user only           | `/setup-platform`, `/create-system-permissions` |
| **Auth Only Routes** |  Yes (any JWT)   | Any authenticated user   | `/profile`, `/tags`, `/tool-bindings`           |
| **Module Routes**    | Yes + permission | Users with module access | `/agents`, `/emails`, `/collections`            |
| **Unknown Routes**   |        —         | Denied                   | Any route not matching above                    |

## Middleware Flow

```
Request
  |
  ├─ OPTIONS? ──────────────────────── Allow (CORS preflight)
  |
  ├─ Open route? ───────────────────── Allow (no auth needed)
  |
  ├─ /task-api? ────────────────────── Validate API key
  |
  ├─ No Bearer token? ─────────────── 401 Unauthorized
  |
  ├─ Decode + verify JWT
  |
  ├─ ROOT user? ────────────────────── Allow (bypass all checks)
  |
  ├─ Root-only route? ──────────────── 403 Forbidden
  |
  ├─ Auth-only route? ──────────────── Allow
  |
  ├─ Module route check:
  |   ├─ Find matching modules (prefix match)
  |   ├─ Determine required level from HTTP method
  |   ├─ Check user has required level on ANY matching module (OR logic)
  |   ├─ Pass? ─────────────────────── Check data filters, then Allow
  |   └─ Fail? ─────────────────────── 401 Access denied
  |
  └─ No match? ─────────────────────── 401 Denied (secure by default)
```

## Module Definitions

Each module in `PLATFORM_MODULES` defines:

| Field           | Type | Description                                         |
| :-------------- | :--- | :-------------------------------------------------- |
| `name`          | str  | Display name for the UI                             |
| `description`   | str  | Description shown in role management                |
| `routes`        | list | API route prefixes this module controls             |
| `web_routes`    | list | Frontend pages visible when module is accessible    |
| `access_levels` | list | Levels available for this module (excluding `none`) |
| `data_filters`  | list | Fields available for data-level filtering           |

### Modules

| Module Key         | Name             | Access Levels    | Web Route                 | Data Filters                        |
| :----------------- | :--------------- | :--------------- | :------------------------ | :---------------------------------- |
| `agents`           | Agents           | view, edit       | /agents                   | name                                |
| `agent_tools`      | Agent Tools      | view, edit, full | /tools                    | —                                   |
| `api_keys`         | API Keys         | full             | /settings/api-keys        | —                                   |
| `assistant`        | Assistant        | view             | —                         | —                                   |
| `class_groups`     | Class Groups     | view, edit, full | /settings/class-group     | —                                   |
| `knowledge`        | Knowledge        | view, edit, full | /knowledge                | name                                |
| `connections`      | Connections      | view, edit, full | /connections              | name, provider_key, auth_schema_key |
| `dashboards`       | Dashboards       | view             | /                         | —                                   |
| `data_templates`   | Data Templates   | view, edit, full | /settings/data-template   | —                                   |
| `integrations`     | Integrations     | view, edit, full | /integrations             | —                                   |
| `intents`          | Intents          | view, edit, full | /settings/intent-class    | —                                   |
| `task_issues`      | Task Issues      | view, edit, full | /issues                   | —                                   |
| `mailbox_pollings` | Mailbox Pollings | view, edit, full | /settings/mailbox-polling | —                                   |
| `organizations`    | Organization     | view, edit       | /settings/account         | —                                   |
| `task_inbox`       | Task Inbox       | view, edit, full | /inbox                    | mailbox_email                       |
| `user_management`  | User Management  | view, edit, full | /settings/manage-user     | —                                   |

### Cross-Module Route Sharing

Some routes appear in multiple modules to support cross-module reads. For example, `/collections` is listed under both `agents` and `knowledge`. The middleware uses **OR logic**: if a user has the required access level on **any** matching module, access is granted.

This means an `agents:edit` user can `GET /collections` (because `/collections` is in the agents route list) even if they have `knowledge:none`.

### Wildcard Route Patterns

Routes with `{}` match any path segment at that position. For example, `/integrations/{}/credentials` matches `/integrations/abc-123/credentials`.

## Default Roles

### Account Admin

Highest level of access for organization management. Full control over all modules.

| Module           | Level |
| :--------------- | :---: |
| Agents           | edit  |
| Agent Tools      | full  |
| API Keys         | full  |
| Assistant        | view  |
| Class Groups     | full  |
| Knowledge        | full  |
| Connections      | full  |
| Dashboards       | view  |
| Data Templates   | full  |
| Integrations     | full  |
| Intents          | full  |
| Task Issues      | full  |
| Mailbox Pollings | full  |
| Organizations    | edit  |
| Task Inbox       | full  |
| User Management  | full  |

### System Admin

High-level permissions. Can manage most components but with reduced write access compared to Account Admin.

| Module           | Level |
| :--------------- | :---: |
| Agents           | view  |
| Agent Tools      | view  |
| API Keys         | full  |
| Assistant        | view  |
| Class Groups     | view  |
| Knowledge        | view  |
| Connections      | view  |
| Dashboards       | view  |
| Data Templates   | view  |
| Integrations     | edit  |
| Intents          | view  |
| Task Issues      | edit  |
| Mailbox Pollings | edit  |
| Organizations    | edit  |
| Task Inbox       | edit  |
| User Management  | edit  |

### Group Admin

Focused on group-level operations. Can manage tasks and view core modules.

| Module        | Level |
| :------------ | :---: |
| Agents        | view  |
| Agent Tools   | view  |
| Assistant     | view  |
| Dashboards    | view  |
| Organizations | view  |
| Task Inbox    | edit  |
| Task Issues   | view  |

### Group Staff

Operational access for task management.

| Module        | Level |
| :------------ | :---: |
| Assistant     | view  |
| Dashboards    | view  |
| Organizations | view  |
| Task Inbox    | edit  |
| Task Issues   | view  |

### Standard User

Most restricted role. Read-only access to operational modules.

| Module        | Level |
| :------------ | :---: |
| Assistant     | view  |
| Dashboards    | view  |
| Organizations | view  |
| Task Inbox    | view  |
| Task Issues   | view  |

## Data-Level Filtering

Beyond module access, the system supports **data-level filtering** to restrict which records a user can see within a module. This is configured per user/group via `data_access` on the user access record.

### Modules with Data Filters

| Module         | Filter Fields                          | Example Use Case                              |
| :------------- | :------------------------------------- | :-------------------------------------------- |
| `agents`       | `name`                                 | User can only see agents named "Sales Bot"    |
| `knowledge`    | `name`                                 | User can only see collection "FAQ Docs"       |
| `connections`  | `name`, `provider_key`, `auth_schema_key` | User can only see Slack connections        |
| `task_inbox`   | `mailbox_email`                        | User can only see tasks from support@acme.com |

### How Data Access is Stored

Data access is stored on the **user access record** (`data_access` JSON field), keyed by module:

```json
{
  "task_inbox": {
    "mailbox_email": ["support@acme.com", "sales@acme.com"]
  },
  "agents": {
    "name": true
  }
}
```

Filter values can be:

| Value Type | Meaning                                      | Example                                |
| :--------- | :------------------------------------------- | :------------------------------------- |
| `list`     | User can only access these specific values   | `["support@acme.com", "sales@acme.com"]` |
| `true`     | Unrestricted access (no filter applied)      | User sees all agents                   |
| `false`    | No access (empty filter — blocks all records) | User sees nothing in this module       |

### User + Group Permission Merging

Users can belong to multiple **user groups**, each with their own `data_access`. The middleware merges all sources (user-level + all group-level) using these rules:

1. **List + List** → union of both lists (e.g., `["a@x.com"]` + `["b@x.com"]` → `["a@x.com", "b@x.com"]`)
2. **List + `true`** → `true` (unrestricted wins)
3. **`true` + anything** → `true` (unrestricted always wins)
4. **`false` + List** → the list (list overrides no-access)
5. **`false` + `false`** → `false` (no access)

Group permissions are fetched in a **single batch query** (not N+1) using the user's `user_group_ids`.

### Incoming Filter Intersection

When a request includes `?filters={"mailbox_email": ["support@acme.com"]}` as a query parameter, the middleware intersects the incoming filters with the user's allowed data permissions:

- If the intersection is non-empty → use the intersection as the effective filter
- If the intersection is empty → **deny access** (401) because the user is requesting data they don't have permission to see
- If no data permissions are configured → pass through incoming filters unchanged

### Request State

After resolution, the final filters are stored in `request.state.filters` as a dictionary. Route handlers use this to scope their database queries:

```python
# In a route handler
filters = request.state.filters  # {"mailbox_email": ["support@acme.com"]} or None
```

A `None` value means no data-level filtering applies (either the module has no data filters or the user has unrestricted access).

## Web App Integration

### Frontend Page Visibility

The `/permissions` endpoint returns all module definitions with their `web_routes`. The frontend uses this to show/hide navigation items based on the user's role.

When a user logs in, `web_routes` are resolved from their role permissions — only modules where the user has level > `none` contribute their web routes. For example, a user with `agents: edit` and `dashboards: view` would get `["/agents", "/"]` as their visible web routes.

The backend utility `get_web_routes(role_permissions)` in `rbac_utils.py` performs this resolution:

```python
# Input: role_permissions from JWT
{"modules": {"agents": {"level": "edit"}, "dashboards": {"level": "view"}}}

# Output: list of web routes
["/agents", "/"]
```

The frontend stores these routes and uses them to conditionally render navigation sidebar items, tab bars, and redirect logic.

### Role Management UI

The role creation/editing page fetches module definitions from `GET /permissions` and presents each module as a row with a dropdown for the access level.

**`GET /permissions` response structure:**

```json
{
  "modules": [
    {
      "key": "agents",
      "name": "Agents",
      "description": "AI agents configuration and management",
      "access_levels": ["view", "edit"],
      "web_routes": ["/agents"],
      "data_filters": ["name"]
    },
    {
      "key": "task_inbox",
      "name": "Task Inbox",
      "description": "Email tasks, attachments, and agent outputs",
      "access_levels": ["view", "edit", "full"],
      "web_routes": ["/inbox"],
      "data_filters": ["mailbox_email"]
    }
  ],
  "total": 16
}
```

The dropdown options for each module are:

- `none` (always available — the frontend prepends this as the default option)
- Plus the module's `access_levels` list (e.g., `view`, `edit`, `full`)

Modules with different `access_levels` present different dropdown options. For example, `api_keys` only offers `none` and `full`, while `task_inbox` offers `none`, `view`, `edit`, and `full`.

When the `field_restrictions` query parameter is set to `true`, the response also includes available values for data filters (fetched from the database). This is used by the user access management UI to let admins assign specific data filter values to users.

### JWT Token

Role permissions are embedded in the JWT token during login/token refresh:

```json
{
  "sub": "user-uuid",
  "org_id": "org-uuid",
  "user_role": "Account Admin",
  "permissions": {
    "modules": {
      "agents": { "level": "edit" },
      "task_inbox": { "level": "full" },
      "dashboards": { "level": "view" }
    }
  },
  "exp": 1234567890
}
```

Key details:

- Only modules with level > `none` are included in the token — omitted modules are implicitly `none`
- The middleware reads `permissions` directly from the decoded JWT — **no database query** is needed for route authorization
- The `user_role` field contains the role name (used to identify ROOT users for bypass logic)
- Token refresh preserves the same permission structure from the user's assigned role

## Configuration

All RBAC configuration lives in a single file: `backend/configs/user_roles.py`

| Constant               | Purpose                                              |
| :--------------------- | :--------------------------------------------------- |
| `ACCESS_HIERARCHY`     | Level name to numeric value mapping                  |
| `HTTP_METHOD_TO_LEVEL` | HTTP method to required access level                 |
| `OPEN_ROUTES`          | Public routes (no auth)                              |
| `ROOT_ONLY_ROUTES`     | System bootstrapping routes (ROOT user only)         |
| `AUTH_ONLY_ROUTES`     | Routes requiring JWT but no module permission        |
| `PLATFORM_MODULES`     | Module definitions with routes, levels, and metadata |
| `DEFAULT_ROLES`        | Pre-configured roles seeded during platform setup    |

## Key Backend Files

| File                                  | Responsibility                                   |
| :------------------------------------ | :----------------------------------------------- |
| `configs/user_roles.py`               | Single source of truth for all RBAC config       |
| `utils/rbac_utils.py`                       | Route resolution and access checking (in-memory) |
| `utils/middleware.py`                 | Middleware that enforces auth and permissions    |
| `utils/permissions.py`                | Role compress/decompress, data-level access      |
| `routes/user_role_routes.py`          | CRUD for roles, serves module definitions        |
| `repository/permission_repository.py` | Permission DB operations, data filter values     |
