# AssistCX Enterprise Integrations: Connections & Sources (Developer Feature Doc)

This document defines the **integration design pattern** for AssistCX to connect to external business systems (Outlook/Microsoft 365, Gmail/Google Workspace, Google Drive, SharePoint/OneDrive, AWS S3, Salesforce, ServiceNow, etc.) in **customer-hosted deployments** (behind firewall / private IP). It is a **developer reference** for implementing the integration framework end-to-end, including **config registries**, **data model**, and **UX flows**.

---

## 1. Goals

### Primary goals

- Provide a **unified, consistent** experience to connect external systems.
- Support **multiple authentication modes** per provider (delegated OAuth, app-only OAuth, service account, API keys, IAM roles, JWT bearer, etc.).
- Treat “what we ingest/watch” as a first-class object with lifecycle controls (enable/disable, health, logs).
- Enable **config-driven extensibility**: new providers can be added primarily via config + adapter code.
- Work well for enterprise deployments with **restricted outbound networking**, proxies, and security controls.

### Non-goals

- This document does not define agent execution logic.
- This document does not mandate polling vs webhook. The abstractions support both.

---

## 2. Key Concepts and Terminology

### Provider (Integration)

A **Provider** is the external system: Outlook, Gmail, Google Drive, SharePoint, S3, Salesforce, ServiceNow.

### Connection

A **Connection** is an **authentication boundary**:

- Stores credentials/tokens/secrets (directly or via a secure secrets reference)
- Represents a security context (“who/what is authenticated?”)
- Has lifecycle status: `connected`, `needs_reauth`, `disabled`, `error`

Examples:

- Microsoft Graph app-only credentials (client credentials)
- Google OAuth tokens for a user
- AWS IAM Role / Access Keys
- Salesforce OAuth / JWT bearer

### Trigger (Template)

A **Trigger** is a **template configuration** that describes:

- the **trigger label** the user selects (e.g., "New Email", "New File", "Record Updated")
- the **input schema** required to create a Source (resource fields, filters, schedule, processing options)
- the **delivery mode** (`poll`, `webhook`, or `both`) indicating how events are received
- the **runtime strategy** (cursor/dedupe hints) used by the adapter

In config, Triggers are identified by keys such as:

- `outlook.new_email`
- `aws_s3.new_object`
- `salesforce.new_or_changed_record`

### Source (Instance) — `task_source` table

A **Source** (stored as `TaskSource`) is the saved, named **instance** of a Trigger, bound to a Connection and an Agent. It is the atomic, end-to-end "connected watch point":

- Has a **name** and optional description (e.g., "Support Inbox — New Email")
- References a **Trigger** (template)
- References a **Connection** (auth boundary)
- Linked to an **Agent** that receives the resulting events
- Contains **resource config**, **filters**, **schedule config**, and **processing options**
- Maintains its own **cursor** for polling state
- Can be started/stopped, tested, and monitored

A Source is what users mean when they say: "Connect this mailbox folder / drive folder / bucket prefix / query."

### Tool (Template)

A **Tool** is a **template configuration** that describes an action an agent can perform in an external system:

- the **tool label** the user sees (e.g., "Send Email", "Upload File", "Create Record")
- the **handler reference** for execution dispatch (the actual function the agent calls)
- the **input schema** (JSON Schema, view-only) — documents what the handler accepts
- the **output schema** (JSON Schema, view-only) — documents what the handler returns

The input signature comes directly from the handler function; the schemas are documentation for the UI catalog and agent context, not form drivers.

In config, Tools are identified by keys such as:

- `outlook.send_email`
- `aws_s3.upload_object`
- `salesforce.create_record`

> **Key difference from Triggers:** Tools are invoked **on-demand** by the agent during task execution. They have no schedule, filter, cursor, dedupe, or config schema. Trigger is to TaskSource as Tool is to AgentTool.

### AgentTool (Instance) — `agent_tool` table

An **AgentTool** is the saved **binding** of a Tool to an Agent, via a Connection. It is the equivalent of TaskSource for the actions side:

- References a **Tool** (template)
- References a **Connection** (auth boundary)
- Linked to an **Agent** that can invoke it
- Can be enabled/disabled per agent

AgentTool is a pure binding — no config, no schedule, no cursor. The agent provides all input parameters at invocation time via the handler function.

An AgentTool is what users mean when they say: "Let this agent send emails via Outlook" or "Let this agent upload files to S3."

### Delegated OAuth nuance (Seamless UX)

Delegated OAuth requires:

- **App Setup** (Azure/Google app credentials)
- **User authorization** (tokens)

To keep UX seamless, AssistCX **hides App Setup as an internal/shared config** and shows a delegated connection as a **connected account**.

- UI shows: “Outlook (Delegated) — [vikas@company.com](mailto:vikas@company.com)”
- Internally: shared App Setup (tenant/client/secret/redirect) may be reused across multiple connected accounts

This avoids a separate “Add Account” action.

---

## 3. Standard Mental Model

```
Inbound:  Provider → Connection → TaskSource (Trigger + Config) → events → agent tasks
Outbound: Provider → Connection → AgentTool (Tool + Config) → agent invokes tool during task execution
```

- **Connection** is the shared authentication boundary for both directions.
- **TaskSources** produce events that create tasks for agents (inbound).
- **AgentTools** provide capabilities the agent uses during task execution (outbound).

