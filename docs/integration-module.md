# App Integrations System

**Enterprise Self-Hosted, Air-Gapped Ready AI Agent Platform**

---

## Table of Contents

1. [Overview & Design Decisions](#1-overview--design-decisions)
2. [Data Flow & Architecture](#2-data-flow--architecture)
3. [Configuration Files](#3-configuration-files)
   - [3.1 Auth Schemas](#31-auth-schemas-configuration)
   - [3.2 Tools (Actions)](#32-tools-actions-configuration)
   - [3.3 Triggers](#33-triggers-configuration)
   - [3.4 Integrations](#34-integrations-configuration)
4. [Database Schema](#4-database-schema)
5. [Backend Architecture](#5-backend-architecture)
   - [5.1 Folder Structure](#51-folder-structure)
   - [5.2 Hybrid Auth Architecture](#52-hybrid-auth-architecture)
   - [5.3 Base Integration Client](#53-base-integration-client)
   - [5.4 Factory and Registry](#54-factory-and-registry)
   - [5.5 Trigger Executor & Runtime](#55-trigger-executor--runtime)
   - [5.6 Auth Handlers](#56-auth-handlers)
6. [Tools Architecture](#6-tools-architecture)
   - [6.1 Tool Types Overview](#61-tool-types-overview)
   - [6.2 Handler Config Format](#62-handler-config-format)
   - [6.3 ToolsFactory Architecture](#63-toolsfactory-architecture)
   - [6.4 Connection Resolution for Tools](#64-connection-resolution-for-tools)
   - [6.5 Tool Execution Flow](#65-tool-execution-flow)
   - [6.6 Agent Workflow Integration](#66-agent-workflow-integration)
7. [Triggers Architecture](#7-triggers-architecture)
   - [7.1 Trigger System Overview](#71-trigger-system-overview)
   - [7.2 Polling Architecture](#72-polling-architecture)
   - [7.3 Handler Config Format](#73-handler-config-format)
   - [7.4 Trigger Runner Implementation](#74-trigger-runner-implementation)
   - [7.5 Polling State Management](#75-polling-state-management)
   - [7.6 TriggerInbox Processing](#76-triggerinbox-processing)
   - [7.7 Event Normalization](#77-event-normalization)
   - [7.8 Scheduler & Celery Integration](#78-scheduler--celery-integration)
8. [OAuth Architecture](#8-oauth-architecture)
   - [8.1 OAuth Types Overview](#81-oauth-types-overview)
   - [8.2 OAuth2User Flow (User-Delegated)](#82-oauth2user-flow-user-delegated)
   - [8.3 OAuth2App Flow (Client Credentials)](#83-oauth2app-flow-client-credentials)
   - [8.4 OAuth Configuration in Auth Schemas](#84-oauth-configuration-in-auth-schemas)
   - [8.5 OAuth Handlers Implementation](#85-oauth-handlers-implementation)
   - [8.6 OAuth API Endpoints](#86-oauth-api-endpoints)
   - [8.7 Redirect URI Configuration](#87-redirect-uri-configuration)
9. [Implementation Examples](#9-implementation-examples)
10. [Appendix](#10-appendix)

---

## 1. Overview & Design Decisions

### 1.1 Goals

This module provides a unified system for:

- Managing external service integrations such as email, file storage, CRM, ERP, other APIs
- Supporting **multiple auth types per integration** (OAuth app-only credentials, OAuth user delegated, API keys, AWS credentials)
- Supporting **multiple connections per integration** (e.g., multiple AWS S3 buckets, multiple email accounts, multiple CRM accounts, etc.)
- **Actions** for tool-driven agent automation (send email, download file, create contact, etc.) which can be used by agents to perform tasks
- **Triggers** for event-driven agent automation (email received, file uploaded, etc.) which can be used by platform to generate tasks for agents to perform
- Easy DB seeding and dynamic credential form rendering for UI
- Air-gapped/offline environment compatibility using polling-first architecture

### 1.2 Key Design Decisions

| Decision             | Approach                                                                                            |
| -------------------- | --------------------------------------------------------------------------------------------------- |
| Multi-auth handling  | Single integration entry supports array of auth schemas                                             |
| Trigger scope        | Defined at integration level; AgentTrigger binds to specific connection                             |
| Config organization  | Separate files: `auth_schemas.py`, `tools.py`, `triggers.py`, `integrations.py`                     |
| Credential storage   | Fernet-encrypted JSON in `encrypted_credentials` column                                             |
| Polling architecture | Scheduler + TriggerRunner + AgentTrigger (with state) + TriggerInbox with cursor/watermark tracking |

### 1.3 Key Principles

- **Modular Design**: Factory pattern and abstract base classes for easy addition of new integrations
- **Air-Gapped Focus**: All logic is offline-post-setup; device code flows for OAuth; bundled configs in Docker images
- **Security**: Credentials encrypted via `cryptography.Fernet`; no plaintext storage/logs
- **Extensibility**: Built-in integrations via code; custom via user-uploaded OpenAPI specs
- **Resilient Auth**: Automatic token refresh with exponential backoff; graceful degradation on auth failures; user notification on re-auth required
- **Audit Trail**: All credential changes, auth failures, and re-auth events logged for compliance

### 1.4 Open Source References

- **Activepieces**: https://github.com/activepieces/activepieces/tree/main/packages/pieces/community
- **Sim Blocks**: https://github.com/simstudioai/sim/tree/main/apps/sim/blocks
- **Flowise**: https://github.com/FlowiseAI/Flowise/tree/main/packages/components/nodes/tools
- **Agno Tools**: https://github.com/agno-agi/agno/tree/main/libs/agno/agno/tools
- **N8N Nodes**: https://github.com/n8n-io/n8n/tree/master/packages/nodes-base

### Documentation References

- **Flowise Documentation**: https://docs.flowiseai.com/integrations
- **Activepieces Documentation**: https://www.activepieces.com/docs/build-pieces/building-pieces/overview
- **Sim Studio Documentation**: https://docs.sim.ai/triggers
- **Leena AI Documentation**: https://docs.leena.ai/integrations

---

## 2. Data Flow & Architecture

### 2.1 Complete Integration Architecture

This diagram shows the end-to-end flow of the integration module, from configuration seeding to task generation and agent action execution.

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              INTEGRATION MODULE ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. CONFIGURATION LAYER (Seeded on Startup)                                             │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  configs/auth_schemas.py     configs/tools.py           configs/triggers.py            │
│  ┌──────────────────┐        ┌──────────────────┐      ┌──────────────────┐           │
│  │ AUTH_SCHEMAS     │        │ ALL_TOOLS        │      │ ALL_TRIGGERS     │           │
│  │ ├─ ms_graph_...  │        │ ├─ send_email    │      │ ├─ new_email     │           │
│  │ ├─ aws_s3        │        │ ├─ upload_file   │      │ ├─ new_object    │           │
│  │ └─ gmail_oauth   │        │ └─ list_objects  │      │ └─ file_created  │           │
│  └──────────────────┘        └──────────────────┘      └──────────────────┘           │
│                                                                                         │
│  configs/integrations.py                                                               │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ INTEGRATIONS                                               │                        │
│  │ ├─ outlook   → supported_auth_schemas: [ms_graph_...]     │                        │
│  │ ├─ gmail     → supported_auth_schemas: [gmail_oauth]      │                        │
│  │ └─ aws       → supported_auth_schemas: [aws_s3]           │                        │
│  └────────────────────────────────────────────────────────────┘                        │
│            │                           │                         │                      │
│            └───────────────────────────┴─────────────────────────┘                      │
│                                        │                                                │
│                                        ▼ Seed Loader (On Startup)                       │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 2. DATABASE LAYER (Runtime Data)                                                       │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌────────────────┐    ┌─────────────┐    ┌────────────────┐                          │
│  │ Integration    │    │ Tool        │    │ Trigger        │                          │
│  │ (Catalog)      │◄───┤ (Catalog)   │    │ (Catalog)      │                          │
│  ├────────────────┤    ├─────────────┤    ├────────────────┤                          │
│  │ key            │    │ slug        │    │ slug           │                          │
│  │ display_name   │    │ integration │    │ integration    │                          │
│  │ auth_schemas[] │    │ handler     │    │ handler        │                          │
│  └────────┬───────┘    │ input_schema│    │ input_schema   │                          │
│           │            └──────┬──────┘    └───────┬────────┘                          │
│           │                   │                   │                                    │
│           ▼                   ▼                   ▼                                    │
│  ┌────────────────┐    ┌─────────────┐    ┌────────────────┐                          │
│  │ Connection     │    │ AgentTool   │    │ AgentTrigger   │                          │
│  │ (User Auth)    │◄───┤ (Binding)   │◄───┤ (Binding)      │                          │
│  ├────────────────┤    ├─────────────┤    ├────────────────┤                          │
│  │ integration_id │    │ agent_id    │    │ agent_id       │                          │
│  │ auth_schema    │    │ tool_id     │    │ trigger_id     │                          │
│  │ encrypted_     │    │ connection  │    │ connection_id  │◄─── Required             │
│  │   credentials  │    │   _id       │    │ cursor         │                          │
│  │ connection_    │    │ config      │    │ next_run_at    │                          │
│  │   config       │    └─────────────┘    │ locked_until   │                          │
│  └────────────────┘                       └────────┬───────┘                          │
│                                                    │                                   │
└────────────────────────────────────────────────────┼───────────────────────────────────┘
                                                     │
                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 3. TRIGGER POLLING FLOW (Event-Driven Task Generation)                                 │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌──────────────────┐                                                                  │
│  │ Celery Beat      │ Every 30-60s                                                     │
│  │ (Scheduler)      │──────┐                                                           │
│  └──────────────────┘      │                                                           │
│                            ▼                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐                 │
│  │ SELECT AgentTrigger WHERE:                                        │                 │
│  │   - is_enabled = true                                             │                 │
│  │   - next_run_at <= NOW()                                          │                 │
│  │   - locked_until IS NULL OR locked_until <= NOW()                 │                 │
│  │ FOR UPDATE SKIP LOCKED                                            │                 │
│  └───────────────────────┬───────────────────────────────────────────┘                 │
│                          │                                                             │
│                          ▼                                                             │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ TriggerRunner (Celery Task)                                │                        │
│  ├────────────────────────────────────────────────────────────┤                        │
│  │ 1. Load: AgentTrigger + Connection + Trigger               │                        │
│  │ 2. Decrypt credentials from Connection.encrypted_token     │                        │
│  │ 3. Get auth handler → get_auth_headers()                   │                        │
│  │ 4. Execute trigger handler:                                │                        │
│  │    integrations/{provider}/triggers.py                     │                        │
│  │    def poll_new_emails(cursor, config, context)            │                        │
│  │ 5. Handler returns: {events[], cursor, has_more}           │                        │
│  └────────────────────────┬───────────────────────────────────┘                        │
│                           │                                                            │
│                           ▼                                                            │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ For each event from trigger handler:                       │                        │
│  │ ┌────────────────────────────────────────────────────────┐ │                        │
│  │ │ TriggerInbox.create(                                   │ │                        │
│  │ │   agent_trigger_id = ...                               │ │                        │
│  │ │   event_type = "email_received"                        │ │                        │
│  │ │   payload = { /* normalized event data */ }            │ │                        │
│  │ │   metadata = {                                         │ │                        │
│  │ │     connection_id,                                     │ │                        │
│  │ │     integration_key,                                   │ │                        │
│  │ │     trigger_slug                                       │ │                        │
│  │ │   }                                                    │ │                        │
│  │ │   dedupe_key = hash(event_id + agent_trigger_id)      │ │                        │
│  │ │   status = "pending"                                   │ │                        │
│  │ │ )                                                      │ │                        │
│  │ └────────────────────────────────────────────────────────┘ │                        │
│  │                                                            │                        │
│  │ Update AgentTrigger:                                       │                        │
│  │   - cursor = new_cursor                                    │                        │
│  │   - next_run_at = NOW() + polling_interval                 │                        │
│  │   - locked_until = NULL (release lock)                     │                        │
│  └────────────────────────────────────────────────────────────┘                        │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 4. INBOX PROCESSING FLOW (Event → Agent Task)                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌──────────────────┐                                                                  │
│  │ Celery Beat      │ Every 10-30s                                                     │
│  │ (Scheduler)      │──────┐                                                           │
│  └──────────────────┘      │                                                           │
│                            ▼                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐                 │
│  │ SELECT TriggerInbox WHERE:                                        │                 │
│  │   - status = 'pending'                                            │                 │
│  │   - created_at <= NOW() - debounce_window                         │                 │
│  │ ORDER BY created_at ASC                                           │                 │
│  │ LIMIT 50                                                          │                 │
│  │ FOR UPDATE SKIP LOCKED                                            │                 │
│  └───────────────────────┬───────────────────────────────────────────┘                 │
│                          │                                                             │
│                          ▼                                                             │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ InboxProcessor (Celery Task)                               │                        │
│  ├────────────────────────────────────────────────────────────┤                        │
│  │ For each TriggerInbox event:                               │                        │
│  │ 1. Extract metadata (connection_id, integration, trigger)  │                        │
│  │ 2. Load AgentTrigger → Agent                               │                        │
│  │ 3. Create Task:                                            │                        │
│  │    ┌─────────────────────────────────────────────────────┐ │                        │
│  │    │ Task.create(                                        │ │                        │
│  │    │   agent_id = agent_trigger.agent_id                 │ │                        │
│  │    │   name = f"Handle {trigger.display_name}"           │ │                        │
│  │    │   description = event.payload (formatted)           │ │                        │
│  │    │   metadata = {                                      │ │                        │
│  │    │     trigger_event: event.payload,                   │ │                        │
│  │    │     connection_id: event.metadata.connection_id,    │ │                        │
│  │    │     integration_key: event.metadata.integration_key │ │                        │
│  │    │   }                                                 │ │                        │
│  │    │   status = "pending"                                │ │                        │
│  │    │ )                                                   │ │                        │
│  │    └─────────────────────────────────────────────────────┘ │                        │
│  │ 4. Update TriggerInbox.status = "processed"                │                        │
│  └────────────────────────┬───────────────────────────────────┘                        │
│                           │                                                            │
└───────────────────────────┼────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ 5. AGENT EXECUTION FLOW (Task Processing with Tool Actions)                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ Agent Workflow Runner                                      │                        │
│  ├────────────────────────────────────────────────────────────┤                        │
│  │ 1. Receive Task (from trigger or user-created)             │                        │
│  │ 2. Load Agent + available tools (AgentTool or config)      │                        │
│  │ 3. Extract connection_id from Task.metadata (if trigger)   │                        │
│  │ 4. Initialize LLM with system prompt + tools               │                        │
│  └────────────────────────┬───────────────────────────────────┘                        │
│                           │                                                            │
│                           ▼                                                            │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ LLM Decision Loop (Agent Reasoning)                        │                        │
│  │ ┌────────────────────────────────────────────────────────┐ │                        │
│  │ │ Agent analyzes task:                                   │ │                        │
│  │ │ "New email from customer about refund request.         │ │                        │
│  │ │  I need to:                                            │ │                        │
│  │ │  1. Get customer details from CRM                      │ │                        │
│  │ │  2. Check refund policy                                │ │                        │
│  │ │  3. Send response email"                               │ │                        │
│  │ └────────────────────────────────────────────────────────┘ │                        │
│  │                                                            │                        │
│  │ LLM decides to call tool: outlook_send_email               │                        │
│  └────────────────────────┬───────────────────────────────────┘                        │
│                           │                                                            │
│                           ▼                                                            │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ ToolsFactory.execute_tool()                                │                        │
│  ├────────────────────────────────────────────────────────────┤                        │
│  │ 1. Resolve connection_id:                                  │                        │
│  │    Priority:                                               │                        │
│  │    a) AgentTool.connection_id (if pinned)                  │                        │
│  │    b) Task.metadata.connection_id (from trigger)           │                        │
│  │    c) Agent.config.tools[].connection_id (per-tool map)    │                        │
│  │    → Error if none found (no auto-selection!)              │                        │
│  │                                                            │                        │
│  │ 2. Load Connection + decrypt credentials                   │                        │
│  │ 3. Load Tool → get handler reference                       │                        │
│  │ 4. Get auth handler → get_auth_headers()                   │                        │
│  │ 5. Prepare tool_runtime context:                           │                        │
│  │    {                                                       │                        │
│  │      connection_id,                                        │                        │
│  │      auth_headers,                                         │                        │
│  │      credentials,                                          │                        │
│  │      connection_config                                     │                        │
│  │    }                                                       │                        │
│  │ 6. Execute handler:                                        │                        │
│  │    integrations/{provider}/actions.py                      │                        │
│  │    def send_email(to, subject, body, tool_runtime)         │                        │
│  └────────────────────────┬───────────────────────────────────┘                        │
│                           │                                                            │
│                           ▼                                                            │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ Integration Provider Action Handler                        │                        │
│  ├────────────────────────────────────────────────────────────┤                        │
│  │ integrations/outlook/actions.py                            │                        │
│  │ ┌────────────────────────────────────────────────────────┐ │                        │
│  │ │ class OutlookActions:                                  │ │                        │
│  │ │   def send_email(self, to, subject, body,              │ │                        │
│  │ │                  tool_runtime):                        │ │                        │
│  │ │     connection = get_connection(tool_runtime)          │ │                        │
│  │ │     client = GraphClient(connection)                   │ │                        │
│  │ │     payload = build_send_email_payload(...)            │ │                        │
│  │ │     response = await client.post(                      │ │                        │
│  │ │       "/me/sendMail", payload                          │ │                        │
│  │ │     )                                                  │ │                        │
│  │ │     return {"success": True, "message_id": ...}        │ │                        │
│  │ └────────────────────────────────────────────────────────┘ │                        │
│  └────────────────────────┬───────────────────────────────────┘                        │
│                           │                                                            │
│                           ▼                                                            │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ External API (Microsoft Graph)                             │                        │
│  │ ┌────────────────────────────────────────────────────────┐ │                        │
│  │ │ POST https://graph.microsoft.com/v1.0/me/sendMail      │ │                        │
│  │ │ Authorization: Bearer {access_token}                   │ │                        │
│  │ │ {                                                      │ │                        │
│  │ │   "message": {                                         │ │                        │
│  │ │     "subject": "Re: Refund Request",                   │ │                        │
│  │ │     "body": {...},                                     │ │                        │
│  │ │     "toRecipients": [...]                              │ │                        │
│  │ │   }                                                    │ │                        │
│  │ │ }                                                      │ │                        │
│  │ │                                                        │ │                        │
│  │ │ ← Response: 202 Accepted                               │ │                        │
│  │ └────────────────────────────────────────────────────────┘ │                        │
│  └────────────────────────┬───────────────────────────────────┘                        │
│                           │                                                            │
│                           ▼ Result                                                     │
│  ┌────────────────────────────────────────────────────────────┐                        │
│  │ Agent receives tool result:                                │                        │
│  │ {"success": true, "message_id": "AAMkAD..."}               │                        │
│  │                                                            │                        │
│  │ Agent continues reasoning or completes task                │                        │
│  │ Task.status = "completed"                                  │                        │
│  └────────────────────────────────────────────────────────────┘                        │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ KEY COMPONENTS SUMMARY                                                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│ ┌─────────────────────┐  ┌──────────────────────┐  ┌────────────────────────┐          │
│ │ Triggers            │  │ Actions (Tools)      │  │ Connections            │          │
│ ├─────────────────────┤  ├──────────────────────┤  ├────────────────────────┤          │
│ │ • Event polling     │  │ • Agent-initiated    │  │ • Auth storage         │          │
│ │ • Generate tasks    │  │ • External API calls │  │ • Credential encrypt   │          │
│ │ • Cursor tracking   │  │ • LLM tool calls     │  │ • Multi-auth support   │          │
│ │ • TriggerInbox      │  │ • Connection context │  │ • Token refresh        │          │
│ └─────────────────────┘  └──────────────────────┘  └────────────────────────┘          │
│                                                                                         │
│ DATA FLOW:                                                                              │
│ Config → DB Seed → Connection Auth → Trigger Poll → TriggerInbox → Task Creation →     │
│ Agent Execution → Tool Call → Connection Resolve → API Request → Result → Task Done    │
│                                                                                         │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 2.2 High-Level Setup and Execution Flow

1. **Seeded catalog is available** (admin / system):
   - Integrations, tools, triggers, and auth schemas are loaded from config files.
   - Tools and triggers include handler references for runtime execution.

2. **User creates a Connection**:
   - Selects integration (e.g., Outlook).
   - Chooses an auth schema (e.g., client credentials).
   - Provides credentials and optional connection_config.
   - System stores encrypted credentials in `connections`.

3. **User binds tools and triggers**:

   **Tools** (choose one approach - see section 2.4 for details):
   - **Approach A (AgentTool table)**: Create AgentTool binding with optional connection pinning
   - **Approach B (Agent config)**: Add tool slugs to `agent.config.tools` array with connection mappings

   **Triggers** (always require explicit connection):
   - AgentTrigger: binds agent + trigger to connection (connection REQUIRED)
   - AgentTrigger initialized with cursor=null, next_run_at=now for immediate first poll

   **Connection Resolution Priority**:
   1. Explicit pinning (AgentTool.connection_id or agent.config.tools[].connection_id)
   2. Runtime context (from task metadata for trigger-driven tasks)
   3. Error if no connection available (never automatic/random selection)

4. **Polling execution**:
   - PollingScheduler selects due AgentTrigger rows (next_run_at <= NOW) and acquires locks.
   - TriggerRunner loads AgentTrigger + Connection + Trigger.
   - Trigger handler runs with cursor + config + credentials.
   - Normalized events are written to TriggerInbox with a dedupe_key.
   - AgentTrigger polling state updated (cursor, next_run_at, backoff, errors).

5. **Inbox processing**:
   - InboxProcessor leases pending TriggerInbox rows.
   - Connection context extracted from `TriggerInbox.metadata` and passed to Task.
   - Events are routed to the agent workflow entrypoint with connection context.
   - Rows are marked done or failed with retries/backoff.

### 2.3 Error Flow & Recovery

**Auth Failures**:

- Connection.is_valid set to False; associated AgentTriggers paused
- Owner notified to re-authenticate
- OAuth tokens auto-refresh before expiry; on failure → backoff → mark invalid

**Trigger Handler Failures**:

- AgentTrigger.error_count incremented; exponential backoff applied to next_run_at
- After 5 consecutive failures: AgentTrigger.is_enabled set to False, admin alerted
- Errors logged to AgentTrigger.last_error for debugging

**Tool Execution Failures**:

- Structured error returned to agent with retry_after hint
- Repeated failures (>10 in 1 hour) → Connection marked for review

**Concurrency & Locking**:

- AgentTrigger uses `SELECT FOR UPDATE SKIP LOCKED` to prevent duplicate execution
- Lock held via locked_until timestamp (typically handler_timeout + 60s)
- Expired locks allow retry by another worker

---

### 2.4 Tool-Connection Mapping: Two Approaches

The system supports two architectural approaches for binding tools to agents and mapping them to connections.

#### **Approach A: Database-Backed (AgentTool Table)**

Uses a dedicated `AgentTool` table to store explicit bindings between agents, tools, and connections.

**Key Characteristics**:

- Explicit rows for each agent-tool binding in database
- Optional connection pinning via `connection_id` column
- Database-enforced constraints (unique constraint, foreign keys)
- Built-in audit trail via timestamps and foreign key relationships
- Query-friendly for "which agents use this tool?"

**When to Use**:

- Multi-integration agents with complex connection requirements
- Enterprise deployments requiring audit trails
- Multi-tenant SaaS with performance needs (indexed FKs)
- Need row-level permissions or fine-grained access control

**Trade-offs**:

- ✅ Strong data integrity via DB constraints
- ✅ Better query performance (indexed FK joins)
- ✅ Clear audit trail with timestamps
- ❌ Additional table and schema complexity
- ❌ Requires database migrations for structure changes

---

#### **Approach B: Config-Backed (Agent.config JSONB)**

Stores tool bindings with per-tool connection mapping directly in the agent's configuration JSON.

**Key Characteristics**:

- Each tool in config includes its own `connection_id`
- No extra database tables or joins
- Flexible JSON structure, easy to extend
- Single atomic update to modify all tools
- Application-level validation required

**When to Use**:

- Simple deployments without strict audit needs
- Trigger-driven workflows (connection from trigger context)
- Rapid prototyping and iteration
- Agents with few tools or simple connection needs

**Trade-offs**:

- ✅ Simpler schema (no extra tables)
- ✅ Flexible configuration structure
- ✅ Easy bulk updates (single JSON change)
- ❌ No database-level constraints
- ❌ Slower queries (JSONB scans vs indexed FKs)
- ❌ No built-in audit trail

---

#### **Hybrid Approach**

Combine both patterns for flexibility:

- Use `agent.config.tools` (with per-tool connection_id) for simple agents
- Create `AgentTool` rows for agents requiring database-enforced constraints and audit trails
- Resolution priority: AgentTool.connection_id → agent.config → runtime context → error

**Benefits**: Start simple, add complexity only when needed

---

#### **Connection Resolution Priority**

Regardless of approach, connection resolution follows this priority:

1. **Explicit Pinning**: `AgentTool.connection_id` or `agent.config.tools[].connection_id`
2. **Runtime Context**: `tool_runtime.connection_id` (from task metadata, trigger event)
3. **Error**: Never automatic/random selection

**Trigger Context Flow**:

```
Trigger Event → TriggerInbox.metadata → Task.metadata → tool_runtime.connection_id
```

This ensures tools use the same connection that received the trigger event (e.g., reply to email from correct account).

---

#### **Decision Matrix**

| Use Case                     | Recommended       | Why                        |
| ---------------------------- | ----------------- | -------------------------- |
| Single integration per agent | **B (Config)**    | Simpler, less overhead     |
| Trigger-driven only          | **B (Config)**    | Connection from context    |
| Manual task creation         | **A (AgentTool)** | Pre-configured connections |
| Enterprise audit             | **A (AgentTool)** | Timestamps + constraints   |
| Multi-tenant SaaS            | **A (AgentTool)** | Query performance          |
| Rapid prototyping            | **B (Config)**    | Fast iteration             |
| Production at scale          | **Hybrid**        | Flexibility + simplicity   |

See **Section 6.4** for detailed implementation examples and code.

---

## 3. Configuration Files

### 3.1 Auth Schemas Configuration

**File: `backend/configs/auth_schemas.py`**

Centralized auth schema definitions with consistent structure for credential form rendering.
These schemas are seeded into database on startup and referenced by Connection.auth_schema_key.

**Preset Template Resolution**: URLs in `preset` may contain variables (e.g., `{tenant_id}`). At runtime:

1. Resolved from user-provided credentials (e.g., `credentials["tenant_id"]`)
2. If missing, resolved from connection_config
3. If still missing, raises validation error before API call

Example: `https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token` uses `credentials["tenant_id"]`

#### Supported Auth Types

| Auth Type    | Description                | Example Integrations      |
| ------------ | -------------------------- | ------------------------- |
| `None`       | No authentication required | Local filesystem          |
| `Basic`      | Username/password          | Legacy APIs               |
| `Bearer`     | Static bearer token        | Pre-generated tokens      |
| `APIKey`     | API key in header/query    | OpenAI, Anthropic, Gemini |
| `OAuth2User` | User-delegated OAuth2 flow | Gmail, Slack              |
| `OAuth2App`  | App-level OAuth2 flow      | Microsoft Graph (app)     |
| `AWSSignV4`  | AWS Signature V4           | AWS S3, DynamoDB          |

#### Full Implementation

```python
# backend/configs/auth_schemas.py
"""
Auth Schemas Configuration
==========================
Centralized authentication schema definitions for all integrations.
Each schema defines:
- preset: System-provided values (token URLs, scopes, etc.)
- user_fields: Fields the user must provide during connection setup
- token_fields: Fields stored after OAuth token exchange (optional)
- connection_config_fields: Non-sensitive connection-specific config (optional)
"""

from enum import Enum
from typing import Dict, Any, List, Optional


class AuthType(str, Enum):
    """Supported authentication types."""
    NONE = "None"
    BASIC = "Basic"
    BEARER = "Bearer"
    OAUTH2_USER = "OAuth2User"  # User-delegated OAuth2 flow (acts on behalf of a user)
    OAUTH2_APP = "OAuth2App"    # App-level OAuth2 flow (application permissions)
    API_KEY = "APIKey"
    AWS_SIGV4 = "AWSSignV4"


class FieldType(str, Enum):
    """Input field types for form rendering."""
    TEXT = "text"
    PASSWORD = "password"
    URL = "url"
    SELECT = "select"
    BOOLEAN = "boolean"
    NUMBER = "number"
    TEXTAREA = "textarea"


def _field(
    name: str,
    label: str,
    description: str,
    field_type: FieldType = FieldType.TEXT,
    required: bool = True,
    example: str = "",
    default: Any = None,
    options: List[str] = None,
    sensitive: bool = False,
    placeholder: str = "",
) -> Dict[str, Any]:
    """
    Helper function to create field definitions with consistent structure.

    Args:
        name: Internal field name (used in credentials dict)
        label: Display label for UI
        description: Help text for the field
        field_type: Input type for form rendering
        required: Whether field is required
        example: Example value to show in UI
        default: Default value if not provided
        options: List of options for SELECT type
        sensitive: Whether field should be masked/encrypted
        placeholder: Placeholder text for input
    """
    field_def = {
        "name": name,
        "label": label,
        "description": description,
        "type": field_type.value,
        "required": required,
        "sensitive": sensitive,
    }
    if example:
        field_def["example"] = example
    if placeholder:
        field_def["placeholder"] = placeholder
    if default is not None:
        field_def["default"] = default
    if options:
        field_def["options"] = options
    return field_def


# =============================================================================
# AUTH SCHEMA DEFINITIONS
# =============================================================================

AUTH_SCHEMAS: Dict[str, Dict[str, Any]] = {

    # =========================================================================
    # MICROSOFT GRAPH / OFFICE 365
    # =========================================================================

    "microsoft_graph_client_credentials": {
        "auth_type": AuthType.OAUTH2_APP.value,
        "display_name": "Microsoft Graph (App-Only)",
        "description": "OAuth2 client credentials flow for Microsoft Graph API. Use for background services that don't require user context (e.g., mailbox polling, calendar sync).",
        "docs_url": "https://learn.microsoft.com/en-us/graph/auth-v2-service",
        "preset": {
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        "input_fields": {
            "CLIENT_ID": _field(
                name="client_id",
                label="Client ID",
                description="The Application (client) ID from Azure AD App Registration",
                example="123e4567-e89b-12d3-a456-426614174000",
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            ),
            "CLIENT_SECRET": _field(
                name="client_secret",
                label="Client Secret",
                description="The client secret value (not the secret ID) from Azure AD",
                field_type=FieldType.PASSWORD,
                example="your-client-secret-value",
                sensitive=True,
            ),
            "TENANT_ID": _field(
                name="tenant_id",
                label="Tenant ID",
                description="The Directory (tenant) ID from Azure AD",
                example="123e4567-e89b-12d3-a456-426614174000",
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
            ),
        },
    },

    "microsoft_graph_delegated": {
        "auth_type": AuthType.OAUTH2_USER.value,
        "display_name": "Microsoft Graph (User Delegated)",
        "description": "OAuth2 delegated flow for Microsoft Graph API. Requires user consent and acts on behalf of a signed-in user.",
        "docs_url": "https://learn.microsoft.com/en-us/graph/auth-v2-user",
        "preset": {
            "authorization_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Calendars.ReadWrite offline_access",
        },
        "input_fields": {
            "CLIENT_ID": _field(
                name="client_id",
                label="Client ID",
                description="The Application (client) ID from Azure AD App Registration",
                example="123e4567-e89b-12d3-a456-426614174000",
            ),
            "CLIENT_SECRET": _field(
                name="client_secret",
                label="Client Secret",
                description="The client secret value from Azure AD",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
            "TENANT_ID": _field(
                name="tenant_id",
                label="Tenant ID",
                description="The Directory (tenant) ID from Azure AD. Use 'common' for multi-tenant apps.",
                example="123e4567-e89b-12d3-a456-426614174000",
                default="common",
            ),
        },
        "token_fields": {
            "access_token": {"sensitive": True, "type": "text"},
            "refresh_token": {"sensitive": True, "type": "text"},
            "expires_at": {"type": "number"},
            "token_type": {"type": "text"},
        },
    },

    # =========================================================================
    # GOOGLE WORKSPACE
    # =========================================================================

    "gmail_oauth": {
        "auth_type": AuthType.OAUTH2_USER.value,
        "display_name": "Gmail",
        "description": "OAuth2 authentication for Gmail API. Supports device code flow for air-gapped environments.",
        "docs_url": "https://developers.google.com/gmail/api/auth/about-auth",
        "preset": {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scope": "https://mail.google.com/",
            "access_type": "offline",
            "prompt": "consent",
        },
        "input_fields": {
            "CLIENT_ID": _field(
                name="client_id",
                label="Client ID",
                description="OAuth Client ID from Google Cloud Console",
                example="123456789-abc123.apps.googleusercontent.com",
            ),
            "CLIENT_SECRET": _field(
                name="client_secret",
                label="Client Secret",
                description="OAuth Client Secret from Google Cloud Console",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
        },
        "token_fields": {
            "access_token": {"sensitive": True},
            "refresh_token": {"sensitive": True},
            "expires_at": {"type": "number"},
        },
    },

    "google_service_account": {
        "auth_type": AuthType.OAUTH2_APP.value,
        "display_name": "Google Service Account",
        "description": "Service account authentication for Google APIs. Use for server-to-server integrations.",
        "docs_url": "https://cloud.google.com/iam/docs/service-accounts",
        "preset": {
            "token_url": "https://oauth2.googleapis.com/token",
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        },
        "input_fields": {
            "SERVICE_ACCOUNT_JSON": _field(
                name="service_account_json",
                label="Service Account JSON",
                description="The full JSON key file content from Google Cloud Console",
                field_type=FieldType.TEXTAREA,
                sensitive=True,
                placeholder='{"type": "service_account", "project_id": "...", ...}',
            ),
            "DELEGATED_USER": _field(
                name="delegated_user",
                label="Delegated User Email",
                description="Email of user to impersonate (for domain-wide delegation)",
                required=False,
                example="admin@company.com",
            ),
        },
    },

    # =========================================================================
    # LLM PROVIDERS
    # =========================================================================

    "openai_auth": {
        "auth_type": AuthType.API_KEY.value,
        "display_name": "OpenAI",
        "description": "API key authentication for OpenAI services (GPT-4, DALL-E, Whisper, etc.)",
        "docs_url": "https://platform.openai.com/docs/api-reference/authentication",
        "preset": {
            "header_name": "Authorization",
            "header_prefix": "Bearer",
            "base_url": "https://api.openai.com/v1",
        },
        "input_fields": {
            "API_KEY": _field(
                name="api_key",
                label="OpenAI API Key",
                description="Your secret API key from OpenAI dashboard",
                field_type=FieldType.PASSWORD,
                example="sk-proj-xxxxxxxxxxxxxxxxxxxxxx",
                sensitive=True,
            ),
            "ORGANIZATION_ID": _field(
                name="organization_id",
                label="Organization ID",
                description="Optional: OpenAI organization ID for billing",
                required=False,
                example="org-xxxxxxxxxxxxxx",
            ),
        },
    },

    "anthropic_auth": {
        "auth_type": AuthType.API_KEY.value,
        "display_name": "Anthropic",
        "description": "API key authentication for Anthropic Claude models",
        "docs_url": "https://docs.anthropic.com/en/api/getting-started",
        "preset": {
            "header_name": "x-api-key",
            "base_url": "https://api.anthropic.com",
        },
        "input_fields": {
            "API_KEY": _field(
                name="api_key",
                label="Anthropic API Key",
                description="Your secret API key from Anthropic Console",
                field_type=FieldType.PASSWORD,
                example="sk-ant-api03-xxxxxxxxxxxxxx",
                sensitive=True,
            ),
        },
    },

    "gemini_auth": {
        "auth_type": AuthType.API_KEY.value,
        "display_name": "Google Gemini",
        "description": "API key authentication for Google Gemini models",
        "docs_url": "https://ai.google.dev/gemini-api/docs/api-key",
        "preset": {
            "query_param_name": "key",
            "base_url": "https://generativelanguage.googleapis.com/v1",
        },
        "input_fields": {
            "API_KEY": _field(
                name="api_key",
                label="Gemini API Key",
                description="Your API key from Google AI Studio",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
        },
    },

    "azure_openai_auth": {
        "auth_type": AuthType.API_KEY.value,
        "display_name": "Azure OpenAI",
        "description": "API key authentication for Azure OpenAI Service",
        "docs_url": "https://learn.microsoft.com/en-us/azure/ai-services/openai/",
        "preset": {
            "header_name": "api-key",
        },
        "input_fields": {
            "API_KEY": _field(
                name="api_key",
                label="Azure OpenAI API Key",
                description="API key from Azure OpenAI resource",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
            "ENDPOINT": _field(
                name="endpoint",
                label="Azure Endpoint",
                description="Your Azure OpenAI endpoint URL",
                field_type=FieldType.URL,
                example="https://your-resource.openai.azure.com",
            ),
            "DEPLOYMENT_NAME": _field(
                name="deployment_name",
                label="Deployment Name",
                description="Name of your model deployment",
                example="gpt-4-deployment",
            ),
            "API_VERSION": _field(
                name="api_version",
                label="API Version",
                description="Azure OpenAI API version",
                default="2024-02-01",
                example="2024-02-01",
            ),
        },
    },

    # =========================================================================
    # AWS SERVICES
    # =========================================================================

    "aws_s3_auth": {
        "auth_type": AuthType.AWS_SIGV4.value,
        "display_name": "AWS S3",
        "description": "AWS Signature V4 authentication for S3 and other AWS services",
        "docs_url": "https://docs.aws.amazon.com/general/latest/gr/signature-version-4.html",
        "preset": {
            "service": "s3",
            "signature_version": "s3v4",
        },
        "input_fields": {
            "AWS_ACCESS_KEY_ID": _field(
                name="aws_access_key_id",
                label="AWS Access Key ID",
                description="Access key ID from AWS IAM",
                example="AKIAIOSFODNN7EXAMPLE",
            ),
            "AWS_SECRET_ACCESS_KEY": _field(
                name="aws_secret_access_key",
                label="AWS Secret Access Key",
                description="Secret access key from AWS IAM",
                field_type=FieldType.PASSWORD,
                example="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                sensitive=True,
            ),
            "AWS_SESSION_TOKEN": _field(
                name="aws_session_token",
                label="AWS Session Token",
                description="Optional: Session token for temporary credentials",
                field_type=FieldType.PASSWORD,
                required=False,
                sensitive=True,
            ),
        },
        "connection_config_fields": {
            "region": _field(
                name="region",
                label="AWS Region",
                description="Default AWS region for operations",
                field_type=FieldType.SELECT,
                options=["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-south-1", "ap-southeast-1", "ap-northeast-1"],
                default="us-east-1",
            ),
            "default_bucket": _field(
                name="default_bucket",
                label="Default S3 Bucket",
                description="Default bucket for file operations",
                required=False,
            ),
        },
    },

    # =========================================================================
    # COLLABORATION TOOLS
    # =========================================================================

    "slack_oauth": {
        "auth_type": AuthType.OAUTH2_USER.value,
        "display_name": "Slack",
        "description": "OAuth2 authentication for Slack API",
        "docs_url": "https://api.slack.com/authentication/oauth-v2",
        "preset": {
            "authorization_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "scope": "chat:write,channels:read,channels:history,users:read,files:read",
        },
        "input_fields": {
            "CLIENT_ID": _field(
                name="client_id",
                label="Client ID",
                description="Slack App Client ID from app settings",
            ),
            "CLIENT_SECRET": _field(
                name="client_secret",
                label="Client Secret",
                description="Slack App Client Secret",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
        },
        "token_fields": {
            "access_token": {"sensitive": True},
            "bot_user_id": {"type": "text"},
            "team_id": {"type": "text"},
            "team_name": {"type": "text"},
        },
    },

    "slack_bot_token": {
        "auth_type": AuthType.BEARER.value,
        "display_name": "Slack Bot Token",
        "description": "Direct bot token authentication for Slack (simpler setup, no OAuth flow)",
        "docs_url": "https://api.slack.com/authentication/token-types",
        "preset": {
            "header_name": "Authorization",
            "header_prefix": "Bearer",
        },
        "input_fields": {
            "BOT_TOKEN": _field(
                name="bot_token",
                label="Bot User OAuth Token",
                description="Bot token starting with 'xoxb-' from Slack app settings",
                field_type=FieldType.PASSWORD,
                example="your-slack-bot-token-here",
                sensitive=True,
            ),
        },
    },

    # =========================================================================
    # GENERIC AUTH TYPES
    # =========================================================================

    "basic_auth": {
        "auth_type": AuthType.BASIC.value,
        "display_name": "Basic Authentication",
        "description": "HTTP Basic authentication with username and password",
        "preset": {},
        "input_fields": {
            "USERNAME": _field(
                name="username",
                label="Username",
                description="The username for authentication",
            ),
            "PASSWORD": _field(
                name="password",
                label="Password",
                description="The password for authentication",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
        },
    },

    "bearer_auth": {
        "auth_type": AuthType.BEARER.value,
        "display_name": "Bearer Token",
        "description": "Bearer token authentication (static token)",
        "preset": {
            "header_name": "Authorization",
            "header_prefix": "Bearer",
        },
        "input_fields": {
            "TOKEN": _field(
                name="token",
                label="Bearer Token",
                description="The bearer token for authentication",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
        },
    },

    "api_key_header": {
        "auth_type": AuthType.API_KEY.value,
        "display_name": "API Key (Header)",
        "description": "Generic API key authentication via HTTP header",
        "preset": {},
        "input_fields": {
            "API_KEY_NAME": _field(
                name="api_key_name",
                label="Header Name",
                description="Name of the HTTP header (e.g., 'X-API-Key', 'api-key')",
                example="X-API-Key",
            ),
            "API_KEY": _field(
                name="api_key",
                label="API Key",
                description="The API key value",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
        },
    },

    "api_key_query": {
        "auth_type": AuthType.API_KEY.value,
        "display_name": "API Key (Query Param)",
        "description": "API key authentication via query parameter",
        "preset": {
            "location": "query",
        },
        "input_fields": {
            "API_KEY_NAME": _field(
                name="api_key_name",
                label="Parameter Name",
                description="Name of the query parameter",
                example="api_key",
            ),
            "API_KEY": _field(
                name="api_key",
                label="API Key",
                description="The API key value",
                field_type=FieldType.PASSWORD,
                sensitive=True,
            ),
        },
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_auth_schema(schema_key: str) -> Optional[Dict[str, Any]]:
    """Get an auth schema by key."""
    return AUTH_SCHEMAS.get(schema_key)


def get_auth_schemas_by_type(auth_type: AuthType) -> List[str]:
    """Get all auth schema keys for a given auth type."""
    return [
        key for key, schema in AUTH_SCHEMAS.items()
        if schema.get("auth_type") == auth_type.value
    ]


def get_all_auth_schema_keys() -> List[str]:
    """Get all available auth schema keys."""
    return list(AUTH_SCHEMAS.keys())


def get_required_fields(schema_key: str) -> List[str]:
    """Get list of required field names for an auth schema."""
    schema = AUTH_SCHEMAS.get(schema_key, {})
    user_fields = schema.get("user_fields", {})
    return [
        field_def["name"]
        for field_def in user_fields.values()
        if field_def.get("required", True)
    ]
```

---

### 3.2 Tools (Actions) Configuration

**File: `backend/configs/tools.py`**

Tool/action definitions are organized by integration and include handler references for execution.

**Note**: Config file is named `tools.py` (catalog of tools), while provider files are named `actions.py` (implementation of actions).
Each tool includes:

- slug: unique identifier
- name, description
- integration_key
- input_schema / output_schema (JSONSchema)
- handler: module + function OR module + class + method

Tools and triggers follow the same config structure pattern (grouped by integration). The `input_schema` describes the tool's arguments for UI rendering and validation; the resolved values are passed into the tool handler at execution time.

Handler formats:

```python
# Class-based handler (for stateful tools)
{
  "module": "integrations.providers.outlook.actions",
  "class": "OutlookActions",
  "method": "send_email",
  "init_args": ["organization_schema", "data_store"]  # Optional DI dependencies
}

# Function-based handler (for simple tools)
{
  "module": "integrations.email.handlers",
  "function": "send_email_handler"
}
```

**Handler Dependency Injection**: `init_args` lists constructor dependencies resolved from DI container (common: `organization_schema`, `data_store`, `logger`). Function handlers receive `(credentials, config, inputs)` directly.

Example tools config structure:

```python
# backend/configs/tools.py
"""
Tools Configuration
===================
Tool definitions organized by integration for easy maintenance.
Each tool includes:
- slug: Unique identifier
- name: Display name
- description: What the tool does
- integration_key: Parent integration
- input_schema: JSONSchema for tool arguments
- output_schema: JSONSchema for tool results
- handler: module/function or module/class/method for runtime execution
"""

from typing import Dict, Any, List


# =============================================================================
# OUTLOOK / MICROSOFT GRAPH TOOLS
# =============================================================================

OUTLOOK_TOOLS: List[Dict[str, Any]] = [
    {
        "slug": "outlook_send_email",
        "name": "Send Email in Outlook",
        "description": "Sends an email message...",
        "integration_key": "outlook",
        "input_schema": {"type": "object", "properties": {"message_id": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"success": {"type": "boolean"}}},
        "handler": {
            "module": "integrations.office_365.outlook",
            "class": "Outlook",
            "method": "send_email",
        },
    },
    {
        "slug": "outlook_flag_email",
        "name": "Flag Email in Outlook",
        "description": "Flags an email message...",
        "integration_key": "outlook",
        "input_schema": {"type": "object", "properties": {"message_id": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"success": {"type": "boolean"}}},
        "handler": {
            "module": "integrations.office_365.outlook",
            "class": "Outlook",
            "method": "flag_email",
        },
    },
    {
        "slug": "outlook_archive_email",
        "name": "Archive Email in Outlook",
        "description": "Archives an email message...",
        "integration_key": "outlook",
        "input_schema": {"type": "object", "properties": {"message_id": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"success": {"type": "boolean"}}},
        "handler": {
            "module": "integrations.office_365.outlook",
            "class": "Outlook",
            "method": "archive_email",
        },
    },
]

AWS_S3_TOOLS: List[Dict[str, Any]] = [
    {
        "slug": "aws_s3_upload_structured_data",
        "name": "Upload Structured Data to S3",
        "description": "Uploads structured data to S3...",
        "integration_key": "aws_s3",
        "input_schema": {"type": "object", "properties": {"bucket": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"s3_uri": {"type": "string"}}},
        "handler": {
            "module": "integrations.aws.aws_s3",
            "class": "AWSS3",
            "method": "tool_upload_structured_data",
            "init_args": ["organization_schema", "data_store"],
        },
    },
    {
        "slug": "aws_s3_download_file",
        "name": "Download File from S3",
        "description": "Downloads a file from S3...",
        "integration_key": "aws_s3",
        "input_schema": {"type": "object", "properties": {"bucket": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"file_uri": {"type": "string"}}},
        "handler": {
            "module": "integrations.aws.aws_s3",
            "class": "AWSS3",
            "method": "tool_download_file",
            "init_args": ["organization_schema", "data_store"],
        },
    },
    {
        "slug": "aws_s3_delete_file",
        "name": "Delete File from S3",
        "description": "Deletes a file from S3...",
        "integration_key": "aws_s3",
        "input_schema": {"type": "object", "properties": {"bucket": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"success": {"type": "boolean"}}},
        "handler": {
            "module": "integrations.aws.aws_s3",
            "class": "AWSS3",
            "method": "tool_delete_file",
            "init_args": ["organization_schema", "data_store"],
        },
    },
]

ALL_TOOLS: List[Dict[str, Any]] = OUTLOOK_TOOLS + AWS_S3_TOOLS
```

---

### 3.3 Triggers Configuration

**File: `backend/configs/triggers.py`**

Trigger definitions organized by integration, following the same pattern as `agent_tools_data.py`.
The `input_schema` defines the subscription configuration for a trigger (UI form + validation); the submitted values are stored in `AgentTrigger.config` and provided to the trigger handler during polling.
Each trigger definition must include a `handler` reference so the TriggerRunner can resolve and execute it.

**All triggers use polling** (no webhooks). Supported polling methods:

| Method                  | Description                          | Cursor Type               | Example Integration |
| ----------------------- | ------------------------------------ | ------------------------- | ------------------- |
| `delta_query`           | API's native delta/sync endpoint     | Delta token string        | Microsoft Graph     |
| `list_objects_v2`       | Pagination with continuation markers | Last object key/timestamp | AWS S3              |
| `history_list`          | Audit log / history traversal        | History ID (integer)      | Gmail               |
| `conversations_history` | Message polling with timestamp       | Message timestamp         | Slack               |

Cursor state is automatically managed in `AgentTrigger.cursor` (JSONB field).

```python
# backend/configs/triggers.py
"""
Triggers Configuration
======================
Trigger definitions organized by integration for easy maintenance.
Each trigger includes:
- slug: Unique identifier
- name: Display name
- description: What the trigger does
- integration_key: Parent integration
- trigger_config: Polling method, intervals, etc.
- input_schema: JSONSchema for user configuration
- handler: module/function or module/class/method for runtime execution

Pattern follows BASIC_AGENT_TOOLS in agent_tools_data.py
"""

from typing import Dict, Any, List


# =============================================================================
# JSONSCHEMA FIELD HELPERS
# =============================================================================

def _str_field(title: str, description: str, default: str = None, enum: List[str] = None) -> Dict:
    """Create a JSONSchema string field."""
    schema = {"type": "string", "title": title, "description": description}
    if default is not None:
        schema["default"] = default
    if enum:
        schema["enum"] = enum
    return schema


def _int_field(title: str, description: str, default: int = None, minimum: int = None, maximum: int = None) -> Dict:
    """Create a JSONSchema integer field."""
    schema = {"type": "integer", "title": title, "description": description}
    if default is not None:
        schema["default"] = default
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _bool_field(title: str, description: str, default: bool = False) -> Dict:
    """Create a JSONSchema boolean field."""
    return {"type": "boolean", "title": title, "description": description, "default": default}


def _array_field(title: str, description: str, items_type: str = "string") -> Dict:
    """Create a JSONSchema array field."""
    return {"type": "array", "title": title, "description": description, "items": {"type": items_type}}


# =============================================================================
# OUTLOOK / MICROSOFT GRAPH TRIGGERS
# =============================================================================

OUTLOOK_TRIGGERS: List[Dict[str, Any]] = [
    {
        "slug": "outlook_new_email",
        "name": "New Email Received",
        "description": "Triggers when a new email arrives in the specified mailbox folder. Uses Microsoft Graph delta queries for efficient incremental sync.",
        "integration_key": "outlook",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.outlook.triggers",
            "class": "OutlookPoller",
            "method": "poll_new_emails",
        },
        "trigger_config": {
            "polling_method": "delta_query",
            "graph_endpoint": "/users/{mailbox_email}/mailFolders/{folder}/messages/delta",
            "default_polling_interval": 300,
            "min_polling_interval": 60,
            "max_polling_interval": 3600,
        },
        "input_schema": {
            "type": "object",
            "title": "Email Trigger Configuration",
            "properties": {
                "mailbox_email": _str_field(
                    "Mailbox Email",
                    "The email address of the mailbox to monitor"
                ),
                "folder": _str_field(
                    "Folder",
                    "The folder to monitor for new emails",
                    default="Inbox",
                    enum=["Inbox", "Drafts", "SentItems", "Archive", "JunkEmail"]
                ),
            },
            "required": ["mailbox_email"],
        },
    },
    {
        "slug": "outlook_email_flagged",
        "name": "Email Flagged",
        "description": "Triggers when an email is flagged for follow-up in the specified mailbox.",
        "integration_key": "outlook",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.outlook.triggers",
            "class": "OutlookPoller",
            "method": "poll_email_flagged",
        },
        "trigger_config": {
            "polling_method": "delta_query",
            "filter": "flag/flagStatus eq 'flagged'",
            "default_polling_interval": 300,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "mailbox_email": _str_field(
                    "Mailbox Email",
                    "The email address of the mailbox to monitor"
                ),
                "flag_status": _str_field(
                    "Flag Status",
                    "The flag status to trigger on",
                    default="flagged",
                    enum=["flagged", "complete", "notFlagged"]
                ),
            },
            "required": ["mailbox_email"],
        },
    },
    {
        "slug": "outlook_calendar_event_created",
        "name": "New Calendar Event",
        "description": "Triggers when a new calendar event is created or received.",
        "integration_key": "outlook",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.outlook.triggers",
            "class": "OutlookPoller",
            "method": "poll_calendar_event_created",
        },
        "trigger_config": {
            "polling_method": "delta_query",
            "graph_endpoint": "/users/{mailbox_email}/calendar/events/delta",
            "default_polling_interval": 600,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "mailbox_email": _str_field(
                    "Mailbox Email",
                    "The email address of the calendar owner"
                ),
                "calendar_id": _str_field(
                    "Calendar ID",
                    "Specific calendar ID (leave empty for default calendar)",
                    default=""
                ),
            },
            "required": ["mailbox_email"],
        },
    },
    {
        "slug": "outlook_email_moved",
        "name": "Email Moved to Folder",
        "description": "Triggers when an email is moved to a specific folder.",
        "integration_key": "outlook",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.outlook.triggers",
            "class": "OutlookPoller",
            "method": "poll_email_moved",
        },
        "trigger_config": {
            "polling_method": "delta_query",
            "default_polling_interval": 300,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "mailbox_email": _str_field(
                    "Mailbox Email",
                    "The email address of the mailbox to monitor"
                ),
                "target_folder": _str_field(
                    "Target Folder",
                    "The folder to watch for incoming emails"
                ),
            },
            "required": ["mailbox_email", "target_folder"],
        },
    },
]


# =============================================================================
# AWS S3 TRIGGERS
# =============================================================================

AWS_S3_TRIGGERS: List[Dict[str, Any]] = [
    {
        "slug": "aws_s3_new_object",
        "name": "New Object Created",
        "description": "Triggers when a new object is created in the specified S3 bucket. Uses list_objects_v2 with marker-based pagination.",
        "integration_key": "aws_s3",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.aws_s3.triggers",
            "class": "S3Poller",
            "method": "poll_new_object",
        },
        "trigger_config": {
            "polling_method": "list_objects_v2",
            "default_polling_interval": 300,
            "min_polling_interval": 60,
            "max_polling_interval": 3600,
        },
        "input_schema": {
            "type": "object",
            "title": "S3 Object Trigger Configuration",
            "properties": {
                "bucket_name": _str_field(
                    "Bucket Name",
                    "The name of the S3 bucket to monitor"
                ),
                "prefix": _str_field(
                    "Key Prefix",
                    "Only monitor objects with keys starting with this prefix",
                    default=""
                ),
                "suffix": _str_field(
                    "File Extension",
                    "Only trigger for objects with this suffix (e.g., .pdf, .json)",
                    default=""
                ),
                "include_metadata": _bool_field(
                    "Include Metadata",
                    "Include object metadata in trigger payload",
                    default=False
                ),
            },
            "required": ["bucket_name"],
        },
    },
    {
        "slug": "aws_s3_object_deleted",
        "name": "Object Deleted",
        "description": "Triggers when an object is deleted from the specified S3 bucket.",
        "integration_key": "aws_s3",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.aws_s3.triggers",
            "class": "S3Poller",
            "method": "poll_object_deleted",
        },
        "trigger_config": {
            "polling_method": "list_objects_v2",
            "track_deletions": True,
            "default_polling_interval": 600,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "bucket_name": _str_field(
                    "Bucket Name",
                    "The name of the S3 bucket to monitor"
                ),
                "prefix": _str_field(
                    "Key Prefix",
                    "Only monitor objects with keys starting with this prefix",
                    default=""
                ),
            },
            "required": ["bucket_name"],
        },
    },
]


# =============================================================================
# SHAREPOINT TRIGGERS
# =============================================================================

SHAREPOINT_TRIGGERS: List[Dict[str, Any]] = [
    {
        "slug": "sharepoint_new_file",
        "name": "New File Added",
        "description": "Triggers when a new file is added to the specified SharePoint document library.",
        "integration_key": "sharepoint",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.sharepoint.triggers",
            "class": "SharePointPoller",
            "method": "poll_new_file",
        },
        "trigger_config": {
            "polling_method": "delta_query",
            "graph_endpoint": "/sites/{site_id}/drives/{drive_id}/root/delta",
            "default_polling_interval": 300,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": _str_field(
                    "Site ID",
                    "The SharePoint site ID (from site URL or Graph API)"
                ),
                "drive_id": _str_field(
                    "Drive ID",
                    "The document library drive ID"
                ),
                "folder_path": _str_field(
                    "Folder Path",
                    "Path to specific folder to monitor (e.g., '/Documents/Invoices')",
                    default="/"
                ),
                "file_extensions": _array_field(
                    "File Extensions",
                    "Only trigger for files with these extensions (e.g., ['pdf', 'docx'])"
                ),
            },
            "required": ["site_id", "drive_id"],
        },
    },
    {
        "slug": "sharepoint_file_modified",
        "name": "File Modified",
        "description": "Triggers when a file is modified in the specified SharePoint library.",
        "integration_key": "sharepoint",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.sharepoint.triggers",
            "class": "SharePointPoller",
            "method": "poll_file_modified",
        },
        "trigger_config": {
            "polling_method": "delta_query",
            "track_modifications": True,
            "default_polling_interval": 600,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "site_id": _str_field("Site ID", "The SharePoint site ID"),
                "drive_id": _str_field("Drive ID", "The document library drive ID"),
                "folder_path": _str_field("Folder Path", "Path to folder to monitor", default="/"),
            },
            "required": ["site_id", "drive_id"],
        },
    },
]


# =============================================================================
# GMAIL TRIGGERS
# =============================================================================

GMAIL_TRIGGERS: List[Dict[str, Any]] = [
    {
        "slug": "gmail_new_email",
        "name": "New Email Received",
        "description": "Triggers when a new email arrives in Gmail. Uses history API for efficient incremental sync.",
        "integration_key": "gmail",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.gmail.triggers",
            "class": "GmailPoller",
            "method": "poll_new_email",
        },
        "trigger_config": {
            "polling_method": "history_list",
            "history_types": ["messageAdded"],
            "default_polling_interval": 300,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "label_ids": _array_field(
                    "Label IDs",
                    "Gmail labels to monitor (e.g., ['INBOX', 'IMPORTANT'])"
                ),
                "query": _str_field(
                    "Search Query",
                    "Gmail search query to filter emails (e.g., 'from:important@company.com')",
                    default=""
                ),
                "include_spam_trash": _bool_field(
                    "Include Spam/Trash",
                    "Include emails in Spam and Trash",
                    default=False
                ),
            },
            "required": [],
        },
    },
    {
        "slug": "gmail_email_labeled",
        "name": "Email Labeled",
        "description": "Triggers when a specific label is added to an email.",
        "integration_key": "gmail",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.gmail.triggers",
            "class": "GmailPoller",
            "method": "poll_email_labeled",
        },
        "trigger_config": {
            "polling_method": "history_list",
            "history_types": ["labelAdded"],
            "default_polling_interval": 300,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "label_id": _str_field(
                    "Label ID",
                    "The label ID to watch for (e.g., 'STARRED', 'IMPORTANT', or custom label ID)"
                ),
            },
            "required": ["label_id"],
        },
    },
]


# =============================================================================
# SLACK TRIGGERS
# =============================================================================

SLACK_TRIGGERS: List[Dict[str, Any]] = [
    {
        "slug": "slack_new_message",
        "name": "New Message in Channel",
        "description": "Triggers when a new message is posted in a specified Slack channel.",
        "integration_key": "slack",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.slack.triggers",
            "class": "SlackPoller",
            "method": "poll_new_message",
        },
        "trigger_config": {
            "polling_method": "conversations_history",
            "default_polling_interval": 60,
            "min_polling_interval": 30,
            "max_polling_interval": 300,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_id": _str_field(
                    "Channel ID",
                    "The Slack channel ID (starts with C for channels, D for DMs)"
                ),
                "ignore_bot_messages": _bool_field(
                    "Ignore Bot Messages",
                    "Skip messages from bots",
                    default=True
                ),
                "ignore_thread_replies": _bool_field(
                    "Ignore Thread Replies",
                    "Only trigger on top-level messages, not thread replies",
                    default=False
                ),
            },
            "required": ["channel_id"],
        },
    },
    {
        "slug": "slack_app_mention",
        "name": "App Mentioned",
        "description": "Triggers when the bot/app is @mentioned in any channel.",
        "integration_key": "slack",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.slack.triggers",
            "class": "SlackPoller",
            "method": "poll_app_mention",
        },
        "trigger_config": {
            "polling_method": "search_messages",
            "query_template": "<@{bot_user_id}>",
            "default_polling_interval": 60,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "include_dms": _bool_field(
                    "Include Direct Messages",
                    "Also trigger on direct messages to the bot",
                    default=True
                ),
            },
            "required": [],
        },
    },
    {
        "slug": "slack_reaction_added",
        "name": "Reaction Added",
        "description": "Triggers when a specific emoji reaction is added to a message.",
        "integration_key": "slack",
        "is_enabled": True,
        "handler": {
            "module": "integrations.providers.slack.triggers",
            "class": "SlackPoller",
            "method": "poll_reaction_added",
        },
        "trigger_config": {
            "polling_method": "reactions_list",
            "default_polling_interval": 120,
        },
        "input_schema": {
            "type": "object",
            "properties": {
                "channel_id": _str_field(
                    "Channel ID",
                    "The Slack channel ID to monitor"
                ),
                "reaction_name": _str_field(
                    "Reaction Name",
                    "The emoji name to watch for (without colons, e.g., 'thumbsup')",
                    default=""
                ),
            },
            "required": ["channel_id"],
        },
    },
]


# =============================================================================
# COMBINED TRIGGERS LIST
# =============================================================================

ALL_TRIGGERS: List[Dict[str, Any]] = (
    OUTLOOK_TRIGGERS +
    AWS_S3_TRIGGERS +
    SHAREPOINT_TRIGGERS +
    GMAIL_TRIGGERS +
    SLACK_TRIGGERS
)

TRIGGERS_BY_INTEGRATION: Dict[str, List[Dict[str, Any]]] = {
    "outlook": OUTLOOK_TRIGGERS,
    "aws_s3": AWS_S3_TRIGGERS,
    "sharepoint": SHAREPOINT_TRIGGERS,
    "gmail": GMAIL_TRIGGERS,
    "slack": SLACK_TRIGGERS,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_triggers_for_integration(integration_key: str) -> List[Dict[str, Any]]:
    """Get all triggers for a specific integration."""
    return TRIGGERS_BY_INTEGRATION.get(integration_key, [])


def get_trigger_by_slug(slug: str) -> Dict[str, Any]:
    """Get a trigger definition by its slug."""
    for trigger in ALL_TRIGGERS:
        if trigger["slug"] == slug:
            return trigger
    return None


def get_enabled_triggers() -> List[Dict[str, Any]]:
    """Get all enabled triggers."""
    return [t for t in ALL_TRIGGERS if t.get("is_enabled", False)]


def get_trigger_input_schema(slug: str) -> Dict[str, Any]:
    """Get the input schema for a trigger."""
    trigger = get_trigger_by_slug(slug)
    return trigger.get("input_schema", {}) if trigger else {}
```

---

### 3.4 Integrations Configuration

**File: `backend/configs/integrations.py`**

Integrations reference an array of supported auth schemas.

```python
# backend/configs/integrations.py
"""
Integrations Configuration
==========================
Integration definitions with support for multiple auth schemas per integration.

Key fields:
- key: Unique identifier
- name: Display name
- supported_auth_schemas: Array of auth schema keys from auth_schemas.py
- integration_config: Metadata (supports_triggers, supports_actions, etc.)
"""

from typing import Dict, Any, List


INTEGRATIONS: List[Dict[str, Any]] = [
    # =========================================================================
    # MICROSOFT 365 / OFFICE 365
    # =========================================================================
    {
        "key": "outlook",
        "name": "Outlook",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/outlook.svg",
        "tags": ["email", "calendar", "productivity"],
        "description": "Microsoft Outlook integration for email management, calendar sync, and task automation through Microsoft Graph API.",
        "supported_auth_schemas": [
            "microsoft_graph_client_credentials",  # App-only (recommended for mailbox polling)
            "microsoft_graph_delegated",           # User context (for personal mailbox)
        ],
        "integration_config": {
            "integration_type": "tool",
            "supports_triggers": True,
            "supports_actions": True,
            "default_auth_schema": "microsoft_graph_client_credentials",
            # UI displays auth schema selection with recommendations:
            "auth_recommendations": {
                "microsoft_graph_client_credentials": "Recommended for background automation, shared mailboxes, triggers",
                "microsoft_graph_delegated": "For personal mailbox access with user consent",
            },
        },
        "docs_url": "https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview",
        "service_types": ["email", "calendar"],
    },
    {
        "key": "sharepoint",
        "name": "SharePoint",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/sharepoint.svg",
        "tags": ["file_management", "data_storage", "collaboration"],
        "description": "SharePoint document management for file sync, library monitoring, and content collaboration.",
        "supported_auth_schemas": ["microsoft_graph_client_credentials"],
        "integration_config": {
            "integration_type": "tool",
            "supports_triggers": True,
            "supports_actions": True,
        },
        "service_types": ["files", "storage"],
    },

    # =========================================================================
    # GOOGLE WORKSPACE
    # =========================================================================
    {
        "key": "gmail",
        "name": "Gmail",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/gmail.svg",
        "tags": ["email"],
        "description": "Gmail integration for email automation, inbox monitoring, and message management.",
        "supported_auth_schemas": [
            "gmail_oauth",              # User delegated (device flow supported)
            "google_service_account",   # Service account with domain-wide delegation
        ],
        "integration_config": {
            "integration_type": "tool",
            "supports_triggers": True,
            "supports_actions": True,
            "supports_device_flow": True,
        },
        "service_types": ["email"],
    },

    # =========================================================================
    # LLM PROVIDERS
    # =========================================================================
    {
        "key": "openai",
        "name": "OpenAI",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/openai.svg",
        "tags": ["language_model", "ai"],
        "description": "OpenAI API integration for GPT models, embeddings, and AI capabilities.",
        "supported_auth_schemas": ["openai_auth"],
        "integration_config": {
            "integration_type": "agent_llm",
            "supports_triggers": False,
            "supports_actions": True,
        },
        "service_types": ["llm"],
    },
    {
        "key": "anthropic",
        "name": "Anthropic",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/anthropic.svg",
        "tags": ["language_model", "ai"],
        "description": "Anthropic Claude models for natural language processing and AI reasoning.",
        "supported_auth_schemas": ["anthropic_auth"],
        "integration_config": {
            "integration_type": "agent_llm",
            "supports_triggers": False,
            "supports_actions": True,
        },
        "service_types": ["llm"],
    },
    {
        "key": "gemini",
        "name": "Google Gemini",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/gemini.svg",
        "tags": ["language_model", "ai"],
        "description": "Google Gemini models for multimodal AI capabilities.",
        "supported_auth_schemas": ["gemini_auth"],
        "integration_config": {
            "integration_type": "agent_llm",
            "supports_triggers": False,
            "supports_actions": True,
        },
        "service_types": ["llm"],
    },
    {
        "key": "azure_openai",
        "name": "Azure OpenAI",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/azure.svg",
        "tags": ["language_model", "ai", "enterprise"],
        "description": "Azure-hosted OpenAI models with enterprise security and compliance.",
        "supported_auth_schemas": ["azure_openai_auth"],
        "integration_config": {
            "integration_type": "agent_llm",
            "supports_triggers": False,
            "supports_actions": True,
        },
        "service_types": ["llm"],
    },

    # =========================================================================
    # CLOUD STORAGE
    # =========================================================================
    {
        "key": "aws_s3",
        "name": "AWS S3",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/s3_bucket.svg",
        "tags": ["cloud_storage", "data_storage"],
        "description": "Amazon S3 object storage for file uploads, downloads, and bucket monitoring.",
        "supported_auth_schemas": ["aws_s3_auth"],
        "integration_config": {
            "integration_type": "tool",
            "supports_triggers": True,
            "supports_actions": True,
        },
        "service_types": ["storage"],
    },

    # =========================================================================
    # COLLABORATION
    # =========================================================================
    {
        "key": "slack",
        "name": "Slack",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/slack.svg",
        "tags": ["messaging", "collaboration"],
        "description": "Slack messaging integration for channel monitoring, notifications, and bot interactions.",
        "supported_auth_schemas": [
            "slack_oauth",      # Full OAuth flow
            "slack_bot_token",  # Direct bot token (simpler)
        ],
        "integration_config": {
            "integration_type": "tool",
            "supports_triggers": True,
            "supports_actions": True,
            "default_auth_schema": "slack_bot_token",
        },
        "service_types": ["messaging"],
    },

    # =========================================================================
    # CUSTOM API
    # =========================================================================
    {
        "key": "custom_api",
        "name": "Custom API",
        "logo_url": "https://assistcx-public.s3.ap-south-1.amazonaws.com/logos/api.svg",
        "tags": ["api", "custom"],
        "description": "Connect to any REST API with configurable authentication.",
        "supported_auth_schemas": [
            "api_key_header",
            "api_key_query",
            "bearer_auth",
            "basic_auth",
        ],
        "integration_config": {
            "integration_type": "tool",
            "is_custom": True,
            "supports_triggers": False,
            "supports_actions": True,
        },
        "service_types": ["api"],
    },
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_integration_by_key(key: str) -> Dict[str, Any]:
    """Get integration definition by key."""
    for integration in INTEGRATIONS:
        if integration["key"] == key:
            return integration
    return None


def get_integrations_by_tag(tag: str) -> List[Dict[str, Any]]:
    """Get all integrations with a specific tag."""
    return [i for i in INTEGRATIONS if tag in i.get("tags", [])]


def get_integrations_by_service_type(service_type: str) -> List[Dict[str, Any]]:
    """Get all integrations for a specific service type."""
    return [i for i in INTEGRATIONS if service_type in i.get("service_types", [])]


def get_integrations_with_triggers() -> List[Dict[str, Any]]:
    """Get all integrations that support triggers."""
    return [
        i for i in INTEGRATIONS
        if i.get("integration_config", {}).get("supports_triggers", False)
    ]


def get_llm_integrations() -> List[Dict[str, Any]]:
    """Get all LLM provider integrations."""
    return [
        i for i in INTEGRATIONS
        if i.get("integration_config", {}).get("integration_type") == "agent_llm"
    ]
```

---

## 4. Database Schema

**Note:** Auth schemas are **static config** (`configs/auth_schemas.py`) and are **not persisted** as a DB table. Only the schema key is stored on `connections`.

### 4.1 Integration Model (Updated)

**File: `backend/models/integration.py`**

The existing Integration model with new columns for multi-auth support.

```python
# backend/models/integration.py
"""
Integration Model - External service integration catalog.

This is a definition/catalog table seeded from configs/integrations.py.
Users don't create integrations directly; they create Connections to integrations.

Changes from Previous Version:
- Removed: auth_type, auth_schema, credentials (single auth approach)
- Added: supported_auth_schemas (array for multi-auth support)
- Added: docs_url, is_custom, openapi_spec (for custom integrations)
"""

from sqlalchemy import Column, String, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
import uuid

from backend.models.base import Base


class IntegrationCatalog(Base):
    __tablename__ = "integration_catalogs"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    key = Column(String(64), unique=True, index=True, nullable=False)  # Unique key e.g., 'outlook', 'gmail', 'aws_s3'
    name = Column(String(128), nullable=False)  # Display name e.g., 'Microsoft Outlook'
    description = Column(Text, nullable=True)  # Detailed description of capabilities
    logo_url = Column(String(512), nullable=True)  # URL to integration logo for UI
    docs_url = Column(String(512), nullable=True)  # Link to official API documentation

    # Authentication - NEW: Array of supported auth schema keys from AUTH_SCHEMAS
    # Example: ['microsoft_graph_client_credentials', 'microsoft_graph_delegated']
    supported_auth_schemas = Column(ARRAY(String), nullable=False, default=[])

    # Metadata
    tags = Column(ARRAY(String), default=[])  # Categorization e.g., ['email', 'calendar']
    service_types = Column(ARRAY(String), default=[])  # Service types e.g., ['email'], ['llm']
    # Contains: integration_type, supports_triggers, supports_actions, default_auth_schema
    integration_config = Column(JSONB, default=dict)

    # Custom Integration Support
    is_custom = Column(Boolean, default=False)  # True for user-uploaded OpenAPI integrations
    openapi_spec = Column(JSONB, nullable=True)  # Full OpenAPI spec for custom integrations

    # Status
    is_active = Column(Boolean, default=True)  # Whether available for use

    # Relationships
    connections = relationship("Connection", back_populates="integration_catalog", cascade="all, delete-orphan")
    triggers = relationship("Trigger", back_populates="integration_catalog", cascade="all, delete-orphan")
    tools = relationship("Tool", back_populates="integration_catalog", cascade="all, delete-orphan")
```

---

### 4.2 Connection Model (New)

**File: `backend/models/connection.py`**

Stores a user's authenticated connection to an integration with encrypted credentials.

```python
# backend/models/connection.py
"""
Connection Model - User's authenticated connection to an integration.

Key Concepts:
- A Connection is an instance of an Integration with user-provided credentials
- One Integration can have multiple Connections (e.g., multiple AWS accounts)
- Credentials are encrypted using Fernet symmetric encryption
- auth_schema_key determines which auth schema from AUTH_SCHEMAS this connection uses
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from backend.models.base import Base


class Connection(Base):
    __tablename__ = "connections"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign Keys
    integration_id = Column(UUID(as_uuid=True), ForeignKey("integration_catalogs.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Connection Identity
    name = Column(String(128), nullable=False)  # Display name e.g., 'Finance Team AWS'
    auth_schema_key = Column(String(64), nullable=False, index=True)  # Key from AUTH_SCHEMAS e.g., 'microsoft_graph_client_credentials'

    # Credentials (Encrypted with Fernet)
    encrypted_credentials = Column(Text, nullable=False)  # User-provided creds: {'client_id': '...', 'client_secret': '...'}
    encrypted_token = Column(Text, nullable=True)  # Encrypted OAuth tokens: {'access_token': '...', 'refresh_token': '...', 'expires_at': ...}

    # Non-Sensitive Config e.g., {'region': 'us-east-1', 'default_bucket': 'my-bucket'}
    connection_config = Column(JSONB, default=dict)

    # Status
    is_active = Column(Boolean, default=True)  # User-controlled enable/disable
    is_valid = Column(Boolean, default=True)  # System-set on auth failure, triggers re-auth prompt
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Soft delete timestamp

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)  # Last action or trigger poll

    # Relationships
    integration_catalog = relationship("IntegrationCatalog", back_populates="connections")
    created_by_user = relationship("User", foreign_keys=[created_by])
    agent_triggers = relationship("AgentTrigger", back_populates="connection", cascade="all, delete-orphan")
```

**Soft Delete Usage**:

Connections support soft delete to prevent accidental data loss:

```python
# Soft delete a connection
def delete_connection(connection_id: str, db: Session):
    connection = db.query(Connection).get(connection_id)

    # Check for active triggers before deletion
    active_triggers = db.query(AgentTrigger).filter(
        AgentTrigger.connection_id == connection_id,
        AgentTrigger.is_enabled == True
    ).count()

    pending_events = db.query(TriggerInbox).join(AgentTrigger).filter(
        AgentTrigger.connection_id == connection_id,
        TriggerInbox.status == "pending"
    ).count()

    # Warn user if deletion would cause data loss
    if active_triggers > 0 or pending_events > 0:
        logger.warning(f"Deleting connection with {active_triggers} active triggers and {pending_events} pending events")

    # Soft delete
    connection.deleted_at = datetime.utcnow()
    connection.is_active = False
    db.commit()

# Query only active (non-deleted) connections
active_connections = db.query(Connection).filter(
    Connection.deleted_at == None,
    Connection.is_active == True
).all()

# Permanently delete old soft-deleted connections (cleanup job)
def cleanup_old_deleted_connections(db: Session, days: int = 30):
    cutoff = datetime.utcnow() - timedelta(days=days)
    old_deleted = db.query(Connection).filter(
        Connection.deleted_at < cutoff
    ).all()

    for conn in old_deleted:
        db.delete(conn)  # Hard delete after grace period
    db.commit()
```

**Data Loss on Connection Deletion**:

When a connection is deleted (soft or hard), the following cascade effects occur:

| Model            | Cascade Behavior                   | Data Loss                                                                                                      | Mitigation                               |
| ---------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| **AgentTrigger** | `CASCADE` - deleted                | ❌ Polling cursor state lost (can't resume from last position)<br>❌ Error history lost<br>❌ User config lost | Soft delete gives 30-day recovery window |
| **TriggerInbox** | `CASCADE` (via AgentTrigger)       | ❌ Pending events lost (never processed)<br>❌ Historical events lost                                          | Check for pending events before delete   |
| **AgentTool**    | `SET NULL` - connection_id cleared | ⚠️ Tools become unpinned, require runtime context                                                              | Can be re-pinned to new connection       |

**Pre-Delete Safety Check** (recommended):

```python
def get_connection_deletion_impact(connection_id: str, db: Session) -> dict:
    """Get impact summary before deleting a connection."""

    active_triggers = db.query(AgentTrigger).filter(
        AgentTrigger.connection_id == connection_id,
        AgentTrigger.is_enabled == True
    ).count()

    total_triggers = db.query(AgentTrigger).filter(
        AgentTrigger.connection_id == connection_id
    ).count()

    pending_events = db.query(TriggerInbox).join(AgentTrigger).filter(
        AgentTrigger.connection_id == connection_id,
        TriggerInbox.status.in_(["pending", "processing"])
    ).count()

    pinned_tools = db.query(AgentTool).filter(
        AgentTool.connection_id == connection_id
    ).count()

    return {
        "can_delete_safely": active_triggers == 0 and pending_events == 0,
        "warnings": {
            "active_triggers": active_triggers,
            "total_triggers": total_triggers,
            "pending_events": pending_events,
            "pinned_tools": pinned_tools,
        },
        "message": f"This will delete {total_triggers} trigger(s), lose {pending_events} pending event(s), and unpin {pinned_tools} tool(s)."
    }
```

**Recommendation**: Always run impact check and show confirmation dialog in UI before allowing connection deletion.

---

### 4.3 Trigger Model (New)

**File: `backend/models/trigger.py`**

Defines available triggers for an integration (seeded from configs/triggers.py).

```python
# backend/models/trigger.py
"""
Trigger Model - Trigger definition at integration level.

Key Concepts:
- Triggers are catalog entries seeded from configs/triggers.py
- Each trigger belongs to one Integration
- Users create AgentTriggers that reference these definitions
- input_schema defines what users configure when setting up the trigger
- trigger_config contains system settings (polling method, intervals, endpoints)
- handler defines the runtime callable (module/function or module/class/method)
"""

from sqlalchemy import Column, String, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from backend.models.base import Base


class Trigger(Base):
    __tablename__ = "triggers"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    slug = Column(String(64), unique=True, index=True, nullable=False)  # Unique identifier e.g., 'outlook_new_email' (kept for config seeding)

    # Foreign Key
    integration_id = Column(UUID(as_uuid=True), ForeignKey("integration_catalogs.id", ondelete="CASCADE"), nullable=False, index=True)

    # Trigger Identity
    name = Column(String(128), nullable=False)  # Display name e.g., 'New Email Received'
    description = Column(Text, nullable=True)  # What this trigger does

    # Configuration Schemas
    # JSONSchema for user-configurable options, rendered as form in UI
    # Example: {'type': 'object', 'properties': {'mailbox_email': {...}}, 'required': ['mailbox_email']}
    input_schema = Column(JSONB, default=dict)
    # System config: polling_method, graph_endpoint, default_polling_interval, webhook_based, etc.
    trigger_config = Column(JSONB, default=dict)
    # Handler reference: module/function or module/class/method
    handler = Column(JSONB, default=dict)

    # Status
    is_enabled = Column(Boolean, default=True)  # Can be disabled without removal

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    integration_catalog = relationship("IntegrationCatalog", back_populates="triggers")
    agent_triggers = relationship("AgentTrigger", back_populates="trigger", cascade="all, delete-orphan")
```

---

### 4.4 AgentTrigger Model (New)

**File: `backend/models/agent_trigger.py`**

Binds an agent to a specific trigger + connection combination, with integrated polling state.

```python
# backend/models/agent_trigger.py
"""
AgentTrigger Model - Binding between Agent, Connection, and Trigger with integrated polling state.

Key Concepts:
- Combines: Agent (receives events) + Connection (credentials) + Trigger (what to poll)
- config contains user values matching Trigger's input_schema
- Polling state (cursor, next_run_at, locks, errors) stored directly in this table
- Unique constraint prevents duplicate trigger bindings per agent+connection

Example Setup:
- Agent: "Email Processor Bot"
- Connection: "Company Outlook" (MS Graph credentials)
- Trigger: "outlook_new_email"
- Config: {"mailbox_email": "support@company.com", "folder": "Inbox"}
"""

from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from backend.models.base import Base


class AgentTrigger(Base):
    __tablename__ = "agent_triggers"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign Keys
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_id = Column(UUID(as_uuid=True), ForeignKey("triggers.id", ondelete="CASCADE"), nullable=False, index=True)

    # User Configuration - values matching trigger.input_schema
    # Example: {'mailbox_email': 'inbox@company.com', 'folder': 'Inbox', 'filter_sender': '*@important.com'}
    config = Column(JSONB, default=dict)

    # Status
    is_enabled = Column(Boolean, default=True)  # User can pause without deleting

    # Polling State (merged from TriggerState)
    cursor = Column(JSONB, nullable=True)  # Delta token, last object key, history ID, etc.
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)  # When to poll next
    locked_until = Column(DateTime(timezone=True), nullable=True)  # Concurrency lock
    backoff_until = Column(DateTime(timezone=True), nullable=True)  # Exponential backoff

    # Error Tracking
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    last_polled_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Constraints and Indexes
    __table_args__ = (
        # Prevent duplicate: same agent + connection + trigger
        UniqueConstraint("agent_id", "connection_id", "trigger_id", name="uq_agent_connection_trigger"),
        # Composite index for polling scheduler query
        Index("idx_polling_query", "is_enabled", "next_run_at", "locked_until"),
    )

    # Relationships
    agent = relationship("Agent", back_populates="agent_triggers")
    connection = relationship("Connection", back_populates="agent_triggers")
    trigger = relationship("Trigger", back_populates="agent_triggers")
```

---

### 4.5 Tool Model (New)

**File: `backend/models/tool.py`**

Seeded catalog of actions/tools. Stored in DB for UI, permissions, and lookups.

```python
# backend/models/tool.py
from sqlalchemy import Column, String, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from backend.models.base import Base


class Tool(Base):
    __tablename__ = "tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    integration_id = Column(UUID(as_uuid=True), ForeignKey("integration_catalogs.id", ondelete="CASCADE"), nullable=False, index=True)

    slug = Column(String(64), unique=True, index=True, nullable=False)  # Unique identifier e.g., 'outlook_send_email' (for config seeding)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    input_schema = Column(JSONB, default=dict)
    output_schema = Column(JSONB, default=dict)
    handler = Column(JSONB, default=dict)  # module/class/method

    tool_config = Column(JSONB, default=dict)

    is_default = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    integration_catalog = relationship("IntegrationCatalog", back_populates="tools")
```

---

### 4.6 AgentTool Model (New)

**File: `backend/models/agent_tool.py`**

Binds an agent to a tool and optionally pins a connection and defaults.

```python
# backend/models/agent_tool.py
from sqlalchemy import Column, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from backend.models.base import Base


class AgentToolBinding(Base):
    __tablename__ = "agent_tool_bindings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    tool_id = Column(UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("connections.id", ondelete="SET NULL"), nullable=True, index=True)

    config = Column(JSONB, default=dict)  # Per-agent configuration overrides
    is_enabled = Column(Boolean, default=True)  # Allow disabling tools per agent

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Constraints
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )

    agent = relationship("Agent", back_populates="agent_tool_bindings")
    tool = relationship("Tool")
    connection = relationship("Connection")
```

---

### 4.7 TriggerInbox Model (New)

**File: `backend/models/trigger_inbox.py`**

Durable inbox for normalized trigger events and retry handling.

```python
# backend/models/trigger_inbox.py
"""
TriggerInbox Model - Durable event queue for trigger events.

Key Concepts:
- Events are written here by TriggerRunner after polling
- Each event is self-contained with payload + metadata
- metadata field stores connection context for tool execution
- Deduplication via unique dedupe_key prevents duplicate processing
- Status tracking enables retry logic and monitoring

Metadata Field Example:
{
    "connection_id": "abc-123-uuid",
    "connection_name": "Company Outlook Production",
    "integration_key": "outlook",
    "trigger_slug": "outlook_new_email",
    "trigger_name": "New Email Received"
}
"""

from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from backend.models.base import Base


class TriggerInbox(Base):
    __tablename__ = "trigger_inbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_trigger_id = Column(UUID(as_uuid=True), ForeignKey("agent_triggers.id", ondelete="CASCADE"), nullable=False, index=True)

    event_type = Column(String(128), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=True)
    dedupe_key = Column(String(256), nullable=False, index=True)

    payload = Column(JSONB, default=dict)  # Normalized event data (actual event content)
    metadata = Column(JSONB, default=dict)  # Event metadata (connection_id, integration_key, trigger_name, etc.)

    status = Column(String(32), default="pending", index=True)  # pending/processing/done/failed
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        # Composite index for inbox processing query (status + created_at)
        Index("idx_inbox_processing", "status", "created_at"),
        # Unique index to prevent duplicate events
        Index("idx_dedupe_key", "dedupe_key", unique=True),
    )
```

---

## 5. Backend Architecture

### 5.1 Simplified Folder Structure

**Analysis of Current Project**: Your project already has well-established patterns:

- `configs/` for configuration files
- `models/` for SQLAlchemy models
- `schemas/` for Pydantic schemas
- `routes/` for API endpoints
- `workers/` for Celery tasks
- `utils/` for shared utilities
- `integrations/` with existing provider folders

**Simplified Approach**: Build on existing structure instead of creating parallel hierarchies.

```
backend/
│
├── configs/                            # ✅ EXISTING - Add new config files here
│   ├── auth_schemas.py                 # NEW: Auth schema definitions
│   ├── tools.py                        # NEW: Tool definitions by integration
│   ├── triggers.py                     # NEW: Trigger definitions by integration
│   └── integrations.py                 # ✅ EXISTS - Expand with new integrations
│
├── models/                             # ✅ EXISTING - Add new models here
│   ├── integration.py                  # ✅ EXISTS - Update schema
│   ├── connection.py                   # NEW: Connection model
│   ├── tool.py                         # NEW: Tool model
│   ├── trigger.py                      # NEW: Trigger model
│   ├── agent_tool.py                   # ✅ EXISTS - Update schema
│   ├── agent_trigger.py                # NEW: AgentTrigger model
│   └── trigger_inbox.py                # NEW: TriggerInbox model
│
├── schemas/                            # ✅ EXISTING - Add new Pydantic schemas
│   ├── connection_schema.py            # NEW: Connection API schemas
│   ├── trigger_schema.py               # NEW: Trigger API schemas
│   └── tool_schema.py                  # NEW: Tool API schemas
│
├── routes/                             # ✅ EXISTING - Add new routes
│   ├── integration_routes.py           # ✅ EXISTS - Expand
│   ├── connection_routes.py            # NEW: Connection CRUD
│   └── trigger_routes.py               # NEW: Trigger management
│
├── integrations/                       # ✅ EXISTS - Restructure existing providers
│   ├── __init__.py
│   │
│   ├── auth/                           # NEW: Reusable auth handlers
│   │   ├── __init__.py                 # Exports get_auth_handler()
│   │   ├── oauth2_app.py               # OAuth2 client credentials
│   │   ├── oauth2_user.py              # OAuth2 authorization code
│   │   ├── api_key.py                  # API key auth
│   │   └── aws_sigv4.py                # AWS signature
│   │
│   ├── office_365/                     # ✅ EXISTS - Restructure
│   │   ├── actions.py                  # Tool handlers (send_email, etc.)
│   │   ├── triggers.py                 # Trigger handlers (delta query)
│   │   └── client.py                   # Graph API client
│   │
│   ├── aws/                            # ✅ EXISTS - Restructure
│   │   ├── actions.py                  # S3 operations
│   │   ├── triggers.py                 # S3 bucket polling
│   │   └── client.py                   # Boto3 wrapper
│   │
│   ├── gmail/                          # NEW
│   │   ├── actions.py
│   │   ├── triggers.py
│   │   └── client.py
│   │
│   ├── slack/                          # NEW
│   │   ├── actions.py
│   │   ├── triggers.py
│   │   └── client.py
│   │
│   ├── handler_loader.py               # NEW: Dynamic handler loading
│   ├── executor.py                     # NEW: Tool execution engine
│   ├── trigger_runner.py               # NEW: Trigger polling engine
│   ├── inbox_processor.py              # NEW: Process TriggerInbox
│   ├── seed_loader.py                  # NEW: Seed configs to DB
│   └── encryption.py                   # NEW: Credential encryption
│
├── workers/                            # ✅ EXISTING - Add integration tasks
│   ├── integration_worker.py           # NEW: Trigger polling tasks
│   └── (existing workers)
│
└── utils/                              # ✅ EXISTING - Add integration utilities
    ├── integration_utils.py            # ✅ EXISTS - Expand
    └── (existing utilities)
```

---

### 5.2 Provider Module Structure

Each provider has **3-4 files** depending on complexity.

#### **Standard Structure**

```
integrations/outlook/
├── actions.py    # Tool/action handlers + inline helper functions
├── triggers.py   # Trigger handlers + inline event normalization
├── client.py     # HTTP client + inline constants
└── constants.py  # Optional: Extract only if >20 constants
```

**Naming Convention**:

- **Config file**: `configs/tools.py` (catalog of all tools)
- **Provider file**: `integrations/{provider}/actions.py` (implementation)
- "Tools" = catalog, "Actions" = implementation

**File Responsibilities**:

| File             | Contains         | Inline Helpers              |
| ---------------- | ---------------- | --------------------------- |
| **actions.py**   | Tool handlers    | Data transformation helpers |
| **triggers.py**  | Trigger handlers | Event normalization helpers |
| **client.py**    | HTTP client      | Constants (endpoints, URLs) |
| **constants.py** | Many constants   | Only if >20 items           |

**Key Pattern: Inline Helpers**

✅ Keep helper functions in the same file where used
✅ Small, focused helpers (5-30 lines)
✅ Clear names (`_build_email_payload`, `_format_response`)
❌ No separate mapper/schema files for most cases

**Why inline helpers?**

- Less file navigation
- Related code stays together
- Easier to understand
- Simpler refactoring
- Good enough for 95% of integrations

---

#### **Detailed Code Patterns**

**1. Client Module (`client.py`)**

Handles HTTP communication, authentication, retries, and rate limiting.

```python
# integrations/outlook/client.py
"""Microsoft Graph API HTTP client for Outlook integration."""

import httpx
from typing import Dict, Any, Optional
from backend.models import Connection
from backend.integrations.auth import get_auth_handler
from backend.utils.crypto_utils import decrypt_credentials


# Constants (inline or import from constants.py)
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_ENDPOINTS = {
    "messages": "/me/messages",
    "send_mail": "/me/sendMail",
    "delta": "/me/messages/delta",
}


class GraphClient:
    """
    HTTP client for Microsoft Graph API.

    Handles:
    - Authentication via auth handlers
    - Request/response formatting
    - Error handling and retries
    - Rate limiting
    """

    def __init__(self, connection: Connection):
        self.connection = connection
        self.base_url = GRAPH_BASE_URL

        # Decrypt credentials
        credentials = decrypt_credentials(connection.encrypted_token)

        # Get auth handler from configs
        from backend.configs.auth_schemas import AUTH_SCHEMAS
        auth_schema = AUTH_SCHEMAS[connection.auth_schema_key]

        self.auth_handler = get_auth_handler(
            auth_schema=auth_schema,
            credentials=credentials,
            token_data=credentials.get("token_data")  # For OAuth refresh
        )

    async def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make authenticated Graph API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., "/me/messages")
            data: Request body (for POST/PATCH)
            params: Query parameters

        Returns:
            Response JSON

        Raises:
            HTTPError: On API errors
        """
        # Get auth headers
        headers = await self.auth_handler.get_auth_headers()
        headers["Content-Type"] = "application/json"

        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise RateLimitError(f"Rate limited, retry after {retry_after}s")

            response.raise_for_status()
            return response.json()

    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """GET request."""
        return await self.request("GET", endpoint, params=params)

    async def post(self, endpoint: str, data: Dict) -> Dict:
        """POST request."""
        return await self.request("POST", endpoint, data=data)

    async def patch(self, endpoint: str, data: Dict) -> Dict:
        """PATCH request."""
        return await self.request("PATCH", endpoint, data=data)
```

---

**2. Actions Module (`actions.py`)**

Tool handlers for agent actions. Includes inline helper functions for data transformation.

```python
# integrations/outlook/actions.py
"""Action handlers for Outlook integration via Microsoft Graph."""

from typing import Dict, Any
from sqlalchemy.orm import Session
from backend.models import Connection
from backend.integrations.outlook.client import GraphClient, GRAPH_ENDPOINTS


class OutlookActions:
    """
    Tool handlers for Outlook integration.

    Each method is a tool handler that:
    - Receives validated inputs from JSONSchema
    - Gets connection from tool_runtime
    - Makes API calls via GraphClient
    - Returns structured output
    """

    def __init__(self, db: Session):
        self.db = db

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = None,
        attachments: list = None,
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send email via Outlook.

        Handler for: outlook_send_email tool

        Args:
            to: Recipient email(s) (comma-separated)
            subject: Email subject
            body: Email body (HTML or plain text)
            cc: CC recipients (optional)
            attachments: List of attachment objects (optional)
            tool_runtime: Runtime context (connection_id, agent_id, task_id)

        Returns:
            {
                "success": true,
                "message_id": "AAMk...",
                "sent_at": "2024-01-15T10:30:00Z"
            }
        """
        # Get connection
        connection_id = tool_runtime.get("connection_id")
        if not connection_id:
            raise ValueError("connection_id required in tool_runtime")

        connection = self.db.query(Connection).get(connection_id)
        if not connection:
            raise ValueError(f"Connection {connection_id} not found")

        # Create Graph client
        client = GraphClient(connection)

        # Map input to Graph API format
        payload = self._map_send_email_request(to, subject, body, cc, attachments)

        # Send via API
        response = await client.post(GRAPH_ENDPOINTS["send_mail"], payload)

        # Map response to output schema
        return self._map_send_email_response(response)

    def move_message(
        self,
        message_id: str,
        destination_folder: str,
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Move email to different folder.

        Handler for: outlook_move_message tool
        """
        connection = self._get_connection(tool_runtime)
        client = GraphClient(connection)

        endpoint = f"/me/messages/{message_id}/move"
        payload = {"destinationId": destination_folder}

        response = await client.post(endpoint, payload)

        return {
            "success": True,
            "message_id": response["id"],
            "new_folder": destination_folder
        }

    # === Helper Functions (Data Transformation - inline pattern) ===

    def _get_connection(self, tool_runtime: Dict) -> Connection:
        """
        Helper: Get connection from runtime context.

        Pattern: Simple helper functions for common operations stay in same file.
        """
        connection_id = tool_runtime.get("connection_id")
        if not connection_id:
            raise ValueError("connection_id required")
        return self.db.query(Connection).get(connection_id)

    def _build_email_payload(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = None,
        attachments: list = None
    ) -> Dict:
        """
        Helper: Transform tool inputs to Graph API sendMail format.

        Pattern: Keep transformation logic close to where it's used.
        This is simpler than separate mapper files for most cases.
        """
        # Parse comma-separated recipients
        to_recipients = [
            {"emailAddress": {"address": addr.strip()}}
            for addr in to.split(",") if addr.strip()
        ]

        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML" if "<" in body else "Text",
                    "content": body
                },
                "toRecipients": to_recipients
            }
        }

        # Optional CC recipients
        if cc:
            payload["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr.strip()}}
                for addr in cc.split(",") if addr.strip()
            ]

        # Optional attachments
        if attachments:
            payload["message"]["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": att["name"],
                    "contentBytes": att["content_base64"]
                }
                for att in attachments
            ]

        return payload

    def _format_response(self, api_response: Dict) -> Dict:
        """
        Helper: Format Graph API response to match tool output schema.

        Pattern: Small transformation functions as helpers, not separate files.
        """
        return {
            "success": True,
            "message_id": api_response.get("id", "sent"),
            "sent_at": api_response.get("sentDateTime")
        }
```

**Why inline helpers over separate mapper files?**

✅ **Simpler**: Related code stays together, easier to understand
✅ **Less navigation**: Don't need to jump between files
✅ **Clear intent**: Function names document what they do
✅ **Easier refactoring**: Change handler and helpers together
✅ **Good enough**: Most APIs don't need complex mapping

**When NOT to use inline**: If a helper function exceeds ~30 lines or is reused across multiple handlers, consider extracting it. But this is rare.

---

**3. Triggers Module (`triggers.py`)**

Trigger handlers for polling external APIs. Includes cursor management and event normalization.

```python
# integrations/outlook/triggers.py
"""Trigger handlers for Outlook integration."""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.models import Connection
from backend.integrations.outlook.client import GraphClient, GRAPH_ENDPOINTS


class OutlookTriggers:
    """
    Trigger handlers for Outlook polling.

    Each method is a trigger handler that:
    - Accepts cursor (last poll state)
    - Accepts config (user configuration)
    - Polls external API for new events
    - Returns normalized events + new cursor
    """

    def __init__(self, db: Session):
        self.db = db

    def poll_new_emails(
        self,
        cursor: str,
        config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Poll for new emails using Microsoft Graph delta query.

        Handler for: outlook_new_email trigger

        Args:
            cursor: Delta link from last poll (or None for first poll)
            config: User configuration (e.g., folder filter, sender filter)
            context: Runtime context (agent_trigger_id, connection, etc.)

        Returns:
            {
                "events": [
                    {
                        "event_id": "msg-123",
                        "event_type": "email_received",
                        "occurred_at": "2024-01-15T10:00:00Z",
                        "data": {
                            "subject": "...",
                            "from": "...",
                            "body_preview": "..."
                        }
                    }
                ],
                "cursor": "@odata.deltaLink=...",
                "has_more": false,
                "polling_interval": 300
            }
        """
        # Get connection from context
        connection = context.get("connection")
        if not connection:
            connection_id = context.get("connection_id")
            connection = self.db.query(Connection).get(connection_id)

        client = GraphClient(connection)

        # Use delta query endpoint
        if cursor:
            # Continue from last cursor
            endpoint = cursor  # Delta link is full URL
        else:
            # First poll - get delta link
            endpoint = GRAPH_ENDPOINTS["delta"]
            params = {"$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments"}

            # Apply user filters from config
            if config.get("folder_filter"):
                params["$filter"] = f"parentFolderId eq '{config['folder_filter']}'"

        # Make API call
        if cursor:
            response = await client.get(cursor)  # Use full delta link
        else:
            response = await client.get(endpoint, params=params)

        # Extract new messages
        messages = response.get("value", [])

        # Normalize events
        events = [self._map_message_to_event(msg) for msg in messages]

        # Get new cursor
        new_cursor = response.get("@odata.deltaLink") or response.get("@odata.nextLink")

        return {
            "events": events,
            "cursor": new_cursor,
            "has_more": "@odata.nextLink" in response,
            "polling_interval": 300 if events else 600  # Poll faster when active
        }

    def poll_flagged_emails(
        self,
        cursor: str,
        config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Poll for newly flagged emails.

        Handler for: outlook_flagged_email trigger
        """
        connection = self._get_connection(context)
        client = GraphClient(connection)

        # Similar pattern to poll_new_emails but with flag filter
        endpoint = GRAPH_ENDPOINTS["messages"]
        params = {
            "$filter": "flag/flagStatus eq 'flagged'",
            "$orderby": "receivedDateTime desc"
        }

        # Use receivedDateTime as cursor for simple polling
        if cursor:
            params["$filter"] += f" and receivedDateTime gt {cursor}"

        response = await client.get(endpoint, params=params)
        messages = response.get("value", [])

        events = [self._map_flagged_message_event(msg) for msg in messages]

        # New cursor is the latest message timestamp
        new_cursor = messages[0]["receivedDateTime"] if messages else cursor

        return {
            "events": events,
            "cursor": new_cursor,
            "has_more": False,
            "polling_interval": 600
        }

    # === Helper Methods ===

    def _get_connection(self, context: Dict) -> Connection:
        """Get connection from context."""
        connection = context.get("connection")
        if connection:
            return connection
        connection_id = context.get("connection_id")
        return self.db.query(Connection).get(connection_id)

    def _map_message_to_event(self, message: Dict) -> Dict:
        """
        Map Graph API message to normalized event format.

        This is the event structure that gets written to TriggerInbox.
        """
        return {
            "event_id": message["id"],
            "event_type": "email_received",
            "occurred_at": message["receivedDateTime"],
            "data": {
                "message_id": message["id"],
                "subject": message.get("subject", ""),
                "from": message["from"]["emailAddress"]["address"],
                "from_name": message["from"]["emailAddress"].get("name"),
                "body_preview": message.get("bodyPreview", ""),
                "received_at": message["receivedDateTime"],
                "has_attachments": message.get("hasAttachments", False),
                "is_read": message.get("isRead", False)
            }
        }

    def _map_flagged_message_event(self, message: Dict) -> Dict:
        """Map flagged message to event."""
        return {
            "event_id": f"{message['id']}_flagged",
            "event_type": "email_flagged",
            "occurred_at": message.get("lastModifiedDateTime", message["receivedDateTime"]),
            "data": {
                "message_id": message["id"],
                "subject": message.get("subject", ""),
                "flagged_by": message["flag"].get("flaggedBy", {}).get("name"),
                "due_date": message["flag"].get("dueDateTime")
            }
        }
```

---

**4. Constants Module (Optional - `constants.py`)**

Extract constants to separate file **only** when you have many (>20 items). Otherwise keep them inline in `client.py`.

```python
# integrations/outlook/constants.py
"""Constants for Outlook/Graph API integration."""

# API Configuration
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_BATCH_LIMIT = 20

# Endpoints
GRAPH_ENDPOINTS = {
    "messages": "/me/messages",
    "send_mail": "/me/sendMail",
    "delta": "/me/messages/delta",
    "folders": "/me/mailFolders",
    "calendar": "/me/calendar/events",
}

# Well-known folder IDs
WELL_KNOWN_FOLDERS = {
    "inbox": "inbox",
    "sent": "sentitems",
    "drafts": "drafts",
    "deleted": "deleteditems",
    "junk": "junkemail",
}

# Scopes
REQUIRED_SCOPES = {
    "mail_read": "Mail.Read",
    "mail_send": "Mail.Send",
    "mail_readwrite": "Mail.ReadWrite",
    "calendar_read": "Calendars.Read",
}

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 60
RETRY_AFTER_DEFAULT = 60
```

**Most integrations**: Keep 5-10 constants inline in `client.py` at the top:

```python
# integrations/slack/client.py
"""Slack API HTTP client."""

import httpx

# Constants (inline for simple integrations)
SLACK_BASE_URL = "https://slack.com/api"
SLACK_ENDPOINTS = {
    "post_message": "/chat.postMessage",
    "upload_file": "/files.upload",
}

class SlackClient:
    # ... implementation ...
```

---

### 5.3 Integration Files Reference

Complete list of all files in the integration system and their responsibilities.

#### **Configuration Files** (`backend/configs/`)

| File              | Purpose                 | Content                                                                           |
| ----------------- | ----------------------- | --------------------------------------------------------------------------------- |
| `auth_schemas.py` | Auth schema definitions | Preset values (URLs, scopes), user fields, auth types for all integrations        |
| `tools.py`        | Tool catalog            | Tool definitions with slugs, names, input/output schemas, handler references      |
| `triggers.py`     | Trigger catalog         | Trigger definitions with slugs, polling config, input schemas, handler references |
| `integrations.py` | Integration catalog     | Integration metadata, supported auth schemas, capabilities                        |

#### **Database Models** (`backend/models/`)

| File               | Purpose                | Key Fields                                                  |
| ------------------ | ---------------------- | ----------------------------------------------------------- |
| `integration.py`   | Integration catalog    | key, name, logo_url, supported_auth_schemas                 |
| `connection.py`    | User connections       | integration_id, auth_schema_key, encrypted_token, is_active |
| `tool.py`          | Tool catalog           | slug, integration_id, handler, input/output schemas         |
| `trigger.py`       | Trigger catalog        | slug, integration_id, handler, trigger_config               |
| `agent_tool.py`    | Agent-tool bindings    | agent_id, tool_id, connection_id (optional)                 |
| `agent_trigger.py` | Agent-trigger bindings | agent_id, trigger_id, connection_id, cursor, next_run_at    |
| `trigger_inbox.py` | Event queue            | agent_trigger_id, payload, metadata, status, dedupe_key     |

#### **Integration Core** (`backend/integrations/`)

| File                 | Purpose                 | Key Functions                                            |
| -------------------- | ----------------------- | -------------------------------------------------------- |
| `handler_loader.py`  | Dynamic handler loading | `load_handler()` - Import and instantiate from config    |
| `executor.py`        | Tool execution          | `execute_tool()` - Load handler, validate, execute       |
| `trigger_runner.py`  | Trigger execution       | `run_trigger()` - Poll API, write events, update state   |
| `inbox_processor.py` | Event processing        | `process_pending_events()` - Create tasks from events    |
| `seed_loader.py`     | Database seeding        | `seed_integrations()`, `seed_tools()`, `seed_triggers()` |
| `encryption.py`      | Credential security     | `encrypt_credentials()`, `decrypt_credentials()`         |

#### **Auth Handlers** (`backend/integrations/auth/`)

| File             | Handler Class       | Purpose                 |
| ---------------- | ------------------- | ----------------------- |
| `oauth2_app.py`  | `OAuth2AppHandler`  | Client credentials flow |
| `oauth2_user.py` | `OAuth2UserHandler` | Authorization code flow |
| `api_key.py`     | `APIKeyHandler`     | API key/Bearer token    |
| `aws_sigv4.py`   | `AWSSignV4Handler`  | AWS request signing     |
| `basic.py`       | `BasicAuthHandler`  | HTTP Basic auth         |

#### **Provider Modules** (`backend/integrations/{provider}/`)

| File                      | Purpose              | Contains                                                             |
| ------------------------- | -------------------- | -------------------------------------------------------------------- |
| `client.py`               | HTTP client          | API requests, auth, retries, rate limiting, inline constants         |
| `actions.py`              | Tool/action handlers | Methods for each tool (send_email, etc.) + inline helper functions   |
| `triggers.py`             | Trigger handlers     | Polling methods (poll_new_emails, etc.) + inline event normalization |
| `constants.py` (optional) | Configuration        | Extract only if >20 constants (endpoints, IDs, scopes)               |

#### **Worker Tasks** (`backend/workers/`)

| File                    | Purpose         | Tasks                                                          |
| ----------------------- | --------------- | -------------------------------------------------------------- |
| `integration_worker.py` | Trigger polling | `schedule_trigger_polls()`, `run_trigger()`, `process_inbox()` |

---

### 5.4 Implementation Workflows

#### **Seeding Process**

Configuration files are seeded into the database on application startup:

```python
# On startup (main.py or init script)
from backend.integrations.seed_loader import seed_all

def startup_event():
    """Run on app startup."""
    seed_all()  # Upsert integrations, tools, triggers, auth schemas

# seed_loader.py
def seed_all():
    """Seed all integration configs to database."""
    with get_db_session() as db:
        seed_integrations(db)
        seed_tools(db)
        seed_triggers(db)

def seed_tools(db: Session):
    """Upsert tools from configs/tools.py."""
    from backend.configs.tools import ALL_TOOLS

    for tool_config in ALL_TOOLS:
        tool = db.query(Tool).filter(Tool.slug == tool_config["slug"]).first()

        if tool:
            # Update existing
            tool.name = tool_config["name"]
            tool.handler = tool_config["handler"]
            tool.input_schema = tool_config.get("input_schema", {})
            tool.output_schema = tool_config.get("output_schema", {})
        else:
            # Create new
            integration = db.query(Integration).filter(
                Integration.key == tool_config["integration_key"]
            ).first()

            tool = Tool(
                slug=tool_config["slug"],
                name=tool_config["name"],
                integration_id=integration.id,
                handler=tool_config["handler"],
                input_schema=tool_config.get("input_schema", {}),
                output_schema=tool_config.get("output_schema", {})
            )
            db.add(tool)

    db.commit()
```

#### **Connection Creation Flow**

1. User selects integration and auth schema
2. Frontend renders form based on `auth_schema.user_fields`
3. User provides credentials
4. Backend validates and encrypts credentials
5. Connection stored with `encrypted_token`

```python
# routes/connection_routes.py
@router.post("/connections")
def create_connection(request: ConnectionCreate, db: Session):
    # Get integration and auth schema
    integration = db.query(Integration).filter(
        Integration.key == request.integration_key
    ).first()

    # Encrypt credentials
    from backend.integrations.encryption import encrypt_credentials
    encrypted = encrypt_credentials(request.credentials)

    # Create connection
    connection = Connection(
        name=request.name,
        integration_id=integration.id,
        auth_schema_key=request.auth_schema_key,
        encrypted_token=encrypted,
        is_active=True
    )
    db.add(connection)
    db.commit()

    return connection
```

#### **Tool Execution Flow**

1. Agent calls tool during task execution
2. ToolsFactory loads handler from database config
3. Handler receives validated inputs + tool_runtime
4. Handler gets connection, makes API call
5. Result returned to agent

```python
# integrations/executor.py
def execute_tool(tool_slug: str, params: dict, tool_runtime: dict, db: Session):
    # Load tool definition from DB
    tool = db.query(Tool).filter(Tool.slug == tool_slug).first()

    # Load handler dynamically
    from backend.integrations.handler_loader import load_handler
    handler = load_handler(tool.handler, db)

    # Execute with runtime context
    result = handler(**params, tool_runtime=tool_runtime)

    return result
```

#### **Trigger Polling Flow**

1. Celery Beat schedules polls every 30s
2. Scheduler selects due AgentTriggers
3. TriggerRunner executes handler
4. Events written to TriggerInbox
5. AgentTrigger state updated (cursor, next_run_at)

```python
# workers/integration_worker.py
@celery_app.task
def run_trigger(agent_trigger_id: str):
    with get_db_session() as db:
        from backend.integrations.trigger_runner import TriggerRunner

        runner = TriggerRunner(agent_trigger_id, db)
        result = runner.run()

        return result
```

---

### 5.5 Auth Handler Architecture

**Centralized, Reusable Pattern**: Generic handlers + integration-specific presets.

```
configs/auth_schemas.py              integrations/auth/
┌──────────────────────┐            ┌─────────────────────┐
│ Auth Schema Preset   │            │  Generic Handler    │
│                      │            │                     │
│ {                    │──auth_type─>│ OAuth2AppHandler   │
│   auth_type: "..."   │            │ OAuth2UserHandler   │
│   preset: {...}      │            │ APIKeyHandler       │
│   user_fields: {...} │            │ AWSSignV4Handler    │
│ }                    │            │                     │
└──────────────────────┘            └─────────────────────┘
         │                                     │
         │                                     │
         └─────────────┬───────────────────────┘
                       ▼
              Connection.encrypted_token
              (Stored in database)
```

**Example**:

```python
# configs/auth_schemas.py - Integration-specific presets
AUTH_SCHEMAS = {
    "microsoft_graph_oauth": {
        "auth_type": "OAuth2App",
        "preset": {
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "https://graph.microsoft.com/.default"
        },
        "user_fields": ["client_id", "client_secret", "tenant_id"]
    }
}

# integrations/auth/oauth2_app.py - Generic handler
class OAuth2AppHandler:
    def get_token(self, preset: dict, credentials: dict) -> str:
        """Generic OAuth2 client credentials flow."""
        response = httpx.post(
            preset["token_url"].format(**credentials),
            data={"grant_type": "client_credentials", ...}
        )
        return response.json()["access_token"]
```

---

### 5.6 Handler Loading Pattern

**Dynamic loading** using `importlib` based on handler config from database:

```python
# integrations/handler_loader.py
import importlib

def load_handler(handler_config: dict, db: Session):
    """
    Load handler class/method from config.

    handler_config = {
        "module": "backend.integrations.outlook.actions",
        "class": "OutlookActions",
        "method": "send_email"
    }
    """
    module = importlib.import_module(handler_config["module"])
    handler_class = getattr(module, handler_config["class"])
    handler_instance = handler_class(db=db)
    return getattr(handler_instance, handler_config["method"])


# Usage in tool execution
tool = db.query(Tool).filter(Tool.slug == "outlook_send_email").first()
handler = load_handler(tool.handler, db)
result = handler(to="user@example.com", subject="Test", body="Hello", tool_runtime=runtime)
```

**Pattern Benefits**:

- ✅ No manual registry to maintain
- ✅ Handlers defined in config, loaded dynamically
- ✅ Easy to add new integrations without code changes
- ✅ Safe (validated handler paths in seed process)

---

### 5.7 Execution Flow Summary

**Tool Execution**:

```
User/Agent Request → ToolsFactory → load_handler() → OutlookTools.send_email()
                                                            ↓
                                                     Connection → Auth Handler → API Call
```

**Trigger Execution**:

```
Scheduler → Select due triggers → TriggerRunner → load_handler() → OutlookTriggers.poll()
                                                                          ↓
                                                                   Events → TriggerInbox
```

**Inbox Processing**:

```
InboxProcessor → Fetch pending events → Create Task → Agent Workflow
```

**Key Points**:

- Dynamic handler loading (no hardcoded registry)
- Centralized auth (reusable across integrations)
- Event normalization for consistency
- State management in AgentTrigger model

---

---

_(Detailed auth handler implementation examples are available in Section 8)_

---

## 6. Tools Architecture

This section describes how tools (actions) are configured, loaded, and executed by agents.

### 6.1 Tool Types Overview

| Type                 | Description                                   | Example                                     |
| -------------------- | --------------------------------------------- | ------------------------------------------- |
| **Integration Tool** | Requires a connection to external service     | `outlook_send_email`, `aws_s3_list_objects` |
| **Base Tool**        | Internal platform tools, no connection needed | `web_search`, `get_current_time`            |
| **Custom Tool**      | User-defined tools via OpenAPI specs          | Custom API endpoints                        |

### 6.2 Handler Config Format

**All tools use a standardized class-based handler pattern** with a consistent constructor signature.

#### Handler Configuration

```python
{
    "slug": "outlook_send_email",
    "name": "Send Email",
    "description": "Send an email via Outlook",
    "handler": {
        "module": "backend.integrations.outlook.actions",
        "class": "OutlookActions",
        "method": "send_email"
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"}
        },
        "required": ["to", "subject", "body"]
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "message_id": {"type": "string"}
        }
    }
}
```

#### Standard Handler Implementation

**All handler classes follow this pattern:**

```python
# backend/integrations/outlook/actions.py
from typing import Dict, Any
from sqlalchemy.orm import Session

class OutlookActions:
    """
    Tool handler for Outlook integration.

    Standard constructor: always receives (db: Session).
    All methods receive tool_runtime as last parameter.
    """

    def __init__(self, db: Session):
        """Standard constructor - receives DB session only."""
        self.db = db

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        tool_runtime: Dict[str, Any]
    ) -> dict:
        """
        Send email via Outlook.

        Args:
            to, subject, body: From input_schema
            tool_runtime: Injected by ToolsFactory with connection_id

        Returns:
            Dict matching output_schema
        """
        connection = resolve_connection(tool_runtime, self.db)
        client = OutlookClient(connection)
        result = client.send_email(to, subject, body)

        return {
            "success": True,
            "message_id": result.id
        }
```

#### Base Tools (No Connection Required)

For platform tools that don't need external connections:

```python
# backend/tools/base/time_tools.py
class TimeTools:
    def __init__(self, db: Session):
        self.db = db

    def get_current_time(self, timezone: str = "UTC") -> dict:
        """No tool_runtime needed - no connection required."""
        return {
            "timestamp": datetime.now(tz=timezone).isoformat(),
            "timezone": timezone
        }
```

### 6.3 ToolsFactory Architecture

The `ToolsFactory` class is responsible for:

1. Loading tool configs from the database
2. Dynamically importing handler modules
3. Generating LangChain `StructuredTool` instances
4. Injecting `tool_runtime` context when needed

```python
# backend/tools/factory.py
from typing import Dict, List, Any, Optional
from langchain_core.tools import StructuredTool
from pydantic import create_model
import importlib
import inspect

class ToolsFactory:
    """Factory for creating LangChain tools from config definitions."""

    def __init__(self, db: Session, org_schema: str):
        self.db = db
        self.org_schema = org_schema

    def create_tools(
        self,
        tool_keys: List[str],
        tool_runtime: Dict[str, Any]
    ) -> List[StructuredTool]:
        """
        Create StructuredTool instances for the given tool keys.

        Args:
            tool_keys: List of tool keys to create (e.g., ["outlook_send_email"])
            tool_runtime: Runtime context passed to tools that need it
                - connection_id: Optional explicit connection ID
                - connection: Optional pre-resolved Connection object
                - agent_id: The executing agent's ID
                - task_id: The current task ID
                - org_schema: Organization schema name

        Returns:
            List of LangChain StructuredTool instances
        """
        tools = []
        tool_configs = self._load_tool_configs(tool_keys)

        for config in tool_configs:
            tool = self._create_single_tool(config, tool_runtime)
            if tool:
                tools.append(tool)

        return tools

    def _load_tool_configs(self, tool_keys: List[str]) -> List[Dict]:
        """Load tool configurations from database."""
        return self.db.query(Tool).filter(
            Tool.key.in_(tool_keys),
            Tool.is_active == True
        ).all()

    def _create_single_tool(
        self,
        config: Dict,
        tool_runtime: Dict[str, Any]
    ) -> Optional[StructuredTool]:
        """Create a single StructuredTool from config."""
        handler = config.get("handler", {})

        # Import the module
        module = importlib.import_module(handler["module"])

        # Get the callable (function or method)
        if "class" in handler:
            # Class-based handler
            cls = getattr(module, handler["class"])
            instance = self._instantiate_class(cls, handler.get("init_args"))
            func = getattr(instance, handler["method"])
        else:
            # Standalone function
            func = getattr(module, handler["function"])

        # Wrap with tool_runtime injection if needed
        wrapped_func = self._wrap_with_runtime(func, tool_runtime)

        # Create Pydantic model for parameters
        args_schema = self._create_args_schema(config)

        return StructuredTool(
            name=config["key"],
            description=config["description"],
            func=wrapped_func,
            args_schema=args_schema
        )

    def _instantiate_class(
        self,
        cls: type,
        init_args: Optional[Dict] = None
    ) -> Any:
        """Instantiate a handler class with appropriate arguments."""
        sig = inspect.signature(cls.__init__)
        params = list(sig.parameters.keys())[1:]  # Skip 'self'

        if init_args:
            # Custom init args provided
            return cls(**init_args)
        elif "db" in params:
            # Standard DB injection
            return cls(db=self.db)
        else:
            # No-arg constructor
            return cls()

    def _wrap_with_runtime(
        self,
        func: callable,
        tool_runtime: Dict[str, Any]
    ) -> callable:
        """Wrap function to inject tool_runtime if signature accepts it."""
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())

        if "tool_runtime" in params:
            # Function expects tool_runtime - inject it
            def wrapper(**kwargs):
                kwargs["tool_runtime"] = tool_runtime
                return func(**kwargs)
            return wrapper
        else:
            # Function doesn't need tool_runtime
            return func

    def _create_args_schema(self, config: Dict) -> type:
        """Create Pydantic model from JSON Schema parameters."""
        params = config.get("parameters", {})
        properties = params.get("properties", {})
        required = params.get("required", [])

        fields = {}
        for name, prop in properties.items():
            python_type = self._json_type_to_python(prop.get("type", "string"))
            default = ... if name in required else None
            fields[name] = (python_type, default)

        return create_model(f"{config['key']}_args", **fields)

    def _json_type_to_python(self, json_type: str) -> type:
        """Convert JSON Schema type to Python type."""
        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict
        }
        return type_map.get(json_type, str)
```

### 6.4 Connection Resolution for Tools

For multi-connection scenarios (e.g., multiple AWS accounts, multiple email connections), tools must have an explicit connection specified. **No automatic fallback** to prevent ambiguity.

| Source                          | How                                              | Required |
| ------------------------------- | ------------------------------------------------ | -------- |
| `AgentTool.connection_id`       | Admin pins connection when binding tool to agent | Option 1 |
| `tool_runtime["connection_id"]` | Provided by trigger/workflow context             | Option 2 |

**One of the above MUST be set. Tools will error if no connection is specified.**

```python
# backend/tools/connection_resolver.py
from typing import Dict, Any
from backend.models import Connection

def resolve_connection(
    tool_runtime: Dict[str, Any],
    db: Session,
) -> Connection:
    """
    Resolve the connection to use for tool execution.

    Explicit-only resolution - no automatic fallback.

    Args:
        tool_runtime: Runtime context with connection info
        db: Database session

    Returns:
        Connection object

    Raises:
        ValueError: If connection_id not provided or connection not found
    """
    connection_id = tool_runtime.get("connection_id")

    if not connection_id:
        raise ValueError(
            "No connection specified. Set connection_id in AgentTool or provide via task context."
        )

    connection = db.query(Connection).filter(
        Connection.id == connection_id,
        Connection.is_active == True,
        Connection.is_valid == True
    ).first()

    if not connection:
        raise ValueError(
            f"Connection {connection_id} not found or inactive. "
            "Please verify connection exists and is enabled."
        )

    return connection
```

**Usage in Tool Implementation:**

```python
class OutlookTools:
    def __init__(self, db: Session):
        self.db = db

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        tool_runtime: Dict[str, Any]
    ) -> dict:
        """
        Send email via Outlook.

        Raises ValueError if connection not specified or invalid.
        """
        # Resolve connection (will raise if not found)
        connection = resolve_connection(
            tool_runtime=tool_runtime,
            db=self.db
        )

        # Get authenticated client
        client = OutlookClient(connection)
        result = client.send_email(to, subject, body)

        return {"success": True, "message_id": result.id}
```

---

#### 6.4.1 Approach A: Database Pattern (AgentTool Table)

**Setup Pattern**:

```python
# Admin binds tools to agent with optional connection pinning
AgentTool.create(
    agent_id="bot-123",
    tool_id="outlook-send-email-id",
    connection_id="conn-outlook-prod"  # Optional pin
)
```

**Runtime Pattern**:

```python
# Query agent's tools
agent_tools = db.query(AgentTool).filter(AgentTool.agent_id == agent.id).all()

# Build tool_runtime for each tool
for agent_tool in agent_tools:
    connection_id = agent_tool.connection_id or task.metadata.get("connection_id")

    tool_runtime = {"connection_id": connection_id, "agent_id": agent.id}
    tool = ToolsFactory.create_tool(agent_tool.tool, tool_runtime, db)
```

**Key Points**:

- Database table enforces constraints (unique, FK)
- Simple JOIN queries: `WHERE agent_id = ? AND tool_id = ?`
- Built-in audit trail via timestamps

---

#### 6.4.2 Approach B: Config Pattern (Agent.config JSONB)

**Setup Pattern**:

```python
# Each tool specifies its connection
agent.config = {
    "tools": [
        {"slug": "outlook_send_email", "connection_id": "conn-outlook-prod"},
        {"slug": "aws_s3_upload", "connection_id": "conn-aws-finance"}
    ]
}
```

**Runtime Pattern**:

```python
# Load tools from config
tool_configs = agent.config.get("tools", [])

for tool_config in tool_configs:
    tool_def = db.query(Tool).filter(Tool.slug == tool_config["slug"]).first()

    # Resolve connection: config → task metadata → error
    connection_id = tool_config.get("connection_id") or task.metadata.get("connection_id")

    tool_runtime = {"connection_id": connection_id, "agent_id": agent.id}
    tool = ToolsFactory.create_tool(tool_def, tool_runtime, db)
```

**Key Points**:

- No extra tables, single JSON update
- Per-tool connection control
- Application-level validation required
- Flexible schema evolution

---

#### 6.4.3 Trigger Context Flow

Connection context automatically flows from trigger events to tools:

```python
# 1. Trigger writes event with connection metadata
TriggerInbox.create(
    payload={"email_id": "msg-123"},
    metadata={"connection_id": "conn-outlook-prod", "integration_key": "outlook"}
)

# 2. Inbox processor passes to task
Task.create(
    metadata={"connection_id": event.metadata["connection_id"]}
)

# 3. Tool uses connection from task
tool_runtime = {"connection_id": task.metadata["connection_id"]}
```

**Result**: Email received in `sales@company.com` → reply sent from `sales@company.com`

---

#### 6.4.4 Storage Comparison

**Approach A (Database)**:

```
agent_tools table:
┌──────────┬────────────────────┬──────────────────┐
│ agent_id │ tool_slug          │ connection_id    │
├──────────┼────────────────────┼──────────────────┤
│ bot-123  │ outlook_send_email │ conn-outlook-001 │
│ bot-123  │ aws_s3_upload      │ conn-aws-001     │
└──────────┴────────────────────┴──────────────────┘
```

**Approach B (Config)**:

```json
agent.config = {
  "tools": [
    {"slug": "outlook_send_email", "connection_id": "conn-outlook-001"},
    {"slug": "aws_s3_upload", "connection_id": "conn-aws-001"}
  ]
}
```

---

### 6.5 Tool Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Tool Execution Flow                               │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│    Agent     │     │ ToolsFactory │     │  Handler     │     │ Connection  │
│   Runtime    │     │              │     │  Class       │     │  Resolver   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘     └──────┬──────┘
       │                    │                    │                    │
       │ 1. Request tools   │                    │                    │
       │    [tool_keys]     │                    │                    │
       │───────────────────>│                    │                    │
       │                    │                    │                    │
       │                    │ 2. Load configs    │                    │
       │                    │    from DB         │                    │
       │                    │                    │                    │
       │                    │ 3. Import modules  │                    │
       │                    │    & create tools  │                    │
       │                    │                    │                    │
       │ 4. StructuredTools │                    │                    │
       │<───────────────────│                    │                    │
       │                    │                    │                    │
       │ 5. LLM invokes     │                    │                    │
       │    tool with args  │                    │                    │
       │────────────────────────────────────────>│                    │
       │                    │                    │                    │
       │                    │                    │ 6. Resolve         │
       │                    │                    │    connection      │
       │                    │                    │───────────────────>│
       │                    │                    │                    │
       │                    │                    │ 7. Connection obj  │
       │                    │                    │<───────────────────│
       │                    │                    │                    │
       │                    │                    │ 8. Execute with    │
       │                    │                    │    auth client     │
       │                    │                    │                    │
       │ 9. Result          │                    │                    │
       │<────────────────────────────────────────│                    │
       │                    │                    │                    │
```

### 6.6 Agent Workflow Integration

When an agent runs, the workflow creates tools with the appropriate runtime context:

```python
# backend/agents/workflow.py
from backend.tools.factory import ToolsFactory

class AgentWorkflow:
    def __init__(self, db: Session, agent: Agent, task: Task):
        self.db = db
        self.agent = agent
        self.task = task

    def build_tools(self) -> List[StructuredTool]:
        """Build tools for this agent execution."""

        # Get tool keys assigned to this agent
        agent_tools = self.db.query(AgentTool).filter(
            AgentTool.agent_id == self.agent.id,
            AgentTool.is_active == True
        ).all()

        tool_keys = [at.tool_key for at in agent_tools]

        # Build tool_runtime context
        tool_runtime = {
            "agent_id": self.agent.id,
            "task_id": self.task.id,
            "org_schema": self.agent.org_schema,
            # Connection from trigger context (if task came from trigger)
            "connection_id": self.task.metadata.get("connection_id"),
            "connection": self.task.metadata.get("connection"),
        }

        # Override with pinned connections from AgentTool
        pinned_connections = {
            at.tool_key: at.connection_id
            for at in agent_tools
            if at.connection_id
        }

        # Create factory and generate tools
        factory = ToolsFactory(db=self.db, org_schema=self.agent.org_schema)

        tools = []
        for tool_key in tool_keys:
            # Use pinned connection if set, otherwise use task context
            runtime = tool_runtime.copy()
            if tool_key in pinned_connections:
                runtime["connection_id"] = pinned_connections[tool_key]

            tool = factory.create_tools([tool_key], runtime)
            tools.extend(tool)

        return tools
```

**Database Schema for Agent Tools:**

```sql
-- AgentTool: Links agents to tools with optional connection pinning
CREATE TABLE agent_tools (
    id UUID PRIMARY KEY,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    tool_key VARCHAR(255) NOT NULL,
    connection_id UUID REFERENCES connections(id) ON DELETE SET NULL,  -- Optional pinned connection
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(agent_id, tool_key)
);
```

**Benefits of This Architecture:**

| Benefit                  | Description                                                    |
| ------------------------ | -------------------------------------------------------------- |
| **Flexibility**          | Supports both pinned and dynamic connection resolution         |
| **Trigger Context**      | Tools automatically use the connection that triggered the task |
| **Admin Control**        | Admins can pin specific connections for specific agent tools   |
| **Backwards Compatible** | Single-connection setups work without any configuration        |
| **Config-Driven**        | Tool behavior defined in config, not hardcoded                 |
| **Type Safety**          | Pydantic models for parameter validation                       |
| **Testability**          | Easy to mock tool_runtime for unit tests                       |

---

## 7. Triggers Architecture

This section details how triggers are configured, scheduled, executed, and how events flow from external services to agent workflows. The polling-first architecture ensures air-gapped compatibility while maintaining near real-time event processing.

### 7.1 Trigger System Overview

The trigger system consists of four main components that work together:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Trigger System Components                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Scheduler     │    │  Trigger Runner │    │  TriggerInbox   │    │ Inbox Processor │
│   (Celery Beat) │───>│  (Celery Task)  │───>│   (Database)    │───>│ (Agent Workflow)│
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
        │                      │                      │                      │
        │                      │                      │                      │
   Selects due            Polls external         Stores normalized      Routes events
   AgentTriggers          services for           events durably         to agents and
   and enqueues           new events                                    creates tasks
```

| Component           | Responsibility                             | Database Table                    |
| ------------------- | ------------------------------------------ | --------------------------------- |
| **Scheduler**       | Finds due triggers, enqueues polling tasks | `agent_triggers`                  |
| **Trigger Runner**  | Executes handler, writes events to inbox   | `agent_triggers`, `trigger_inbox` |
| **TriggerInbox**    | Durable event storage with deduplication   | `trigger_inbox`                   |
| **Inbox Processor** | Consumes events, creates agent tasks       | `tasks`                           |

### 7.2 Polling Architecture

We use a **polling-first** architecture for air-gapped environment compatibility. Even for services that support webhooks, polling provides a consistent, reliable fallback.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Polling Architecture Flow                            │
└─────────────────────────────────────────────────────────────────────────────┘

1. SCHEDULER PHASE (Every 30 seconds)
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ SELECT * FROM agent_triggers                                            │
   │ WHERE is_enabled = TRUE                                                 │
   │   AND next_run_at <= NOW()                                              │
   │   AND (locked_until IS NULL OR locked_until < NOW())                    │
   │   AND (backoff_until IS NULL OR backoff_until < NOW())                  │
   │                                                                         │
   │ For each due trigger:                                                   │
   │   1. Set locked_until = NOW() + lock_duration                           │
   │   2. Enqueue Celery task: run_trigger.delay(agent_trigger_id)           │
   └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
2. TRIGGER RUNNER PHASE (Celery Worker)
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ def run_trigger(agent_trigger_id):                                      │
   │     # Load context                                                      │
   │     agent_trigger = load_agent_trigger(agent_trigger_id)                │
   │     connection = load_connection(agent_trigger.connection_id)           │
   │     trigger = load_trigger(agent_trigger.trigger_id)                    │
   │     state = load_trigger_state(agent_trigger_id)                        │
   │                                                                         │
   │     # Resolve and execute handler                                       │
   │     handler = resolve_handler(trigger.handler)                          │
   │     result = handler(                                                   │
   │         cursor=state.cursor,                                            │
   │         config=agent_trigger.config,                                    │
   │         credentials=decrypt(connection.encrypted_credentials),          │
   │         connection_config=connection.connection_config,                 │
   │     )                                                                   │
   │                                                                         │
   │     # Process results                                                   │
   │     events = normalize_events(result["events"])                         │
   │     write_trigger_inbox(events, agent_trigger_id, connection.id)        │
   │     update_trigger_state(state, result)                                 │
   └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
3. INBOX PROCESSOR PHASE (Separate Celery Task)
   ┌─────────────────────────────────────────────────────────────────────────┐
   │ SELECT * FROM trigger_inbox                                             │
   │ WHERE status = 'pending'                                                │
   │ ORDER BY created_at                                                     │
   │ LIMIT batch_size                                                        │
   │ FOR UPDATE SKIP LOCKED                                                  │
   │                                                                         │
   │ For each event:                                                         │
   │   1. Set status = 'processing'                                          │
   │   2. Create Task for agent with event payload                           │
   │   3. Set status = 'done' (or 'failed' with retry)                       │
   └─────────────────────────────────────────────────────────────────────────┘
```

**Polling Methods by Integration:**

| Integration    | Polling Method        | Cursor Type              | Notes                        |
| -------------- | --------------------- | ------------------------ | ---------------------------- |
| **Outlook**    | Delta Query           | `deltaLink` URL          | Efficient incremental sync   |
| **Gmail**      | History API           | `historyId`              | Incremental since last check |
| **AWS S3**     | list_objects_v2       | `LastModified` timestamp | Marker-based pagination      |
| **SharePoint** | Delta Query           | `deltaLink` URL          | Same as Outlook              |
| **Slack**      | conversations.history | `latest` timestamp       | Channel-based polling        |

### 7.3 Handler Config Format

Triggers use the same handler config pattern as tools:

```python
{
    "slug": "outlook_new_email",
    "name": "New Email Received",
    "description": "Triggers when a new email arrives in the mailbox",
    "integration_key": "outlook",
    "handler": {
        "module": "integrations.providers.outlook.triggers",
        "class": "OutlookPoller",
        "method": "poll_new_email",
    },
    "trigger_config": {
        "polling_method": "delta_query",
        "graph_endpoint": "/users/{mailbox_email}/mailFolders/{folder}/messages/delta",
        "default_polling_interval": 300,
        "min_polling_interval": 60,
        "max_polling_interval": 3600,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "mailbox_email": {"type": "string", "description": "Mailbox to monitor"},
            "folder": {"type": "string", "default": "Inbox"},
            "include_attachments": {"type": "boolean", "default": false},
        },
        "required": ["mailbox_email"],
    },
}
```

**Handler Implementation Pattern:**

```python
# integrations/providers/outlook/triggers.py

class OutlookPoller:
    """Polling handlers for Outlook/Microsoft Graph triggers."""

    def __init__(self, connection: Connection, db: Session):
        self.connection = connection
        self.db = db
        self.credentials = decrypt_credentials(connection.encrypted_credentials)
        self.auth_handler = get_auth_handler(
            auth_schema=get_auth_schema(connection.auth_schema_key),
            credentials=self.credentials,
            token_data=decrypt_credentials(connection.encrypted_token) if connection.encrypted_token else None,
        )

    async def poll_new_email(
        self,
        cursor: Optional[Dict],
        config: Dict,
        context: Dict,
    ) -> Dict:
        """
        Poll for new emails using Microsoft Graph delta query.

        Args:
            cursor: Previous state {"delta_link": "...", "last_message_id": "..."}
            config: User config from AgentTrigger {"mailbox_email": "...", "folder": "..."}
            context: Runtime context {"agent_trigger_id": "..."}

        Returns:
            {
                "events": [...],           # List of new email events
                "cursor": {...},           # Updated cursor for next poll
                "has_more": bool,          # Whether more pages exist
                "polling_interval": int,   # Suggested next interval (seconds)
            }
        """
        headers = await self.auth_handler.get_auth_headers()

        # Build Graph API URL
        if cursor and cursor.get("delta_link"):
            url = cursor["delta_link"]
        else:
            mailbox = config["mailbox_email"]
            folder = config.get("folder", "Inbox")
            url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/{folder}/messages/delta"
            url += "?$select=id,subject,from,receivedDateTime,bodyPreview,hasAttachments"

        # Fetch delta
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        # Extract events
        events = []
        for message in data.get("value", []):
            if "@removed" not in message:  # Skip deletions
                events.append({
                    "event_type": "new_email",
                    "event_id": message["id"],
                    "occurred_at": message.get("receivedDateTime"),
                    "data": {
                        "message_id": message["id"],
                        "subject": message.get("subject"),
                        "from": message.get("from", {}).get("emailAddress", {}),
                        "body_preview": message.get("bodyPreview"),
                        "has_attachments": message.get("hasAttachments", False),
                    },
                })

        # Build new cursor
        new_cursor = {
            "delta_link": data.get("@odata.deltaLink"),
            "next_link": data.get("@odata.nextLink"),
        }

        return {
            "events": events,
            "cursor": new_cursor,
            "has_more": "@odata.nextLink" in data,
            "polling_interval": 300 if events else 600,  # Poll faster when active
        }
```

### 7.4 Trigger Runner Implementation

The Trigger Runner is responsible for executing trigger handlers and managing the lifecycle of a single poll operation.

```python
# integrations/core/trigger_runner.py

import importlib
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from backend.models import AgentTrigger, Connection, Trigger, TriggerInbox
from backend.integrations.core.encryption import decrypt_credentials
from backend.db.session import get_session

logger = logging.getLogger(__name__)


class TriggerRunner:
    """Executes a single trigger poll and processes results."""

    def __init__(self, agent_trigger_id: str, org_schema: str):
        self.agent_trigger_id = agent_trigger_id
        self.org_schema = org_schema

    def run(self) -> Dict[str, Any]:
        """
        Execute the trigger poll.

        Returns:
            {
                "success": bool,
                "events_count": int,
                "error": Optional[str],
            }
        """
        with get_session(self.org_schema) as db:
            try:
                # Load all required data
                agent_trigger = db.query(AgentTrigger).filter(
                    AgentTrigger.id == self.agent_trigger_id
                ).first()

                if not agent_trigger or not agent_trigger.is_enabled:
                    return {"success": False, "events_count": 0, "error": "Trigger disabled"}

                connection = db.query(Connection).filter(
                    Connection.id == agent_trigger.connection_id
                ).first()

                if not connection or not connection.is_active:
                    return {"success": False, "events_count": 0, "error": "Connection inactive"}

                trigger = db.query(Trigger).filter(
                    Trigger.id == agent_trigger.trigger_id
                ).first()

                # Resolve handler
                handler_callable = self._resolve_handler(trigger.handler, connection, db)

                # Execute poll with current cursor from AgentTrigger
                result = handler_callable(
                    cursor=agent_trigger.cursor,
                    config=agent_trigger.config,
                    context={"agent_trigger_id": str(self.agent_trigger_id)},
                )

                # Normalize and write events to inbox
                events = self._normalize_events(result.get("events", []), trigger.slug)
                self._write_to_inbox(db, events, agent_trigger, connection, trigger)

                # Update AgentTrigger polling state
                self._update_state(db, agent_trigger, result, success=True)

                db.commit()

                return {
                    "success": True,
                    "events_count": len(events),
                    "error": None,
                }

            except Exception as e:
                logger.exception(f"Trigger {self.agent_trigger_id} failed: {e}")
                db.rollback()

                # Update AgentTrigger state with error
                self._update_state(db, agent_trigger, {}, success=False, error=str(e))
                db.commit()

                return {
                    "success": False,
                    "events_count": 0,
                    "error": str(e),
                }

    def _resolve_handler(self, handler_config: Dict, connection: Connection, db) -> callable:
        """Dynamically import and instantiate the handler."""
        module = importlib.import_module(handler_config["module"])

        if "class" in handler_config:
            cls = getattr(module, handler_config["class"])
            instance = cls(connection=connection, db=db)
            return getattr(instance, handler_config["method"])
        else:
            return getattr(module, handler_config["function"])

    def _normalize_events(self, events: list, trigger_slug: str) -> list:
        """Normalize events to standard format."""
        normalized = []
        for event in events:
            normalized.append({
                "event_type": event.get("event_type", trigger_slug),
                "event_id": event.get("event_id", str(uuid.uuid4())),
                "occurred_at": event.get("occurred_at", datetime.utcnow().isoformat()),
                "data": event.get("data", {}),
                "raw": event,
            })
        return normalized

    def _write_to_inbox(
        self,
        db,
        events: list,
        agent_trigger: AgentTrigger,
        connection: Connection,
        trigger: Trigger,
    ):
        """
        Write normalized events to TriggerInbox with deduplication and metadata.

        Metadata includes connection context for runtime tool execution.
        """
        for event in events:
            dedupe_key = f"{agent_trigger.id}:{event['event_type']}:{event['event_id']}"

            # Check for duplicate
            existing = db.query(TriggerInbox).filter(
                TriggerInbox.dedupe_key == dedupe_key
            ).first()

            if existing:
                logger.debug(f"Skipping duplicate event: {dedupe_key}")
                continue

            inbox_entry = TriggerInbox(
                agent_trigger_id=agent_trigger.id,
                event_type=event["event_type"],
                occurred_at=event.get("occurred_at"),
                dedupe_key=dedupe_key,
                payload=event["data"],  # Normalized event data
                metadata={
                    "connection_id": str(connection.id),
                    "connection_name": connection.name,
                    "integration_key": connection.integration.key,
                    "trigger_slug": trigger.slug,
                    "trigger_name": trigger.name,
                    "auth_schema_key": connection.auth_schema_key,
                },
                status="pending",
            )
            db.add(inbox_entry)

    def _update_state(
        self,
        db,
        agent_trigger: AgentTrigger,
        result: Dict,
        success: bool,
        error: str = None,
    ):
        """Update AgentTrigger polling state after poll."""

        state.last_polled_at = datetime.utcnow()
        state.locked_until = None  # Release lock

        if success:
            agent_trigger.cursor = result.get("cursor")
            agent_trigger.error_count = 0
            agent_trigger.last_error = None
            agent_trigger.last_polled_at = datetime.utcnow()
            agent_trigger.locked_until = None  # Release lock

            # Calculate next run
            interval = result.get("polling_interval", 300)
            agent_trigger.next_run_at = datetime.utcnow() + timedelta(seconds=interval)
        else:
            agent_trigger.error_count = (agent_trigger.error_count or 0) + 1
            agent_trigger.last_error = error
            agent_trigger.locked_until = None  # Release lock

            # Exponential backoff on error
            backoff = min(3600, 60 * (2 ** agent_trigger.error_count))
            agent_trigger.backoff_until = datetime.utcnow() + timedelta(seconds=backoff)
            agent_trigger.next_run_at = agent_trigger.backoff_until

            # Disable after 5 consecutive failures
            if agent_trigger.error_count >= 5:
                agent_trigger.is_enabled = False
                logger.error(f"AgentTrigger {agent_trigger.id} disabled after 5 failures")
```

### 7.5 Polling State Management

AgentTrigger includes polling state fields to track each trigger's polling cycle:

| Field            | Purpose                              | Example                                                |
| ---------------- | ------------------------------------ | ------------------------------------------------------ |
| `cursor`         | Position marker for incremental sync | `{"delta_link": "https://...", "history_id": "12345"}` |
| `next_run_at`    | When to poll next                    | `2024-01-15 10:30:00`                                  |
| `locked_until`   | Prevents concurrent polls            | `2024-01-15 10:25:30`                                  |
| `backoff_until`  | Error backoff expiry                 | `2024-01-15 11:00:00`                                  |
| `error_count`    | Consecutive failures                 | `3`                                                    |
| `last_error`     | Most recent error message            | `"401 Unauthorized"`                                   |
| `last_polled_at` | Last successful poll time            | `2024-01-15 10:20:00`                                  |

**State Transitions:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     AgentTrigger Polling State Lifecycle                     │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌───────────────┐
                    │    IDLE       │
                    │ next_run_at   │
                    │ in future     │
                    └───────┬───────┘
                            │ next_run_at <= NOW()
                            ▼
                    ┌───────────────┐
                    │   SCHEDULED   │
                    │ locked_until  │
                    │ = NOW() + 5m  │
                    └───────┬───────┘
                            │ Celery task starts
                            ▼
                    ┌───────────────┐
                    │   RUNNING     │
                    │ Poll in       │
                    │ progress      │
                    └───────┬───────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
      ┌───────────────┐           ┌───────────────┐
      │   SUCCESS     │           │    ERROR      │
      │ cursor updated│           │ error_count++ │
      │ next_run_at   │           │ backoff_until │
      │ = NOW() + int │           │ = exp backoff │
      └───────────────┘           └───────────────┘
```

### 7.6 TriggerInbox Processing

The TriggerInbox acts as a durable event queue between polling and agent task creation:

```python
# integrations/core/inbox_processor.py

from celery import shared_task
from datetime import datetime
from typing import List

from backend.models import TriggerInbox, AgentTrigger, Task
from backend.db.session import get_session


@shared_task(bind=True, max_retries=3)
def process_trigger_inbox(self, org_schema: str, batch_size: int = 100):
    """
    Process pending events from TriggerInbox.

    This task:
    1. Selects pending events with row-level locking
    2. Creates Tasks for the associated agents
    3. Marks events as done/failed
    """
    with get_session(org_schema) as db:
        # Select and lock pending events
        events = db.query(TriggerInbox).filter(
            TriggerInbox.status == "pending"
        ).order_by(
            TriggerInbox.created_at
        ).limit(batch_size).with_for_update(skip_locked=True).all()

        for event in events:
            try:
                event.status = "processing"
                event.attempts += 1
                event.last_attempt_at = datetime.utcnow()
                db.flush()

                # Load agent trigger to get agent_id
                agent_trigger = db.query(AgentTrigger).filter(
                    AgentTrigger.id == event.agent_trigger_id
                ).first()

                if not agent_trigger or not agent_trigger.is_enabled:
                    event.status = "skipped"
                    continue

                # Create task for agent with connection context from event metadata
                task = Task(
                    agent_id=agent_trigger.agent_id,
                    task_type="trigger",
                    status="pending",
                    metadata={
                        "trigger_inbox_id": str(event.id),
                        "agent_trigger_id": str(event.agent_trigger_id),
                        "connection_id": event.metadata.get("connection_id"),
                        "integration_key": event.metadata.get("integration_key"),
                        "trigger_slug": event.metadata.get("trigger_slug"),
                    },
                    input_data={
                        "trigger_event": event.payload,
                        "event_type": event.event_type,
                        "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
                    },
                )
                db.add(task)

                event.status = "done"

            except Exception as e:
                logger.exception(f"Failed to process inbox event {event.id}: {e}")
                event.status = "failed" if event.attempts >= 3 else "pending"
                event.last_error = str(e)

        db.commit()

        return {"processed": len(events)}
```

**Inbox Status Flow:**

```
pending → processing → done
                    ↘ failed (after max retries)
                    ↘ skipped (trigger disabled)
```

### 7.7 Event Normalization

All trigger events are normalized to a standard format before being written to TriggerInbox:

```python
# Standard Event Format
{
    "event_type": "new_email",              # Trigger type identifier
    "event_id": "AAMkAGI2...",              # Unique ID from source system
    "occurred_at": "2024-01-15T10:30:00Z",  # When event occurred
    "data": {                               # Normalized payload
        "message_id": "AAMkAGI2...",
        "subject": "Q4 Report",
        "from": {"name": "John", "email": "john@example.com"},
        "body_preview": "Please find attached...",
        "has_attachments": true,
    },
    "raw": {...},                           # Original API response (for debugging)
}
```

**Normalization by Integration:**

| Integration    | Source Format     | Normalized Fields                                                  |
| -------------- | ----------------- | ------------------------------------------------------------------ |
| **Outlook**    | Graph API Message | `message_id`, `subject`, `from`, `body_preview`, `has_attachments` |
| **Gmail**      | Gmail API Message | `message_id`, `thread_id`, `subject`, `from`, `snippet`, `labels`  |
| **AWS S3**     | ListObjectsV2     | `bucket`, `key`, `size`, `last_modified`, `etag`                   |
| **SharePoint** | DriveItem         | `item_id`, `name`, `path`, `size`, `modified_by`, `web_url`        |

### 7.8 Scheduler & Celery Integration

The scheduler runs as a Celery Beat task that finds due triggers and enqueues polling tasks:

```python
# integrations/tasks.py

from celery import shared_task
from celery.schedules import crontab
from datetime import datetime

from backend.db.session import get_all_org_schemas, get_session
from backend.models import AgentTrigger


# Celery Beat Schedule
CELERYBEAT_SCHEDULE = {
    "trigger-scheduler": {
        "task": "integrations.tasks.schedule_triggers",
        "schedule": 30.0,  # Every 30 seconds
    },
    "inbox-processor": {
        "task": "integrations.tasks.process_all_inboxes",
        "schedule": 10.0,  # Every 10 seconds
    },
}


@shared_task
def schedule_triggers():
    """
    Scheduler task: Find due triggers across all orgs and enqueue polling tasks.
    """
    for org_schema in get_all_org_schemas():
        with get_session(org_schema) as db:
            # Find enabled triggers that are due
            due_triggers = db.query(AgentTrigger).filter(
                AgentTrigger.is_enabled == True,
                AgentTrigger.next_run_at <= datetime.utcnow(),
                (AgentTrigger.locked_until == None) | (AgentTrigger.locked_until < datetime.utcnow()),
                (AgentTrigger.backoff_until == None) | (AgentTrigger.backoff_until < datetime.utcnow()),
            ).with_for_update(skip_locked=True).all()

            for agent_trigger in due_triggers:
                # Acquire lock
                agent_trigger.locked_until = datetime.utcnow() + timedelta(minutes=5)
                db.flush()

                # Enqueue polling task
                run_trigger.delay(
                    agent_trigger_id=str(agent_trigger.id),
                    org_schema=org_schema,
                )

            db.commit()


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_trigger(self, agent_trigger_id: str, org_schema: str):
    """
    Worker task: Execute a single trigger poll.
    """
    runner = TriggerRunner(agent_trigger_id, org_schema)
    result = runner.run()

    if not result["success"] and result.get("error"):
        # Retry on transient errors
        if "timeout" in result["error"].lower() or "429" in result["error"]:
            raise self.retry(exc=Exception(result["error"]))

    return result


@shared_task
def process_all_inboxes():
    """
    Process TriggerInbox for all organizations.
    """
    for org_schema in get_all_org_schemas():
        process_trigger_inbox.delay(org_schema=org_schema)
```

**Scheduler Flow Diagram:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Celery Beat + Worker Flow                            │
└─────────────────────────────────────────────────────────────────────────────┘

  Celery Beat                    Redis Queue                  Celery Workers
  ───────────                    ───────────                  ──────────────

  Every 30s:                          │
  schedule_triggers() ────────────────┼───> [run_trigger(id1)]
                                      │     [run_trigger(id2)]
                                      │     [run_trigger(id3)]
                                      │                │
                                      │                ▼
                                      │         Worker executes:
                                      │         - Load trigger context
                                      │         - Call handler.poll()
                                      │         - Write to TriggerInbox
                                      │         - Update TriggerState
                                      │
  Every 10s:                          │
  process_all_inboxes() ──────────────┼───> [process_inbox(org1)]
                                      │     [process_inbox(org2)]
                                      │                │
                                      │                ▼
                                      │         Worker executes:
                                      │         - Select pending events
                                      │         - Create agent Tasks
                                      │         - Mark events done
```

**Benefits of This Architecture:**

| Benefit              | Description                                                |
| -------------------- | ---------------------------------------------------------- |
| **Air-Gapped Ready** | No inbound connections required; pure polling model        |
| **Fault Tolerant**   | TriggerInbox provides durable event storage                |
| **Scalable**         | Celery workers can scale horizontally                      |
| **Deduplication**    | `dedupe_key` prevents duplicate event processing           |
| **Backoff**          | Exponential backoff on errors prevents API hammering       |
| **Multi-Tenant**     | Org schema isolation for SaaS deployments                  |
| **Observable**       | AgentTrigger state fields track polling health per trigger |

---

## 8. OAuth Architecture

### 8.1 OAuth Types Overview

We support two OAuth 2.0 flows:

| Type           | Name               | Use Case                                                                 | User Interaction           |
| -------------- | ------------------ | ------------------------------------------------------------------------ | -------------------------- |
| **OAuth2User** | User-Delegated     | Act on behalf of a user (personal Gmail, user's calendar)                | User signs in and consents |
| **OAuth2App**  | Client Credentials | App-only access without user context (mailbox polling, service accounts) | Admin configures once      |

### 8.2 OAuth2User Flow (User-Delegated)

Used when the integration needs to act on behalf of a specific user.

**Examples**: Gmail (personal), Microsoft Graph (user mailbox), Slack (user token)

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           OAuth2User Flow (User-Delegated)                           │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌──────────┐      ┌──────────────┐      ┌──────────────┐      ┌─────────────────────┐
│  User    │      │   Frontend   │      │   Backend    │      │  OAuth Provider     │
│ Browser  │      │  (React App) │      │  (FastAPI)   │      │  (Google/Microsoft) │
└────┬─────┘      └──────┬───────┘      └──────┬───────┘      └──────────┬──────────┘
     │                   │                     │                         │
     │ 1. Click "Connect Gmail"                │                         │
     │──────────────────>│                     │                         │
     │                   │                     │                         │
     │                   │ 2. GET /api/oauth/authorize                   │
     │                   │    ?integration=gmail                         │
     │                   │────────────────────>│                         │
     │                   │                     │                         │
     │                   │                     │ 3. Build authorization URL
     │                   │                     │    with redirect_uri=   │
     │                   │                     │    {APP_URL}/oauth/callback
     │                   │                     │                         │
     │                   │ 4. Return auth_url  │                         │
     │                   │<────────────────────│                         │
     │                   │                     │                         │
     │ 5. Redirect to auth_url                 │                         │
     │<──────────────────│                     │                         │
     │                   │                     │                         │
     │ 6. User signs in & consents             │                         │
     │─────────────────────────────────────────────────────────────────>│
     │                   │                     │                         │
     │ 7. Redirect to {APP_URL}/oauth/callback?code=AUTH_CODE&state=... │
     │<─────────────────────────────────────────────────────────────────│
     │                   │                     │                         │
     │ 8. Frontend receives callback           │                         │
     │──────────────────>│                     │                         │
     │                   │                     │                         │
     │                   │ 9. POST /api/oauth/callback                   │
     │                   │    {code, state}    │                         │
     │                   │────────────────────>│                         │
     │                   │                     │                         │
     │                   │                     │ 10. Exchange code for tokens
     │                   │                     │────────────────────────>│
     │                   │                     │                         │
     │                   │                     │ 11. Return access_token,│
     │                   │                     │     refresh_token       │
     │                   │                     │<────────────────────────│
     │                   │                     │                         │
     │                   │                     │ 12. Encrypt & store tokens
     │                   │                     │     in Connection.encrypted_token
     │                   │                     │                         │
     │                   │ 13. Return success  │                         │
     │                   │<────────────────────│                         │
     │                   │                     │                         │
     │ 14. Show "Connected!"                   │                         │
     │<──────────────────│                     │                         │
     │                   │                     │                         │
```

**Key Points:**

- `redirect_uri` is the web app URL (private IP or domain where app runs)
- Frontend handles the OAuth callback and forwards to backend
- Backend exchanges code for tokens and stores encrypted in `Connection.encrypted_token`
- Refresh tokens are used to get new access tokens when expired

### 8.3 OAuth2App Flow (Client Credentials)

Used when the app accesses resources without user context.

**Examples**: Microsoft Graph (app-only mailbox access), Google Service Account

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         OAuth2App Flow (Client Credentials)                          │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌──────────┐      ┌──────────────┐      ┌──────────────┐      ┌─────────────────────┐
│  Admin   │      │   Frontend   │      │   Backend    │      │  OAuth Provider     │
│          │      │  (React App) │      │  (FastAPI)   │      │  (Azure AD/Google)  │
└────┬─────┘      └──────┬───────┘      └──────┬───────┘      └──────────┬──────────┘
     │                   │                     │                         │
     │ 1. Enter client_id, client_secret, tenant_id                      │
     │──────────────────>│                     │                         │
     │                   │                     │                         │
     │                   │ 2. POST /api/connections                      │
     │                   │    {credentials}    │                         │
     │                   │────────────────────>│                         │
     │                   │                     │                         │
     │                   │                     │ 3. Encrypt credentials  │
     │                   │                     │    Store in Connection  │
     │                   │                     │                         │
     │                   │                     │ 4. Test connection:     │
     │                   │                     │    POST to token_url    │
     │                   │                     │────────────────────────>│
     │                   │                     │                         │
     │                   │                     │ 5. Return access_token  │
     │                   │                     │<────────────────────────│
     │                   │                     │                         │
     │                   │                     │ 6. Validate with test API call
     │                   │                     │────────────────────────>│
     │                   │                     │                         │
     │                   │                     │ 7. Success              │
     │                   │                     │<────────────────────────│
     │                   │                     │                         │
     │                   │ 8. Return connection created                  │
     │                   │<────────────────────│                         │
     │                   │                     │                         │
     │ 9. Show "Connected!"                    │                         │
     │<──────────────────│                     │                         │
     │                   │                     │                         │

RUNTIME (When trigger polls or action executes):

     │                   │                     │                         │
     │                   │                     │ A. Check token expiry   │
     │                   │                     │                         │
     │                   │                     │ B. If expired, POST to  │
     │                   │                     │    token_url (same flow)│
     │                   │                     │────────────────────────>│
     │                   │                     │                         │
     │                   │                     │ C. Get new access_token │
     │                   │                     │<────────────────────────│
     │                   │                     │                         │
     │                   │                     │ D. Make API call with   │
     │                   │                     │    Bearer token         │
     │                   │                     │────────────────────────>│
```

**Key Points:**

- No user interaction after initial setup
- Admin provides app credentials (client_id, client_secret)
- Tokens are short-lived, acquired on-demand using client credentials
- No refresh token - just re-authenticate with credentials

### 8.4 OAuth Configuration in Auth Schemas

```python
# backend/configs/auth_schemas.py

AUTH_SCHEMAS = {
    # =========================================================================
    # OAuth2User - User Delegated (requires user sign-in)
    # =========================================================================
    "gmail_oauth": {
        "auth_type": "OAuth2User",
        "display_name": "Gmail (User)",
        "description": "Access Gmail on behalf of a user",
        "preset": {
            "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scope": "https://mail.google.com/",
            "access_type": "offline",     # Request refresh token
            "prompt": "consent",          # Always show consent screen
        },
        "user_fields": {
            "CLIENT_ID": _field("client_id", "Client ID", "OAuth Client ID from Google Cloud Console"),
            "CLIENT_SECRET": _field("client_secret", "Client Secret", "OAuth Client Secret", sensitive=True),
        },
        "token_fields": ["access_token", "refresh_token", "expires_at", "token_type"],
    },

    "microsoft_graph_user": {
        "auth_type": "OAuth2User",
        "display_name": "Microsoft Graph (User)",
        "description": "Access Microsoft 365 on behalf of a user",
        "preset": {
            "authorization_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send offline_access",
        },
        "user_fields": {
            "CLIENT_ID": _field("client_id", "Client ID", "App registration client ID"),
            "CLIENT_SECRET": _field("client_secret", "Client Secret", "App registration secret", sensitive=True),
            "TENANT_ID": _field("tenant_id", "Tenant ID", "Azure AD tenant ID", default="common"),
        },
        "token_fields": ["access_token", "refresh_token", "expires_at", "token_type"],
    },

    # =========================================================================
    # OAuth2App - Client Credentials (app-only, no user)
    # =========================================================================
    "microsoft_graph_app": {
        "auth_type": "OAuth2App",
        "display_name": "Microsoft Graph (App-Only)",
        "description": "Access Microsoft 365 without user context (mailbox polling, etc.)",
        "preset": {
            "token_url": "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        "user_fields": {
            "CLIENT_ID": _field("client_id", "Client ID", "App registration client ID"),
            "CLIENT_SECRET": _field("client_secret", "Client Secret", "App registration secret", sensitive=True),
            "TENANT_ID": _field("tenant_id", "Tenant ID", "Azure AD tenant ID"),
        },
        # No token_fields - tokens acquired on-demand, not stored long-term
    },

    "google_service_account": {
        "auth_type": "OAuth2App",
        "display_name": "Google Service Account",
        "description": "Server-to-server access using service account",
        "preset": {
            "token_url": "https://oauth2.googleapis.com/token",
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        },
        "user_fields": {
            "SERVICE_ACCOUNT_JSON": _field(
                "service_account_json", "Service Account JSON",
                "Full JSON key file content", field_type=FieldType.TEXTAREA, sensitive=True
            ),
            "DELEGATED_USER": _field(
                "delegated_user", "Delegated User Email",
                "Email to impersonate (for domain-wide delegation)", required=False
            ),
        },
    },
}
```

### 8.5 OAuth Handlers Implementation

```python
# backend/integrations/auth/oauth2_user.py
"""OAuth2User - User-delegated flow with authorization code + refresh tokens."""

import httpx
from datetime import datetime
from urllib.parse import urlencode
from typing import Dict, Any, Optional

from backend.integrations.auth.base import BaseAuthHandler
from backend.core.config import settings


class OAuth2UserHandler(BaseAuthHandler):
    """
    Handles OAuth2 User-Delegated flow.

    Flow:
    1. build_authorization_url() - Generate URL for user to authorize
    2. exchange_code_for_tokens() - Exchange auth code for tokens
    3. get_auth_headers() - Get Bearer header (refreshes if needed)
    """

    def build_authorization_url(self, state: str) -> str:
        """
        Build the authorization URL for user to visit.

        Args:
            state: Random string to prevent CSRF, stored in session
        """
        auth_url = self.preset["authorization_url"]

        # Replace placeholders like {tenant_id}
        for key, value in self.credentials.items():
            auth_url = auth_url.replace(f"{{{key}}}", str(value))

        params = {
            "client_id": self.credentials["client_id"],
            "response_type": "code",
            "redirect_uri": f"{settings.APP_URL}/oauth/callback",
            "scope": self.preset.get("scope", ""),
            "state": state,
            "access_type": self.preset.get("access_type", "offline"),
        }

        if self.preset.get("prompt"):
            params["prompt"] = self.preset["prompt"]

        return f"{auth_url}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token data dict with access_token, refresh_token, expires_at
        """
        token_url = self.preset["token_url"]

        # Replace placeholders
        for key, value in self.credentials.items():
            token_url = token_url.replace(f"{{{key}}}", str(value))

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.credentials["client_id"],
                    "client_secret": self.credentials["client_secret"],
                    "code": code,
                    "redirect_uri": f"{settings.APP_URL}/oauth/callback",
                },
            )
            response.raise_for_status()
            data = response.json()

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_at": datetime.utcnow().timestamp() + data.get("expires_in", 3600),
            "token_type": data.get("token_type", "Bearer"),
        }

    async def get_auth_headers(self) -> Dict[str, str]:
        """Get Bearer header, refreshing token if expired."""
        if self._is_expired():
            await self._refresh_token()
        return {"Authorization": f"Bearer {self.token_data['access_token']}"}

    async def refresh_if_needed(self) -> Optional[Dict]:
        """Refresh token if expired. Returns new token_data or None if not needed."""
        if self._is_expired():
            await self._refresh_token()
            return self.token_data
        return None

    async def _refresh_token(self):
        """Use refresh token to get new access token."""
        if not self.token_data.get("refresh_token"):
            raise ValueError("No refresh token available - user must re-authorize")

        token_url = self.preset["token_url"]
        for key, value in self.credentials.items():
            token_url = token_url.replace(f"{{{key}}}", str(value))

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.credentials["client_id"],
                    "client_secret": self.credentials["client_secret"],
                    "refresh_token": self.token_data["refresh_token"],
                },
            )
            response.raise_for_status()
            data = response.json()

        self.token_data["access_token"] = data["access_token"]
        self.token_data["expires_at"] = datetime.utcnow().timestamp() + data.get("expires_in", 3600)
        # Some providers return new refresh token
        if data.get("refresh_token"):
            self.token_data["refresh_token"] = data["refresh_token"]

    def _is_expired(self) -> bool:
        expires_at = self.token_data.get("expires_at", 0)
        return datetime.utcnow().timestamp() > expires_at - 300  # 5 min buffer

    async def test_credentials(self) -> bool:
        """For OAuth2User, credentials are valid if we have a refresh token."""
        return bool(self.token_data.get("refresh_token"))


# backend/integrations/auth/oauth2_app.py
"""OAuth2App - Client credentials flow (app-only, no user context)."""

import httpx
from datetime import datetime
from typing import Dict, Any

from backend.integrations.auth.base import BaseAuthHandler


class OAuth2AppHandler(BaseAuthHandler):
    """
    Handles OAuth2 App-level flow (client credentials grant).

    No user interaction - app authenticates directly with client credentials.
    Tokens are short-lived and acquired on-demand.
    """

    async def get_auth_headers(self) -> Dict[str, str]:
        """Get Bearer header, acquiring token if needed or expired."""
        if not self.token_data.get("access_token") or self._is_expired():
            await self._acquire_token()
        return {"Authorization": f"Bearer {self.token_data['access_token']}"}

    async def test_credentials(self) -> bool:
        """Test by acquiring a token."""
        try:
            await self._acquire_token()
            return True
        except Exception:
            return False

    async def _acquire_token(self):
        """Acquire access token using client credentials."""
        token_url = self.preset["token_url"]

        # Replace placeholders like {tenant_id}
        for key, value in self.credentials.items():
            token_url = token_url.replace(f"{{{key}}}", str(value))

        # Build request based on grant type
        grant_type = self.preset.get("grant_type", "client_credentials")

        if grant_type == "client_credentials":
            data = {
                "grant_type": "client_credentials",
                "client_id": self.credentials["client_id"],
                "client_secret": self.credentials["client_secret"],
                "scope": self.preset.get("scope", ""),
            }
        elif grant_type == "urn:ietf:params:oauth:grant-type:jwt-bearer":
            # Google Service Account - build JWT assertion
            data = {
                "grant_type": grant_type,
                "assertion": self._build_jwt_assertion(),
            }
        else:
            raise ValueError(f"Unsupported grant type: {grant_type}")

        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()

        self.token_data = {
            "access_token": token_data["access_token"],
            "expires_at": datetime.utcnow().timestamp() + token_data.get("expires_in", 3600),
            "token_type": token_data.get("token_type", "Bearer"),
        }

    def _build_jwt_assertion(self) -> str:
        """Build JWT assertion for Google Service Account auth."""
        import json
        import jwt
        from datetime import datetime, timedelta

        service_account = json.loads(self.credentials["service_account_json"])

        now = datetime.utcnow()
        payload = {
            "iss": service_account["client_email"],
            "scope": self.preset.get("scope", ""),
            "aud": self.preset["token_url"],
            "iat": now,
            "exp": now + timedelta(hours=1),
        }

        # Add delegated user if specified
        if self.credentials.get("delegated_user"):
            payload["sub"] = self.credentials["delegated_user"]

        return jwt.encode(
            payload,
            service_account["private_key"],
            algorithm="RS256",
        )

    def _is_expired(self) -> bool:
        expires_at = self.token_data.get("expires_at", 0)
        return datetime.utcnow().timestamp() > expires_at - 300  # 5 min buffer
```

### 8.6 OAuth API Endpoints

```python
# backend/routers/oauth.py
"""OAuth flow endpoints."""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import secrets

from backend.configs.auth_schemas import AUTH_SCHEMAS
from backend.integrations.auth import get_auth_handler
from backend.models.connection import Connection
from backend.core.security import get_current_user

router = APIRouter(prefix="/oauth", tags=["oauth"])


class OAuthInitResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str
    connection_id: str  # Connection being authorized


@router.get("/authorize/{connection_id}", response_model=OAuthInitResponse)
async def initiate_oauth(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Start OAuth flow for a connection.

    Returns authorization URL for frontend to redirect user.
    """
    connection = db.query(Connection).filter(Connection.id == connection_id).first()
    if not connection:
        raise HTTPException(404, "Connection not found")

    auth_schema = AUTH_SCHEMAS.get(connection.auth_schema_key)
    if not auth_schema or auth_schema.get("auth_type") != "OAuth2User":
        raise HTTPException(400, "Connection does not use OAuth2User flow")

    # Get decrypted credentials
    credentials = decrypt_credentials(connection.encrypted_credentials)

    # Create handler and build auth URL
    handler = get_auth_handler(auth_schema, credentials)
    state = secrets.token_urlsafe(32)

    # Store state in session/cache for validation
    await cache.set(f"oauth_state:{state}", connection_id, ttl=600)

    return OAuthInitResponse(
        authorization_url=handler.build_authorization_url(state),
        state=state,
    )


@router.post("/callback")
async def oauth_callback(
    request: OAuthCallbackRequest,
    db: Session = Depends(get_db),
):
    """
    Handle OAuth callback - exchange code for tokens.

    Called by frontend after user authorizes.
    """
    # Validate state
    stored_connection_id = await cache.get(f"oauth_state:{request.state}")
    if not stored_connection_id or stored_connection_id != request.connection_id:
        raise HTTPException(400, "Invalid state parameter")

    await cache.delete(f"oauth_state:{request.state}")

    # Get connection
    connection = db.query(Connection).filter(Connection.id == request.connection_id).first()
    if not connection:
        raise HTTPException(404, "Connection not found")

    auth_schema = AUTH_SCHEMAS.get(connection.auth_schema_key)
    credentials = decrypt_credentials(connection.encrypted_credentials)

    # Exchange code for tokens
    handler = get_auth_handler(auth_schema, credentials)
    token_data = await handler.exchange_code_for_tokens(request.code)

    # Store encrypted tokens
    connection.encrypted_token = encrypt_credentials(token_data)
    connection.is_valid = True
    db.commit()

    return {"status": "success", "message": "OAuth authorization complete"}
```

### 8.7 Redirect URI Configuration

For OAuth2User flow, the redirect URI must be registered with each OAuth provider.

**Configuration:**

```python
# backend/core/config.py
class Settings:
    APP_URL: str = os.getenv("APP_URL", "http://localhost:3000")

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.APP_URL}/oauth/callback"
```

**Provider Registration:**

| Provider                  | Redirect URI to Register   |
| ------------------------- | -------------------------- |
| Google Cloud Console      | `{APP_URL}/oauth/callback` |
| Azure AD App Registration | `{APP_URL}/oauth/callback` |
| Slack App Settings        | `{APP_URL}/oauth/callback` |

**Example values:**

- Development: `http://localhost:3000/oauth/callback`
- Private network: `http://192.168.1.100:3000/oauth/callback`
- Custom domain: `https://assistcx.company.local/oauth/callback`

**Frontend Callback Handler:**

```typescript
// frontend/src/pages/oauth/callback.tsx
import { useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';

export function OAuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const connectionId = sessionStorage.getItem('oauth_connection_id');

    if (code && state && connectionId) {
      // Send to backend
      fetch('/api/oauth/callback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, state, connection_id: connectionId }),
      })
        .then(() => navigate('/connections?success=true'))
        .catch(() => navigate('/connections?error=oauth_failed'));
    }
  }, []);

  return <div>Completing authorization...</div>;
}
```

---

## 9. Implementation Examples

This section shows complete implementations of three integrations following the established patterns.

### 9.1 Gmail Integration

Gmail integration using OAuth2 user-delegated flow and Google's Gmail API.

#### 9.1.1 Client (`integrations/gmail/client.py`)

```python
"""Gmail API HTTP client with OAuth2 authentication."""

import httpx
from typing import Dict, Any, Optional
from backend.models import Connection
from backend.integrations.auth import get_auth_handler
from backend.configs.auth_schemas import AUTH_SCHEMAS
from backend.utils.crypto_utils import decrypt_credentials

# Constants
GMAIL_BASE_URL = "https://gmail.googleapis.com/gmail/v1"
GMAIL_ENDPOINTS = {
    "messages": "/users/me/messages",
    "send": "/users/me/messages/send",
    "history": "/users/me/history",
    "profile": "/users/me/profile",
}


class GmailClient:
    """HTTP client for Gmail API."""

    def __init__(self, connection: Connection):
        self.connection = connection
        self.base_url = GMAIL_BASE_URL

        # Decrypt and setup auth
        credentials = decrypt_credentials(connection.encrypted_token)
        auth_schema = AUTH_SCHEMAS[connection.auth_schema_key]
        self.auth_handler = get_auth_handler(auth_schema, credentials, credentials.get("token_data"))

    async def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make authenticated Gmail API request."""
        headers = await self.auth_handler.get_auth_headers()
        headers["Content-Type"] = "application/json"

        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params
            )
            response.raise_for_status()
            return response.json()

    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """GET request."""
        return await self.request("GET", endpoint, params=params)

    async def post(self, endpoint: str, data: Dict) -> Dict:
        """POST request."""
        return await self.request("POST", endpoint, data=data)
```

#### 9.1.2 Actions (`integrations/gmail/actions.py`)

```python
"""Action handlers for Gmail integration."""

from typing import Dict, Any
from sqlalchemy.orm import Session
import base64
from email.mime.text import MIMEText
from backend.models import Connection
from backend.integrations.gmail.client import GmailClient, GMAIL_ENDPOINTS


class GmailActions:
    """Gmail action handlers."""

    def __init__(self, db: Session):
        self.db = db

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = None,
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send email via Gmail.

        Handler for: gmail_send_email tool
        """
        connection = self._get_connection(tool_runtime)
        client = GmailClient(connection)

        # Build MIME message
        message = self._build_mime_message(to, subject, body, cc)

        # Send via API
        response = await client.post(
            GMAIL_ENDPOINTS["send"],
            {"raw": message}
        )

        return {
            "success": True,
            "message_id": response["id"],
            "thread_id": response.get("threadId")
        }

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create draft email."""
        connection = self._get_connection(tool_runtime)
        client = GmailClient(connection)

        message = self._build_mime_message(to, subject, body)

        response = await client.post(
            "/users/me/drafts",
            {"message": {"raw": message}}
        )

        return {
            "success": True,
            "draft_id": response["id"],
            "message_id": response["message"]["id"]
        }

    # === Helper Functions ===

    def _get_connection(self, tool_runtime: Dict) -> Connection:
        """Helper: Get connection from runtime."""
        connection_id = tool_runtime.get("connection_id")
        if not connection_id:
            raise ValueError("connection_id required")
        return self.db.query(Connection).get(connection_id)

    def _build_mime_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = None
    ) -> str:
        """
        Helper: Build base64-encoded MIME message for Gmail API.

        Pattern: Small transformation helpers stay in same file.
        """
        message = MIMEText(body)
        message["To"] = to
        message["Subject"] = subject
        if cc:
            message["Cc"] = cc

        # Base64url encode
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return raw
```

#### 9.1.3 Triggers (`integrations/gmail/triggers.py`)

```python
"""Trigger handlers for Gmail integration."""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.models import Connection
from backend.integrations.gmail.client import GmailClient, GMAIL_ENDPOINTS


class GmailTriggers:
    """Gmail trigger handlers."""

    def __init__(self, db: Session):
        self.db = db

    def poll_new_emails(
        self,
        cursor: str,
        config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Poll for new emails using History API.

        Handler for: gmail_new_email trigger

        Uses Gmail History API for efficient incremental sync.
        Cursor stores historyId from last poll.
        """
        connection = self._get_connection(context)
        client = GmailClient(connection)

        # Get starting historyId
        if cursor:
            start_history_id = cursor
        else:
            # First poll - get current historyId
            profile = await client.get(GMAIL_ENDPOINTS["profile"])
            start_history_id = profile["historyId"]

        # Fetch history
        params = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded"
        }

        # Apply label filter from config
        if config.get("label_ids"):
            params["labelId"] = config["label_ids"]

        response = await client.get(GMAIL_ENDPOINTS["history"], params=params)

        # Extract new messages
        messages = []
        for history_record in response.get("history", []):
            for message_added in history_record.get("messagesAdded", []):
                messages.append(message_added["message"])

        # Normalize to events
        events = [self._normalize_message(msg) for msg in messages]

        # New cursor is latest historyId
        new_cursor = response.get("historyId", start_history_id)

        return {
            "events": events,
            "cursor": new_cursor,
            "has_more": False,
            "polling_interval": 300  # 5 minutes
        }

    # === Helper Functions ===

    def _get_connection(self, context: Dict) -> Connection:
        """Helper: Get connection from context."""
        connection_id = context.get("connection_id")
        return self.db.query(Connection).get(connection_id)

    def _normalize_message(self, message: Dict) -> Dict:
        """
        Helper: Transform Gmail message to normalized event format.

        Pattern: Event normalization helpers stay inline.
        """
        # Extract headers
        headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}

        return {
            "event_id": message["id"],
            "event_type": "email_received",
            "occurred_at": message.get("internalDate"),
            "data": {
                "message_id": message["id"],
                "thread_id": message.get("threadId"),
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "snippet": message.get("snippet", ""),
                "labels": message.get("labelIds", [])
            }
        }
```

---

### 9.2 Outlook Integration (Microsoft Graph)

Outlook integration using Microsoft Graph API with OAuth2 app-level flow.

#### 9.2.1 Client (`integrations/outlook/client.py`)

```python
"""Microsoft Graph API HTTP client for Outlook."""

import httpx
from typing import Dict, Any, Optional
from backend.models import Connection
from backend.integrations.auth import get_auth_handler
from backend.configs.auth_schemas import AUTH_SCHEMAS
from backend.utils.crypto_utils import decrypt_credentials

# Constants
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_ENDPOINTS = {
    "messages": "/me/messages",
    "send_mail": "/me/sendMail",
    "delta": "/me/messages/delta",
}


class GraphClient:
    """HTTP client for Microsoft Graph API."""

    def __init__(self, connection: Connection):
        self.connection = connection
        self.base_url = GRAPH_BASE_URL

        credentials = decrypt_credentials(connection.encrypted_token)
        auth_schema = AUTH_SCHEMAS[connection.auth_schema_key]
        self.auth_handler = get_auth_handler(auth_schema, credentials, credentials.get("token_data"))

    async def request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make authenticated Graph API request."""
        headers = await self.auth_handler.get_auth_headers()
        headers["Content-Type"] = "application/json"

        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise RateLimitError(f"Rate limited, retry after {retry_after}s")

            response.raise_for_status()
            return response.json()

    async def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        return await self.request("GET", endpoint, params=params)

    async def post(self, endpoint: str, data: Dict) -> Dict:
        return await self.request("POST", endpoint, data=data)
```

#### 9.2.2 Actions (`integrations/outlook/actions.py`)

```python
"""Action handlers for Outlook integration."""

from typing import Dict, Any
from sqlalchemy.orm import Session
from backend.models import Connection
from backend.integrations.outlook.client import GraphClient, GRAPH_ENDPOINTS


class OutlookActions:
    """Outlook action handlers."""

    def __init__(self, db: Session):
        self.db = db

    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = None,
        importance: str = "normal",
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Send email via Outlook.

        Handler for: outlook_send_email tool
        """
        connection = self._get_connection(tool_runtime)
        client = GraphClient(connection)

        # Build payload
        payload = self._build_send_email_payload(to, subject, body, cc, importance)

        # Send
        response = await client.post(GRAPH_ENDPOINTS["send_mail"], payload)

        return {
            "success": True,
            "message": "Email sent successfully"
        }

    def move_message(
        self,
        message_id: str,
        destination_folder: str,
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Move email to different folder."""
        connection = self._get_connection(tool_runtime)
        client = GraphClient(connection)

        response = await client.post(
            f"/me/messages/{message_id}/move",
            {"destinationId": destination_folder}
        )

        return {
            "success": True,
            "message_id": response["id"],
            "new_folder": destination_folder
        }

    # === Helper Functions ===

    def _get_connection(self, tool_runtime: Dict) -> Connection:
        connection_id = tool_runtime.get("connection_id")
        if not connection_id:
            raise ValueError("connection_id required")
        return self.db.query(Connection).get(connection_id)

    def _build_send_email_payload(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = None,
        importance: str = "normal"
    ) -> Dict:
        """Helper: Build Graph API sendMail payload."""
        to_recipients = [
            {"emailAddress": {"address": addr.strip()}}
            for addr in to.split(",") if addr.strip()
        ]

        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML" if "<" in body else "Text",
                    "content": body
                },
                "toRecipients": to_recipients,
                "importance": importance
            }
        }

        if cc:
            payload["message"]["ccRecipients"] = [
                {"emailAddress": {"address": addr.strip()}}
                for addr in cc.split(",") if addr.strip()
            ]

        return payload
```

#### 9.2.3 Triggers (`integrations/outlook/triggers.py`)

```python
"""Trigger handlers for Outlook integration."""

from typing import Dict, Any
from sqlalchemy.orm import Session
from backend.models import Connection
from backend.integrations.outlook.client import GraphClient, GRAPH_ENDPOINTS


class OutlookTriggers:
    """Outlook trigger handlers."""

    def __init__(self, db: Session):
        self.db = db

    def poll_new_emails(
        self,
        cursor: str,
        config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Poll for new emails using delta query.

        Handler for: outlook_new_email trigger

        Uses Graph delta query for efficient incremental sync.
        Cursor stores @odata.deltaLink from previous poll.
        """
        connection = self._get_connection(context)
        client = GraphClient(connection)

        # Use delta endpoint
        if cursor:
            # Continue from delta link
            response = await client.get(cursor)
        else:
            # First poll - initialize delta
            params = {
                "$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments",
                "$top": 50
            }

            # Apply folder filter from config
            folder = config.get("folder", "inbox")
            endpoint = f"/me/mailFolders/{folder}/messages/delta"

            response = await client.get(endpoint, params=params)

        # Extract messages
        messages = response.get("value", [])

        # Normalize to events
        events = [self._normalize_message(msg) for msg in messages]

        # Get new cursor
        new_cursor = response.get("@odata.deltaLink") or response.get("@odata.nextLink")

        return {
            "events": events,
            "cursor": new_cursor,
            "has_more": "@odata.nextLink" in response,
            "polling_interval": 300 if events else 600
        }

    # === Helper Functions ===

    def _get_connection(self, context: Dict) -> Connection:
        connection_id = context.get("connection_id")
        return self.db.query(Connection).get(connection_id)

    def _normalize_message(self, message: Dict) -> Dict:
        """Helper: Transform Graph message to normalized event."""
        return {
            "event_id": message["id"],
            "event_type": "email_received",
            "occurred_at": message["receivedDateTime"],
            "data": {
                "message_id": message["id"],
                "subject": message.get("subject", ""),
                "from_email": message["from"]["emailAddress"]["address"],
                "from_name": message["from"]["emailAddress"].get("name", ""),
                "body_preview": message.get("bodyPreview", ""),
                "received_at": message["receivedDateTime"],
                "has_attachments": message.get("hasAttachments", False)
            }
        }
```

---

### 9.3 AWS S3 Integration

S3 integration using AWS SDK (boto3) with AWS SigV4 authentication.

#### 9.3.1 Client (`integrations/aws/client.py`)

```python
"""AWS S3 client using boto3."""

import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional
from backend.models import Connection
from backend.utils.crypto_utils import decrypt_credentials


class S3Client:
    """Boto3-based S3 client."""

    def __init__(self, connection: Connection):
        self.connection = connection

        # Decrypt credentials
        credentials = decrypt_credentials(connection.encrypted_token)

        # Create boto3 session
        self.session = boto3.Session(
            aws_access_key_id=credentials["aws_access_key_id"],
            aws_secret_access_key=credentials["aws_secret_access_key"],
            aws_session_token=credentials.get("aws_session_token"),
            region_name=connection.connection_config.get("region", "us-east-1")
        )

        self.s3 = self.session.client("s3")

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        continuation_token: str = None
    ) -> Dict[str, Any]:
        """List objects in bucket."""
        params = {"Bucket": bucket, "Prefix": prefix}

        if continuation_token:
            params["ContinuationToken"] = continuation_token

        return self.s3.list_objects_v2(**params)

    def upload_file(
        self,
        bucket: str,
        key: str,
        file_content: bytes,
        content_type: str = "application/octet-stream"
    ) -> Dict[str, Any]:
        """Upload file to S3."""
        response = self.s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=file_content,
            ContentType=content_type
        )

        return {
            "etag": response["ETag"],
            "version_id": response.get("VersionId")
        }

    def download_file(self, bucket: str, key: str) -> bytes:
        """Download file from S3."""
        response = self.s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()
```

#### 9.3.2 Actions (`integrations/aws/actions.py`)

```python
"""Action handlers for AWS S3 integration."""

from typing import Dict, Any
from sqlalchemy.orm import Session
import base64
from backend.models import Connection
from backend.integrations.aws.client import S3Client


class AwsS3Actions:
    """S3 action handlers."""

    def __init__(self, db: Session):
        self.db = db

    def upload_file(
        self,
        bucket: str,
        key: str,
        content_base64: str,
        content_type: str = "application/octet-stream",
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Upload file to S3 bucket.

        Handler for: aws_s3_upload tool
        """
        connection = self._get_connection(tool_runtime)
        client = S3Client(connection)

        # Decode base64 content
        file_content = base64.b64decode(content_base64)

        # Upload
        result = client.upload_file(bucket, key, file_content, content_type)

        return {
            "success": True,
            "bucket": bucket,
            "key": key,
            "etag": result["etag"],
            "size": len(file_content)
        }

    def download_file(
        self,
        bucket: str,
        key: str,
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Download file from S3 bucket."""
        connection = self._get_connection(tool_runtime)
        client = S3Client(connection)

        # Download
        content = client.download_file(bucket, key)

        # Encode to base64 for transport
        content_base64 = base64.b64encode(content).decode()

        return {
            "success": True,
            "bucket": bucket,
            "key": key,
            "content_base64": content_base64,
            "size": len(content)
        }

    def list_objects(
        self,
        bucket: str,
        prefix: str = "",
        max_keys: int = 100,
        tool_runtime: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """List objects in S3 bucket."""
        connection = self._get_connection(tool_runtime)
        client = S3Client(connection)

        response = client.list_objects(bucket, prefix)

        objects = [
            {
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
                "etag": obj["ETag"]
            }
            for obj in response.get("Contents", [])[:max_keys]
        ]

        return {
            "success": True,
            "bucket": bucket,
            "prefix": prefix,
            "objects": objects,
            "count": len(objects)
        }

    # === Helper Functions ===

    def _get_connection(self, tool_runtime: Dict) -> Connection:
        connection_id = tool_runtime.get("connection_id")
        if not connection_id:
            raise ValueError("connection_id required")
        return self.db.query(Connection).get(connection_id)
```

#### 9.3.3 Triggers (`integrations/aws/triggers.py`)

```python
"""Trigger handlers for AWS S3 integration."""

from typing import Dict, Any
from sqlalchemy.orm import Session
from backend.models import Connection
from backend.integrations.aws.client import S3Client


class AwsS3Triggers:
    """S3 trigger handlers."""

    def __init__(self, db: Session):
        self.db = db

    def poll_new_objects(
        self,
        cursor: str,
        config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Poll for new S3 objects.

        Handler for: aws_s3_new_object trigger

        Uses list_objects_v2 with continuation token.
        Cursor stores last seen object key for watermark-based polling.
        """
        connection = self._get_connection(context)
        client = S3Client(connection)

        bucket = config["bucket"]
        prefix = config.get("prefix", "")
        suffix = config.get("suffix", "")

        # List objects
        response = client.list_objects(bucket, prefix)

        # Filter new objects (after cursor)
        all_objects = response.get("Contents", [])

        if cursor:
            # Only include objects modified after cursor timestamp
            new_objects = [
                obj for obj in all_objects
                if obj["LastModified"].isoformat() > cursor
            ]
        else:
            new_objects = all_objects

        # Apply suffix filter
        if suffix:
            new_objects = [
                obj for obj in new_objects
                if obj["Key"].endswith(suffix)
            ]

        # Normalize to events
        events = [self._normalize_object(obj, bucket) for obj in new_objects]

        # New cursor is latest modification time
        if new_objects:
            new_cursor = max(obj["LastModified"].isoformat() for obj in new_objects)
        else:
            new_cursor = cursor

        return {
            "events": events,
            "cursor": new_cursor,
            "has_more": response.get("IsTruncated", False),
            "polling_interval": 600  # 10 minutes
        }

    # === Helper Functions ===

    def _get_connection(self, context: Dict) -> Connection:
        connection_id = context.get("connection_id")
        return self.db.query(Connection).get(connection_id)

    def _normalize_object(self, s3_object: Dict, bucket: str) -> Dict:
        """Helper: Transform S3 object to normalized event."""
        return {
            "event_id": s3_object["Key"],
            "event_type": "object_created",
            "occurred_at": s3_object["LastModified"].isoformat(),
            "data": {
                "bucket": bucket,
                "key": s3_object["Key"],
                "size": s3_object["Size"],
                "etag": s3_object["ETag"].strip('"'),
                "last_modified": s3_object["LastModified"].isoformat(),
                "storage_class": s3_object.get("StorageClass", "STANDARD")
            }
        }
```

---

### 9.4 Key Patterns Demonstrated

These examples show:

1. **File Structure**: Separate `client.py`, `actions.py`, `triggers.py` files
2. **Auth Integration**: Using centralized auth handlers via `get_auth_handler()`
3. **Inline Helpers**: Small helper functions in same file (e.g., `_normalize_message`, `_build_send_email_payload`)
4. **Standard Signatures**: All handlers follow `def method(..., tool_runtime: Dict)`
5. **Connection Resolution**: From `tool_runtime` context
6. **Event Normalization**: Consistent event structure with `event_id`, `event_type`, `occurred_at`, `data`
7. **Cursor Management**: Different strategies (historyId, deltaLink, timestamp watermark)
8. **Error Handling**: Proper exception raising with clear messages

---

## 10. Appendix

### 10.1 Celery Polling Architecture

```python
# backend/integrations/tasks.py
from celery import shared_task
from datetime import datetime, timedelta

from backend.db.session import SessionLocal
from backend.models.agent_trigger import AgentTrigger
from backend.models.trigger_inbox import TriggerInbox
from backend.integrations.core.handler_loader import resolve_handler
from backend.integrations.core.dedupe import build_dedupe_key
from backend.integrations.core.encryption import decrypt_credentials


@shared_task(bind=True, max_retries=5)
def poll_agent_trigger(self, agent_trigger_id: str):
    db = SessionLocal()
    try:
        agent_trigger = db.query(AgentTrigger).filter(AgentTrigger.id == agent_trigger_id).first()
        if not agent_trigger or not agent_trigger.is_enabled:
            return

        trigger_def = agent_trigger.trigger
        connection = agent_trigger.connection

        handler = resolve_handler(trigger_def.handler)
        result = handler(
            cursor=agent_trigger.cursor,
            config=agent_trigger.config,
            credentials=decrypt_credentials(connection.encrypted_credentials),
            connection_config=connection.connection_config,
            context={"agent_trigger_id": agent_trigger_id},
        )

        for event in result.get("events", []):
            db.add(TriggerInbox(
                agent_trigger_id=agent_trigger_id,
                event_type=event["event_type"],
                occurred_at=event.get("occurred_at"),
                dedupe_key=build_dedupe_key(event, agent_trigger, connection),
                payload=event.get("payload", {}),  # Normalized data only
                metadata={
                    "connection_id": str(connection.id),
                    "connection_name": connection.name,
                    "integration_key": trigger_def.integration.key,
                    "trigger_slug": trigger_def.slug,
                },
            ))

        # Update polling state
        agent_trigger.cursor = result.get("cursor")
        agent_trigger.last_polled_at = datetime.utcnow()
        agent_trigger.error_count = 0
        agent_trigger.backoff_until = result.get("backoff_until")
        agent_trigger.next_run_at = result.get("next_run_at")
        agent_trigger.locked_until = None  # Release lock
        db.commit()

    except Exception as e:
        agent_trigger.error_count += 1
        agent_trigger.last_error = str(e)
        agent_trigger.locked_until = None  # Release lock
        db.commit()
        # Exponential backoff on retry
        raise self.retry(countdown=min(60 * (2 ** agent_trigger.error_count), 3600))
    finally:
        db.close()


def schedule_due_triggers():
    """Called by Celery beat every 30-60 seconds."""
    db = SessionLocal()
    due_triggers = (
        db.query(AgentTrigger)
        .filter(AgentTrigger.is_enabled == True)
        .filter(AgentTrigger.next_run_at <= datetime.utcnow())
        .filter((AgentTrigger.locked_until == None) | (AgentTrigger.locked_until <= datetime.utcnow()))
        .with_for_update(skip_locked=True)
        .all()
    )

    for agent_trigger in due_triggers:
        agent_trigger.locked_until = datetime.utcnow() + timedelta(minutes=5)
        db.commit()
        poll_agent_trigger.delay(str(agent_trigger.id))

    db.close()
```

### 10.2 Air-Gapped OAuth Strategy

```python
# backend/integrations/auth/oauth2_user.py
"""
Air-gapped OAuth2 device flow implementation.
Supports Google, Microsoft, GitHub, Slack without callback URLs.
"""

AIR_GAPPED_MODE = os.getenv("AIR_GAPPED", "true").lower() == "true"

async def initiate_oauth_flow(integration_key: str, auth_schema_key: str) -> dict:
    """Start OAuth flow - returns device code for air-gapped, redirect URL otherwise."""

    schema = get_auth_schema(auth_schema_key)

    if AIR_GAPPED_MODE:
        # Device code flow
        device_code_url = schema['preset'].get('device_code_url')
        if not device_code_url:
            raise ValueError(f"Device flow not supported for {auth_schema_key}")

        # Request device code from provider
        response = await httpx.post(device_code_url, data={
            'client_id': schema['preset']['client_id'],
            'scope': schema['preset']['scope'],
        })

        return {
            'flow_type': 'device_code',
            'device_code': response.json()['device_code'],
            'user_code': response.json()['user_code'],
            'verification_url': response.json()['verification_uri'],
            'expires_in': response.json()['expires_in'],
        }
    else:
        # Standard redirect flow
        return {
            'flow_type': 'redirect',
            'authorization_url': build_auth_url(schema),
        }
```

### 10.3 Recommended Built-in Integrations (MVP)

| Priority | Integration       | Auth Type           | Triggers | Actions |
| -------- | ----------------- | ------------------- | -------- | ------- |
| 1        | Gmail             | OAuth2User          | Yes      | Yes     |
| 2        | Microsoft Outlook | OAuth2App/User      | Yes      | Yes     |
| 3        | Slack             | OAuth2User / Bearer | Yes      | Yes     |
| 4        | AWS S3            | AWS SigV4           | Yes      | Yes     |
| 5        | OpenAI            | API Key             | No       | Yes     |
| 6        | Anthropic         | API Key             | No       | Yes     |
| 7        | SharePoint        | OAuth2App           | Yes      | Yes     |
| 8        | Custom API        | Multiple            | No       | Yes     |

### 10.4 Dependencies

```
# requirements.txt additions
cryptography>=41.0.0      # Fernet encryption
msal>=1.24.0              # Microsoft auth
google-auth>=2.23.0       # Google OAuth
google-auth-oauthlib>=1.0.0
google-api-python-client>=2.100.0
boto3>=1.28.0             # AWS SDK
httpx>=0.25.0             # Async HTTP client
prance>=23.6.0            # OpenAPI parsing (for custom integrations)
```