### 3.1 Overall Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                          INTEGRATION MODULE ARCHITECTURE                              │
└──────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────────┐
│ 1. CONFIG REGISTRIES (Config-Driven, Seeded on Startup)                               │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  Integration Registry          Auth Schema Registry         Trigger Registry          │
│  ┌───────────────────┐         ┌───────────────────┐       ┌───────────────────┐     │
│  │ outlook            │         │ msft.oauth2.       │       │ outlook.new_email │     │
│  │  ├─ delegated      │         │   delegated        │       │  ├─ delivery_mode │     │
│  │  │  auth_schema ────┼────────►│  ├─ fields[]      │       │  ├─ resource_     │     │
│  │  │  triggers ───────┼────┐   │  ├─ oauth config   │       │  │   schema       │     │
│  │  │  tools ──────────┼──┐ │   │  └─ scopes[]       │       │  ├─ filter_schema │     │
│  │  └─ app_only       │  │ │   │ msft.oauth2.       │       │  ├─ schedule_     │     │
│  │ aws_s3             │  │ │   │   app_only         │       │  │   schema       │     │
│  │  └─ iam_role       │  │ │   │ aws.iam            │       │  ├─ processing_   │     │
│  │ salesforce         │  │ │   │ sf.jwt_bearer      │       │  │   schema       │     │
│  │  └─ jwt_bearer     │  │ │   └───────────────────┘       │  └─ runtime       │     │
│  └───────────────────┘  │ │                                │    (cursor/dedupe) │     │
│                          │ └───────────────────────────────►│                    │     │
│                          │                                  │ aws_s3.new_object │     │
│                          │    Tool Registry                 │ sf.new_or_changed │     │
│                          │   ┌───────────────────┐         └───────────────────┘     │
│                          │   │ outlook.send_email │                                   │
│                          │   │  ├─ input_schema  │                                   │
│                          └──►│  ├─ config_schema │                                   │
│                              │  ├─ output_schema │                                   │
│                              │  └─ handler       │                                   │
│                              │ aws_s3.upload_obj  │                                   │
│                              │ sf.create_record   │                                   │
│                              └───────────────────┘                                   │
│                                                                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼ Seed / Validate
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ 2. DATA LAYER (Runtime State)                                                         │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  ┌─────────────────────┐         ┌──────────────────────────────────┐                │
│  │ Connection           │         │ TaskSource                       │                │
│  │ (Auth Boundary)      │         │ (Watch Point — Inbound)          │                │
│  ├─────────────────────┤         ├──────────────────────────────────┤                │
│  │ provider_key         │◄────────│ connection_id                    │                │
│  │ connection_mode      │         │ agent_id ──────────────────────────► Agent        │
│  │ status               │         │ trigger_key                      │                │
│  │ auth_schema_key      │         │ name                             │                │
│  │ secrets_ref ─────────┼──► 🔐  │ resource_config    (jsonb)       │                │
│  │ metadata      (jsonb)│         │ filter_config      (jsonb)       │                │
│  └──────────┬──────────┘         │ schedule_config    (jsonb)       │                │
│             │                     │ processing_config  (jsonb)       │                │
│             │ cascading           │ cursor             (jsonb)       │                │
│             │ status              │ enabled / status                 │                │
│             │                     └──────────────┬───────────────────┘                │
│             │                                    │                                    │
│             │  Connection.status                 │ produces                           │
│             │  ≠ connected?                      ▼                                    │
│             │  ──► TaskSource.status             ┌──────────────────────────┐         │
│             │      = auth_error                  │ EventInbox               │         │
│             │      (auto-pause)                  ├──────────────────────────┤         │
│             │                                    │ task_source_id           │         │
│             │  Connection restored?              │ external_event_id       │         │
│             └──► TaskSource resumes              │ dedupe_key (unique)     │         │
│                  automatically                   │ payload         (jsonb) │         │
│                                                  │ status                  │         │
│                                                  │ (pending → processed)   │         │
│                                                  └────────────┬─────────────┘         │
│                                                               │                       │
│  ┌──────────────────────────────────┐  Connection also used by AgentTools:            │
│  │ AgentTool                         │                                                │
│  │ (Tool Binding — Outbound)         │                                                │
│  ├──────────────────────────────────┤                                                │
│  │ connection_id ──► Connection      │                                                │
│  │ agent_id ─────── ► Agent          │                                                │
│  │ tool_key                          │                                                │
│  │ enabled                           │                                                │
│  └──────────────────────────────────┘                                                │
│                                                                                       │
└───────────────────────────────────────────────────────────────┼───────────────────────┘
                                                                │
                                                                ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ 3. TRIGGER RUNTIME (Event Ingestion)                                                  │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  ┌──────────────┐     ┌─────────────────────────────────────────────────────────┐    │
│  │ Scheduler     │     │ Poll Cycle (per TaskSource)                             │    │
│  │ (Celery Beat) │────►│                                                         │    │
│  │ every 30-60s  │     │ 1. SELECT TaskSource WHERE enabled=true                 │    │
│  └──────────────┘     │    AND schedule is due AND status ≠ auth_error           │    │
│                        │                                                         │    │
│                        │ 2. Load Connection → decrypt credentials                │    │
│                        │    → get auth headers                                   │    │
│                        │                                                         │    │
│                        │ 3. Execute provider adapter:                            │    │
│                        │    adapter.poll(cursor, resource_config, filters)        │    │
│                        │    → returns {events[], new_cursor, has_more}           │    │
│                        │                                                         │    │
│                        │ 4. For each event:                                      │    │
│                        │    INSERT INTO EventInbox (dedupe via dedupe_key)       │    │
│                        │                                                         │    │
│                        │ 5. UPDATE TaskSource SET cursor = new_cursor,           │    │
│                        │    last_checked_at = NOW(), last_success_at = NOW()     │    │
│                        └─────────────────────────────────────────────────────────┘    │
│                                                                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ 4. EVENT PROCESSING (EventInbox → Agent Task)                                         │
├──────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                       │
│  ┌──────────────┐     ┌─────────────────────────────────────────────────────────┐    │
│  │ Scheduler     │     │ Inbox Processor                                         │    │
│  │ (Celery Beat) │────►│                                                         │    │
│  │ every 10-30s  │     │ 1. SELECT EventInbox WHERE status = 'pending'           │    │
│  └──────────────┘     │    ORDER BY created_at LIMIT batch_size                  │    │
│                        │    FOR UPDATE SKIP LOCKED                                │    │
│                        │                                                         │    │
│                        │ 2. For each event:                                      │    │
│                        │    a. Load TaskSource → Agent                           │    │
│                        │    b. Create Task for the Agent:                        │    │
│                        │       ┌───────────────────────────────────────────┐     │    │
│                        │       │ Task(                                     │     │    │
│                        │       │   agent_id  = task_source.agent_id,       │     │    │
│                        │       │   name      = "Handle {trigger label}",   │     │    │
│                        │       │   payload   = event.payload,              │     │    │
│                        │       │   metadata  = {task_source_id, ...},      │     │    │
│                        │       │   status    = "pending"                   │     │    │
│                        │       │ )                                         │     │    │
│                        │       └───────────────────────────────────────────┘     │    │
│                        │    c. Update EventInbox.status = 'processed'            │    │
│                        └─────────────────────────────────────────────────────────┘    │
│                                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────────────┐ │
│  │ KEY COMPONENTS                                                                   │ │
│  ├───────────────────┬──────────────────────┬───────────────────────────────────────┤ │
│  │ Config Registries  │ Data Layer           │ Runtime                              │ │
│  ├───────────────────┼──────────────────────┼───────────────────────────────────────┤ │
│  │ Integration        │ Connection           │ Scheduler (Celery Beat)              │ │
│  │ Auth Schema        │ TaskSource           │ Provider Adapter (poll/webhook)      │ │
│  │ Trigger            │ EventInbox           │ Inbox Processor (event → task)       │ │
│  │ Tool               │ AgentTool            │ Tool Executor (agent → action)       │ │
│  └───────────────────┴──────────────────────┴───────────────────────────────────────┘ │
│                                                                                       │
│  DATA FLOW (inbound):                                                                 │
│  Config Registries → DB Seed → Connection (auth) → TaskSource (config + cursor)       │
│  → Adapter Poll → EventInbox (dedupe) → Inbox Processor → Agent Task                 │
│                                                                                       │
│  DATA FLOW (outbound):                                                                │
│  Agent Task → AgentTool (tool_key + config) → Connection (auth) → Tool Handler        │
│  → External API call → Structured output → Agent                                      │
│                                                                                       │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. UX Information Architecture

### Provider Integration page (recommended)

For each provider show three tabs:

- **Connections** (auth)
  - Create/manage credentials or connected accounts
  - Re-authenticate
  - Validate connectivity

- **Sources** (watch points — inbound)
  - Create Sources (select Trigger + configure Resource/Filters/Schedule/Processing)
  - Enable/disable Sources
  - Test Source

- **Tools** (actions — outbound)
  - Browse available tools for this provider (read-only catalog)
  - View tool input/config schemas
  - "Add to Agent" action per tool (opens agent picker + connection picker)

### Global operational views (recommended)

- **All Connections**: across providers
- **All Sources**: across providers

### Agent configuration

Agents should have two integration sections:

- **Inputs** — attaches existing Sources or creates a new Source inline
- **Tools** — enables tools the agent can invoke during task execution (+ Add Tool / Remove Tool)

> Guidance: **Sources and AgentTools are first-class objects** with lifecycle controls, but can be created from Agent config for seamless setup.

---

## 5. Provider Mapping Examples

### Outlook

- **Connection (app-only):** "Outlook (App-only) — Acme Tenant" (tenant/client/secret)
- **Connection (delegated):** "Outlook (Delegated) — vikas@company.com" (user tokens, app setup hidden/shared)
- **Trigger:** "New Email" (`outlook.new_email`)
- **Source:** "Support Inbox — New Email" (resource: `support@ / Inbox` + filters + schedule)
- **Tools:** Send Email (`outlook.send_email`), Reply to Email (`outlook.reply_email`), Move Email (`outlook.move_email`)
- **AgentTool:** "Support Triage → Send Email" (connection: Acme Tenant)

### AWS S3

- **Connection:** AWS auth context (role/keys/instance profile)
- **Trigger:** "New Object" (`aws_s3.new_object`)
- **Source:** "Invoices Drop — New Object" (resource: bucket+prefix + filters + schedule)
- **Tools:** Upload Object (`aws_s3.upload_object`), Download Object (`aws_s3.download_object`)
- **AgentTool:** "Doc Processor → Upload Object" (connection: AWS Prod)

### Salesforce

- **Connection:** OAuth/JWT bearer
- **Trigger:** "New or Changed Record" (`salesforce.new_or_changed_record`)
- **Source:** "Opportunities Changed" (resource: object+query + schedule)
- **Tools:** Create Record (`salesforce.create_record`), Query Records (`salesforce.query_records`)
- **AgentTool:** "CRM Agent → Create Record" (connection: SF Prod)

### Gmail

- **Connection:** OAuth user / service account
- **Trigger:** "New Email" (`gmail.new_email`)
- **Source:** "Inbox — New Email" (resource: label/query + schedule)
- **Tools:** Send Email (`gmail.send_email`), Add Label (`gmail.add_label`)
- **AgentTool:** "Responder → Send Email" (connection: user OAuth)

### Google Drive

- **Connection:** OAuth user / service account
- **Trigger:** "New File" (`google_drive.new_file`)
- **Source:** "Shared Drive — New File" (resource: folder + schedule)
- **Tools:** Upload File (`google_drive.upload_file`), Move File (`google_drive.move_file`)

### SharePoint

- **Connection:** delegated / app-only
- **Trigger:** "New File" (`sharepoint.new_file`)
- **Source:** "HR Docs — New File" (resource: site+library+folder + schedule)
- **Tools:** Upload File (`sharepoint.upload_file`), Create Folder (`sharepoint.create_folder`)

---

## 6. UX Flows

### 6.1 Creating Connections (Standalone)

Connections can be created standalone from the Connections tab, or inline during Source creation (see 6.3).

#### App-only / Service Account / API Keys / IAM

1. Integrations → Provider → Connections tab → **+ Add Connection**
2. Select **auth schema** (dropdown filtered by provider's `supported_auth_schemas`)
   - Dropdown items rendered from auth schema `display_name`
   - Pre-select `default_auth_schema` if set on the integration
3. Form renders from auth schema `input_fields[]` (see 6.4 for field rendering rules)
4. User fills form → **Validate** (optional: test connectivity) → **Save**

Result: Connection row appears — e.g., "Outlook (App-only) — Acme Tenant"

#### Delegated OAuth (Seamless)

1. Integrations → Provider → Connections tab → **+ Add Connection**
2. Select delegated auth schema (e.g., "Microsoft Graph (User Delegated)")
3. If App Setup not configured for this tenant, show app credentials step first (admin-only)
4. **Sign in with Microsoft / Google** → OAuth redirect → tokens saved
5. Connection created automatically

Result: "Outlook (Delegated) — vikas@company.com"

Adding another user repeats the flow; app credentials are reused (step 3 skipped).

> No separate "Add Account" action. Each delegated connection is a row in the Connections list.

---

### 6.2 Source Creation — Entry Points

Sources can be created from two places. Both use the **same form** (6.3); the only difference is context:

| Entry point                                              | Context                                                       | After save                               |
| -------------------------------------------------------- | ------------------------------------------------------------- | ---------------------------------------- |
| **Agent → Inputs → + Add Source**                        | `agent_id` pre-filled, user picks Provider/Trigger/Connection | Source auto-attached to this Agent       |
| **Integrations → Provider → Sources tab → + Add Source** | `provider_key` pre-filled, user picks Trigger/Connection      | Prompt: "Attach to an agent?" (optional) |

A third option — **Agent → Inputs → Attach Existing Source** — lets users search/filter existing Sources by provider, trigger, connection, or tags and attach without creating a new one.

---

### 6.3 Source Creation Form — Step-by-Step

The form is a **multi-step wizard** or a **single scrollable form with sections**. Every section is driven by config data from the registries.

#### Step 1: Select Provider

- **Data source**: `ALL_INTEGRATIONS` (filtered to `is_enabled: true`)
- **Render**: Grid or list of provider cards — each card shows `icon`, `name`, `description`, `tags`
- **Skip if**: Provider is already known from context (e.g., opened from Integrations → Outlook → Sources)
- **On select**: Store `provider_key`, move to Step 2

#### Step 2: Select Trigger

- **Data source**: `get_triggers_for_provider(provider_key)` — returns all triggers for the selected provider
- **Render**: List of trigger options — each shows `label`, `description`, `delivery_mode` badge
- **Example** (Outlook): "New Email", "Email Flagged", "New Calendar Event"
- **On select**: Store `trigger_key`, load trigger schema, move to Step 3

#### Step 3: Select Connection

- **Data source**: Existing connections filtered by `provider_key` from DB + "Create new connection" option
- **Render**: Dropdown or radio list — each shows Connection `display_name` and `status` badge
  - Only connections with `status: connected` are selectable
  - Connections with `needs_reauth` or `error` shown greyed out with status label
- **"+ New Connection" option**: Opens inline connection form (auth schema selection + `input_fields` form from 6.1). On save, new connection is auto-selected and flow continues.
- **On select**: Store `connection_id`, move to Step 4

#### Step 4: Configure Source (Schema-Driven Form)

This is the core of the form. The frontend calls `get_trigger_form_schema(trigger_key)` which returns four schema sections. Each section renders as a **collapsible form group**:

**4a. Resource — "What to watch"** (from `resource_schema.fields[]`)

> These are the primary fields that define the watch target. All required fields must be filled.

Example for `outlook.new_email`:

| Field from schema                  | Renders as                                                 |
| ---------------------------------- | ---------------------------------------------------------- |
| `mailbox_address` (text, required) | Text input — "Mailbox Email"                               |
| `folder_path` (text, optional)     | Text input — "Folder" with default "Inbox"                 |
| `folder_id` (text, required)       | Text input — "Folder ID" (or resolved via resource picker) |

**4b. Filters — "Conditions"** (from `filter_schema[]`)

> All optional. Collapsed by default, expandable via "Add Filters" toggle.

Example for `outlook.new_email`:

| Field from schema                       | Renders as                      |
| --------------------------------------- | ------------------------------- |
| `from_domains` (string[], optional)     | Tag input — "From Domains"      |
| `subject_contains` (text, optional)     | Text input — "Subject Contains" |
| `has_attachments` (boolean, optional)   | Toggle — "Has Attachments"      |
| `attachment_types` (string[], optional) | Tag input — "Attachment Types"  |

**4c. Schedule** (from `schedule_schema`)

> Render an interval picker. Use `schedule_schema.default` to pre-fill, enforce `min` and `max` as bounds on the input.

| Schema field    | UI behavior                              |
| --------------- | ---------------------------------------- |
| `default.every` | Pre-filled value in the interval input   |
| `min.every`     | Minimum allowed value (input validation) |
| `max.every`     | Maximum allowed value (input validation) |

**4d. Processing — "Options"** (from `processing_schema[]`)

> Controls how matched events are processed before being written to EventInbox. Collapsed by default, pre-filled with defaults.

Example for `outlook.new_email`:

| Field from schema                              | Renders as                                   |
| ---------------------------------------------- | -------------------------------------------- |
| `include_body` (boolean, default: true)        | Toggle — "Include Body" (pre-checked)        |
| `include_attachments` (boolean, default: true) | Toggle — "Include Attachments" (pre-checked) |
| `max_attachment_mb` (integer, default: 25)     | Number input — "Max Attachment Size (MB)"    |

#### Step 5: Name & Save

- **Source Name**: Auto-suggested from resource + trigger label (e.g., "support@company.com / Inbox — New Email"). User can edit.
- **Description**: Optional text field
- **Tags**: Optional tag input for filtering/grouping
- **Agent**: If entry point was Agent config, pre-filled and read-only. If entry point was Integrations page, show agent picker (optional — can be attached later).
- **Save**: Creates the TaskSource record with all config fields populated

---

### 6.4 Schema-to-Form Field Rendering

Every field in `input_fields` (auth schemas), `resource_schema.fields`, `filter_schema`, and `processing_schema` is rendered using the same rules. The `FieldType` enum maps to a UI component:

| `type` (FieldType) | UI Component                 | Notes                                            |
| ------------------ | ---------------------------- | ------------------------------------------------ |
| `text`             | Single-line text input       | Standard input                                   |
| `password`         | Masked text input            | Shows/hide toggle; `sensitive: true` implied     |
| `url`              | URL input                    | Frontend validates URL format                    |
| `email`            | Email input                  | Frontend validates email format                  |
| `textarea`         | Multi-line text area         | Used for keys, JSON, queries                     |
| `select`           | Dropdown                     | Options from field's `enum[]` array              |
| `boolean`          | Toggle / checkbox            |                                                  |
| `integer`          | Number input (whole numbers) | Step = 1                                         |
| `string[]`         | Tag / chip input             | User types value + Enter to add, click to remove |

Additional field properties that affect rendering:

| Property      | UI behavior                                        |
| ------------- | -------------------------------------------------- |
| `label`       | Form field label text                              |
| `description` | Help text shown below the input                    |
| `placeholder` | Ghost text inside the input                        |
| `required`    | Show asterisk, validate on submit                  |
| `default`     | Pre-fill input with this value                     |
| `sensitive`   | Encrypt on save, mask in UI after save             |
| `enum`        | Populate dropdown options (only for `select` type) |

#### Validation rules

- **Required fields**: Block submit if empty. Show inline error "This field is required."
- **Type-based**: `url` fields validate URL format, `email` fields validate email format, `integer` fields reject non-numeric input
- **Schedule bounds**: Interval value must be ≥ `schedule_schema.min.every` and ≤ `schedule_schema.max.every`
- **Sensitive fields**: Never echo back after save — show "••••••••" with a "Change" button

---

### 6.5 Example Walkthrough: Creating a Source from Agent Config

> Agent "Support Triage" → Inputs tab → **+ Add Source**

**Step 1 — Select Provider**: Grid shows Outlook, Gmail, AWS S3, Salesforce, Google Drive, SharePoint. User picks **Outlook**.

**Step 2 — Select Trigger**: List shows:

- New Email — "Triggers when a new email arrives in the specified mailbox folder."
- Email Flagged — "Triggers when an email is flagged for follow-up."
- New Calendar Event — "Triggers when a new calendar event is created."

User picks **New Email**.

**Step 3 — Select Connection**: Dropdown shows:

- "Outlook (App-only) — Acme Tenant" ✅ connected
- "Outlook (Delegated) — vikas@company.com" ✅ connected
- \+ New Connection

User picks **"Outlook (App-only) — Acme Tenant"**.

**Step 4 — Configure Source**:

Form renders from `outlook.new_email` schema:

```
── Resource ──────────────────────────────────
  Mailbox Email *      [ support@company.com     ]
  Folder               [ Inbox                    ]
  Folder ID *          [ AQMkAD...    ] (or 📂 Browse)

── Filters (optional) ────────────────────────
  From Domains         [ acme.com ] [ vendor.io ] [+]
  Subject Contains     [                          ]
  Has Attachments      [✓]
  Attachment Types     [ pdf ] [+]

── Schedule ──────────────────────────────────
  Poll every           [ 60 ] seconds  (min: 30, max: 3600)

── Processing (optional) ─────────────────────
  Include Body         [✓]
  Include Attachments  [✓]
  Max Attachment MB    [ 25 ]
```

**Step 5 — Name & Save**:

```
  Source Name           [ Support Inbox — New Email ]  (auto-suggested)
  Description           [ Poll support inbox for new emails with PDF attachments ]
  Tags                  [ support ] [ outlook ] [+]
  Agent                 [ Support Triage ]  (pre-filled, read-only)

  [ Cancel ]  [ Save Source ]
```

Result: TaskSource created, attached to "Support Triage" agent, polling starts immediately.

---

### 6.6 Tool Configuration — Entry Points

Tools are enabled on agents, not created standalone. Both entry points use the same form (6.7):

| Entry point                             | Context                                                              | After save                             |
| --------------------------------------- | -------------------------------------------------------------------- | -------------------------------------- |
| **Agent → Tools → + Add Tool**          | `agent_id` pre-filled, user picks Provider/Tool/Connection           | AgentTool created for this Agent       |
| **Integrations → Provider → Tools tab** | Read-only catalog of available tools; "Add to Agent" action per tool | Opens agent picker + connection picker |

To **remove a tool**: Agent → Tools → select tool → **Remove** (deletes the AgentTool binding).

---

### 6.7 Tool Configuration Form — Step-by-Step

Much simpler than Source creation (6.3) — tools have no resource/filter/schedule/processing/config sections. AgentTool is a pure binding: agent + tool + connection.

#### Step 1: Select Provider

- Same pattern as 6.3 Step 1, but filtered to providers with `supports_actions: true`
- **Skip if**: Provider is already known from context

#### Step 2: Select Tool

- **Data source**: `get_tools_for_provider(provider_key)` — returns all tools for the selected provider
- **Render**: List of tool options — each shows `label`, `description`, and a collapsible view of `input_schema` / `output_schema` (read-only, for reference)
- **Example** (Outlook): "Send Email", "Reply to Email", "Forward Email", "Move Email", "Flag Email", "Create Calendar Event"
- **On select**: Store `tool_key`, move to Step 3

#### Step 3: Select Connection

- Same pattern as 6.3 Step 3 — dropdown of existing connections filtered by `provider_key` + "New Connection" inline option

#### Step 4: Save

- Creates the AgentTool record (agent_id + tool_key + connection_id). The agent can now invoke this tool during task execution.

---

### 6.8 Example Walkthrough: Adding a Tool to an Agent

> Agent "Support Triage" → Tools tab → **+ Add Tool**

**Step 1 — Select Provider**: User picks **Outlook**.

**Step 2 — Select Tool**: List shows Send Email, Reply to Email, Forward Email, Move Email, Flag Email, Create Calendar Event. User picks **Send Email**. The tool card shows input/output schemas for reference:

```
  Send Email — "Send an email via Microsoft Graph API."
  Input:  to (string[]), subject (string), body (string), cc, bcc, importance, ...
  Output: message_id (string), internet_message_id (string)
```

**Step 3 — Select Connection**: Dropdown shows:

- "Outlook (App-only) — Acme Tenant" ✅ connected

User picks the connection.

**Step 4 — Save**: AgentTool created. "Support Triage" agent can now send emails via Outlook.

---

## 7. Data Model

For complete database schema documentation including SQLAlchemy 2.0 models, credential encryption, indexes, and relationships, see:

**[integration-database.md](integration-database.md)**

That document covers:

- **Connection Model** — Authenticated credentials with encrypted storage, dual status tracking (user control + system validation), and soft deletes
- **TaskSource Model** — Configured trigger instances with resource/filter/schedule/processing config, runtime cursor, and health monitoring
- **EventInbox Model** — Intermediate event storage with deduplication
- **AgentTool Model** — Tool bindings for agent capabilities
- **Credential Encryption** — Fernet-based symmetric encryption utilities
- **Database Indexes** — Recommended indexes for query performance
- **Relationships Diagram** — Complete entity relationships

**Key Design Principles:**

- **Single source of truth** — Integration metadata lives in Python registries (`ALL_INTEGRATIONS`), validated at runtime via `@validates` decorator
- **No catalog table** — `provider_key` validated against in-memory registry, eliminating duplication and sync issues
- **Denormalized keys** — `provider_key` stored on Connection, TaskSource, and AgentTool for efficient queries
- **Cursor on TaskSource** — 1:1 relationship with runtime state, updated every poll cycle
- **Deduplication in EventInbox** — Unique constraint on `dedupe_key` prevents duplicate event processing

---

## 8. Config-Driven Architecture

We keep separate registries for modularity. All registries use **dict-keyed** structure (key → config) for O(1) lookup at runtime, with provider-level sub-dicts for code organization:

- **Integration registry**: provider metadata (name, logo, description, tags) + supported auth schemas
- **Auth schema registry**: preset (system values) + input fields (user form) + token fields (post-auth storage)
- **Trigger registry**: handler (execution reference) + input schemas (Resource/Filters/Schedule/Processing) + delivery mode + runtime strategy
- **Tool registry**: handler (execution reference) + input schema (JSON Schema, view-only) + output schema (JSON Schema, view-only)

This enables:

- consistent UI rendering (forms built from schema — field labels, types, placeholders, sensitivity flags)
- consistent validation (required fields, min/max constraints)
- config-driven dispatch (handler references resolve to adapter code without switch/if logic)
- faster addition of new providers

---

## 9. Config Schema Reference

All config registry schemas and samples are maintained in a dedicated reference document:

**[integration-schemas.md](integration-schemas.md)**

That document covers:

- **Integration registry** — provider metadata + supported auth schemas (Outlook, Gmail, AWS S3, Salesforce, Google Drive, SharePoint)
- **Auth schema registry** — preset / input_fields / token_fields per auth type (OAuth2 delegated, OAuth2 app, service account, IAM keys/role, JWT bearer)
- **Trigger registry** — handler + input schemas + runtime, organized by provider
- **Tool registry** — handler + input/config/output schemas, organized by provider
- **TaskSource config examples** — runtime instances for all providers
- **AgentTool binding examples** — runtime instances for all providers
- **Registry merge pattern** — Python reference for provider-level sub-dicts merged at startup (ALL_TRIGGERS, ALL_TOOLS)

---

## 10. Summary of Config Patterns

### Registry structure

All registries use **dict-keyed** structure (`key → config`) for O(1) lookup. Provider-specific configs are defined in separate dicts and merged:

```python
# Triggers (inbound)
OUTLOOK_TRIGGERS = { "outlook.new_email": {...}, ... }
AWS_S3_TRIGGERS  = { "aws_s3.new_object": {...}, ... }
ALL_TRIGGERS     = { **OUTLOOK_TRIGGERS, **AWS_S3_TRIGGERS, ... }

# Tools (outbound)
OUTLOOK_TOOLS    = { "outlook.send_email": {...}, ... }
AWS_S3_TOOLS     = { "aws_s3.upload_object": {...}, ... }
ALL_TOOLS        = { **OUTLOOK_TOOLS, **AWS_S3_TOOLS, ... }
```

### Auth schema split

Each auth schema separates:

- **preset** — system-provided values (URLs, scopes, grant types) — never shown to user
- **input_fields** — user fills during connection setup — rendered as a form with labels, types, placeholders, sensitivity flags
- **token_fields** — stored after OAuth exchange or set by the system

### Trigger template structure

Each trigger defines:

- **handler** — `{module, class, method}` for config-driven dispatch
- **input schemas** — resource_schema, filter_schema, schedule_schema (with default/min/max), processing_schema
- **runtime** — cursor strategy and dedupe key
- **delivery_mode** — `poll`, `webhook`, or `both`

### Tool template structure

Each tool defines:

- **handler** — `{module, class, method}` for config-driven dispatch
- **input_schema** — JSON Schema describing what the handler accepts (view-only, for catalog display and agent context)
- **output_schema** — JSON Schema describing what the handler returns (view-only)

---

## 11. Implementation Guidelines

### 11.1 Separation of concerns

- **Connections**: secrets, consent, token refresh, auth errors
- **Triggers (templates)**: UI schema + delivery mode + runtime strategy hints
- **TaskSources (instances)**: resource + filters + schedule + processing; enable/disable; owns its own cursor
- **EventInbox**: deduplicated event storage between ingestion and agent routing
- **Tools (templates)**: handler + input/config/output schemas for actions
- **AgentTools (instances)**: pure binding (agent + tool + connection); enable/disable

### 11.2 Provider adapter responsibilities

Each provider adapter should implement:

- Connection validation
- Resource listing (optional, for picker UI)
- Resource resolution (e.g., folder path → folder id)
- Source execution (polling or webhook event handling)
- Normalized event payload generation
- Tool execution — accept input from agent, call external API, return structured output

### 11.3 Normalized event payload

Ingestion should produce a normalized event structure:

- `provider_key`
- `task_source_id`
- `external_event_id`
- `occurred_at`
- `summary` (optional)
- `actor` (optional)
- `payload` (provider-native JSON)

### 11.4 Multiple rules from the same Source

If multiple agent rules should run from the same watch point:

- Prefer **one Source** (collector) and agent-side rules/conditions.
- Source produces events once; agent bindings evaluate conditions and create tasks.

(Agent-side routing and rule evaluation are documented separately.)

### 11.5 Connection → Source cascading status

When a Connection's status degrades, all Sources referencing that Connection must reflect the change:

| Connection status | Effect on linked Sources                                    |
| ----------------- | ----------------------------------------------------------- |
| `connected`       | Sources run normally; status determined by their own health |
| `needs_reauth`    | Sources auto-pause; Source status set to `auth_error`       |
| `error`           | Sources auto-pause; Source status set to `auth_error`       |
| `disabled`        | Sources auto-pause; Source status set to `auth_error`       |

Rules:

- `auth_error` is a **derived status** distinct from a Source-level `error` (e.g., "folder not found", "bucket access denied"). This tells the user the problem is the Connection, not the Source config.
- When a Connection returns to `connected`, its linked Sources **automatically resume** if they were paused solely due to the Connection status (i.e., `enabled` is still `true`).
- Sources that were manually disabled (`enabled: false`) before the Connection degraded remain disabled after recovery.

### 11.6 Delivery modes (poll vs webhook)

Each Trigger declares a `delivery_mode` indicating how events are received:

| Mode      | Behavior                                                                                                                               |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `poll`    | Adapter polls the external system on the interval defined in `schedule_config`                                                         |
| `webhook` | External system pushes events to a registered webhook endpoint; `schedule_config` is used for an optional health-check / fallback poll |
| `both`    | Adapter supports either mode; Source config or system preference determines which is active                                            |

The `schedule_config` field on Source applies to all modes:

- **Poll mode**: primary polling interval (e.g., every 60s)
- **Webhook mode**: health-check interval to verify webhook registration and catch missed events
- **Both mode**: determined by the active delivery method

This keeps the Source schema stable regardless of delivery mode and avoids retrofitting when webhook-capable providers are added.

### 11.7 Connection → AgentTool cascading status

Unlike Sources (which auto-pause when a Connection degrades), AgentTools **fail at invocation time**:

| Connection status | Effect on linked AgentTools                                          |
| ----------------- | -------------------------------------------------------------------- |
| `connected`       | Tools execute normally                                               |
| `needs_reauth`    | Tool invocation fails with auth error; agent receives error response |
| `error`           | Tool invocation fails with connection error                          |
| `disabled`        | Tool invocation fails; tool shown as unavailable in agent config     |

Rationale: Sources are background processes that must be paused to avoid wasted poll cycles. Tools are invoked on-demand — there is no background process to pause. The agent receives an error at invocation time and can surface it to the user or retry.

---

## 12. Security & Enterprise Constraints

### Secrets

- Never store raw secrets in plaintext.
- Store secrets via encrypted storage (vault/kms/db-encrypted) referenced by `secrets_ref`.

### Least privilege

- Support allowlists where applicable (e.g., mailbox allowlist for app-only Outlook).
- Keep scopes minimal.

### Behind firewall

- Provide diagnostics:
  - outbound connectivity tests to required domains
  - proxy support per deployment

---

## 13. Extensibility Checklist (Adding a New Provider)

1. Add provider entry in Integration registry (set `supports_triggers` / `supports_actions` flags)
2. Add auth schema(s)
3. Add Trigger definitions (trigger registry) — if provider supports inbound events
4. Add Tool definitions (tool registry) — if provider supports outbound actions
5. Implement adapter methods (poll/webhook for triggers, execution for tools)
6. Add UI labels/icons and capabilities

---

## 14. Recommended UI Copy

- Provider page tabs: **Connections**, **Sources**, and **Tools**

- Primary CTAs:
  - In Connections tab: **+ Add Connection**
  - In Sources tab: **+ Add Source**
  - In Tools tab: **Add to Agent** (per tool row)

- Agent page section labels:
  - **Inputs** — Actions: **+ Add Source** / **Attach Existing Source**
  - **Tools** — Actions: **+ Add Tool** / **Remove**

---

## 15. Acceptance Criteria

MVP integration framework must support:

- Create/manage Connections per provider
- Delegated OAuth seamless flow (single "Add Connection" action creating a connected account)
- Define Triggers (templates) via config registry
- Create Sources tied to a Connection and Trigger
- Create Sources from Agent config and from Integration page
- Show provider-specific Sources list and global Sources list
- Define Tools (templates) via config registry
- Create AgentTools tied to an Agent, Connection, and Tool
- Enable/disable AgentTools per agent; browse tool catalog per provider
- Persist and validate configs using registries (triggers + tools)
- Store runtime cursor on TaskSource; deduplicate via EventInbox
- Tool invocation: agent calls tool → load handler → execute with connection credentials → return structured output

---

## Appendix A: Common Provider Mappings

| Provider     | Connection types            | Trigger examples   | Source resource examples   | Tool examples                 |
| ------------ | --------------------------- | ------------------ | -------------------------- | ----------------------------- |
| Outlook      | delegated OAuth, app-only   | New Email          | mailbox+folder             | Send Email, Reply, Move Email |
| Gmail        | OAuth user, service account | New Email          | label/query                | Send Email, Add Label         |
| Google Drive | OAuth user, service account | New File           | folder/shared drive folder | Upload File, Move File        |
| SharePoint   | delegated, app-only         | New File           | site+library+folder        | Upload File, Create Folder    |
| OneDrive     | delegated, app-only         | New File           | drive+folder               | Upload File, Move File        |
| AWS S3       | keys/role                   | New Object         | bucket+prefix              | Upload Object, Download       |
| Salesforce   | OAuth/JWT                   | New/Changed Record | object+query               | Create Record, Query Records  |
| ServiceNow   | OAuth/basic                 | New/Changed Record | table+query                | Create Record, Update Record  |
