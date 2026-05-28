# Integration Framework: Database Models

This document defines the complete database schema for the AssistCX integration framework, including SQLAlchemy 2.0 models, relationships, and helper utilities.

---

## Table of Contents

1. [Schema Overview](#1-schema-overview)
2. [Connection Model](#2-connection-model)
3. [TaskSource Model](#3-tasksource-model)
4. [EventInbox Model](#4-eventinbox-model)
5. [AgentTool Model](#5-agenttool-model)
6. [Credential Encryption](#6-credential-encryption)
7. [Database Indexes](#7-database-indexes)
8. [Relationships Diagram](#8-relationships-diagram)

---

## 1. Schema Overview

The integration framework uses 4 core tables:

| Table          | Purpose                                               | Key Relationships             |
| -------------- | ----------------------------------------------------- | ----------------------------- |
| `connections`  | Authenticated credentials for an integration instance | → task_sources, → agent_tools |
| `task_sources` | Configured trigger instances (inbound event sources)  | ← connections, ← agents       |
| `event_inbox`  | Intermediate event storage before agent routing       | ← task_sources                |
| `agent_tools`  | Tool bindings (outbound action capabilities)          | ← connections, ← agents       |

**Note:** Integration metadata (provider names, icons, capabilities) is stored in Python registries (`ALL_INTEGRATIONS`), not in the database. This eliminates duplication and sync issues. The `provider_key` field validates against the registry at runtime.

---

## 2. Connection Model

Authenticated link to an external system. One Connection can be shared across multiple TaskSources and AgentTools.

### Table Schema

| Field                   | Type             | Description                                                                              |
| ----------------------- | ---------------- | ---------------------------------------------------------------------------------------- |
| `id`                    | uuid             | Primary key                                                                              |
| `created_by`            | uuid / null      | FK → User who created this Connection (null for system/admin-level connections)          |
| `name`                  | string(128)      | Display name (e.g., "Finance Team AWS", "Support Outlook")                               |
| `provider_key`          | string(64)       | Provider identifier (validated against ALL_INTEGRATIONS registry)                        |
| `auth_schema_key`       | string(64)       | References auth schema registry entry (e.g., `msft.oauth2.app_only`)                     |
| `encrypted_credentials` | text             | Fernet-encrypted user-provided credentials (client_id, client_secret, api_keys, etc.)    |
| `encrypted_token`       | text / null      | Fernet-encrypted OAuth tokens (access_token, refresh_token, expires_at)                  |
| `connection_config`     | jsonb            | Non-sensitive provider-specific config (region, tenant_id, instance_url, default_bucket) |
| `metadata`              | jsonb            | Operational context: validation attempts, error details, reauth history                  |
| `is_active`             | bool             | User-controlled enable/disable toggle                                                    |
| `auth_status`           | string(32)       | System-managed: `valid` · `expired` · `invalid` · `reauth_required`                      |
| `deleted_at`            | timestamp / null | Soft delete timestamp (preserves audit trail)                                            |
| `created_at`            | timestamp        | When the connection was created                                                          |
| `updated_at`            | timestamp        | Last modification timestamp                                                              |
| `last_used_at`          | timestamp / null | Last time this connection was used (TaskSource poll or AgentTool invocation)             |
| `last_validated_at`     | timestamp / null | Last successful authentication check                                                     |

### SQLAlchemy 2.0 Model

```python
# backend/models/connection.py
"""
Connection Model - Authenticated connection to an external integration.

A Connection stores credentials and auth state for a specific integration instance.
It can be shared across multiple TaskSources (triggers) and AgentTools (actions).
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import uuid

from backend.models.base import Base
from backend.registry import ALL_INTEGRATIONS


class Connection(Base):
    """
    Represents an authenticated connection to an external system.

    Examples:
    - Microsoft Graph app-only credentials for Outlook/SharePoint
    - Google OAuth tokens for Gmail/Drive
    - AWS IAM role credentials for S3
    - Salesforce OAuth/JWT bearer tokens
    """
    __tablename__ = "connections"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Foreign Keys
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Connection Identity
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    provider_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Validated against ALL_INTEGRATIONS registry at runtime"
    )

    auth_schema_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="References AUTH_SCHEMAS registry (e.g., 'msft.oauth2.app_only')"
    )

    # Credentials (Fernet encrypted)
    encrypted_credentials: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Fernet-encrypted user inputs: client_id, client_secret, api_keys, etc."
    )

    encrypted_token: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted OAuth tokens: access_token, refresh_token, expires_at"
    )

    # Non-Sensitive Config
    connection_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Provider-specific non-sensitive config: region, tenant_id, instance_url"
    )

    metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Operational context: validation_attempts, error_details, reauth_history"
    )

    # Status & Health
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
        comment="User-controlled enable/disable toggle"
    )

    auth_status: Mapped[str] = mapped_column(
        String(32),
        default="valid",
        index=True,
        comment="System-managed: valid, expired, invalid, reauth_required"
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Soft delete timestamp for audit trail"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last TaskSource poll or AgentTool invocation"
    )

    last_validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful authentication check"
    )

    # Validation
    @validates('provider_key')
    def validate_provider_key(self, key, value):
        """Validate provider_key exists in the integration registry."""
        if value not in ALL_INTEGRATIONS:
            raise ValueError(
                f"Invalid provider_key: '{value}'. "
                f"Must be one of: {', '.join(sorted(ALL_INTEGRATIONS.keys()))}"
            )
        return value

    # Relationships
    created_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by]
    )

    task_sources: Mapped[list["TaskSource"]] = relationship(
        "TaskSource",
        back_populates="connection",
        cascade="all, delete-orphan"
    )

    agent_tools: Mapped[list["AgentTool"]] = relationship(
        "AgentTool",
        back_populates="connection",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Connection(id={self.id}, name='{self.name}', provider='{self.provider_key}', status='{self.auth_status}')>"
```

### Key Design Decisions

1. **Explicit encryption fields** — `encrypted_credentials` and `encrypted_token` use Fernet symmetric encryption in-app rather than external vault pointers. Simplifies deployment for customer-hosted environments.

2. **Dual status tracking** — `is_active` (user control) vs `auth_status` (system detection) provides clear separation of concerns and better UX.

3. **Soft deletes** — `deleted_at` preserves audit trails and enables recovery. Essential for compliance.

4. **Activity tracking** — `last_used_at` and `last_validated_at` enable monitoring, cleanup policies, and proactive reauth prompts.

5. **Registry validation** — `provider_key` is validated against the Python registry using SQLAlchemy's `@validates` decorator, ensuring referential integrity without a catalog table.

6. **Metadata for extensibility** — JSONB `metadata` field allows tracking operational context without schema changes.

### Metadata Structure

The `metadata` JSONB field stores operational context for debugging and monitoring:

```python
{
    # Validation tracking
    "validation_attempts": 3,
    "last_validation_error": "Token refresh failed: invalid_grant",
    "last_validation_at": "2024-01-01T10:00:00Z",

    # Reauth history
    "reauth_prompts_sent": 2,
    "last_reauth_prompt_at": "2024-01-01T09:00:00Z",
    "reauth_method": "email",  # email, in-app, webhook

    # Connection health
    "consecutive_failures": 0,
    "last_failure_at": null,
    "last_success_at": "2024-01-01T10:05:00Z",

    # Rate limiting context
    "rate_limit_hits": 5,
    "last_rate_limit_at": "2024-01-01T09:30:00Z",
    "rate_limit_reset_at": "2024-01-01T10:00:00Z",

    # Provider-specific context
    "tenant_info": {"id": "abc123", "region": "us-east-1"},
    "scopes_granted": ["Mail.Read", "Mail.Send"],
    "token_expiry_warning_sent": false
}
```

**Common fields:**

- `validation_attempts` - Count of validation attempts
- `last_validation_error` - Detailed error from last validation
- `reauth_prompts_sent` - Number of reauth notifications sent
- `consecutive_failures` - Track connection health
- `rate_limit_hits` - Track rate limiting incidents
- `tenant_info` - Provider-specific tenant context

---

## 3. TaskSource Model

A configured watch point — the instance of a Trigger bound to a Connection and an Agent. This is the core operational entity: it defines _what_ to watch, _how_ to watch it, and _which agent_ receives the resulting events. Referred to as **Source** in the UI.

### Table Schema

| Field               | Type             | Description                                                                        |
| ------------------- | ---------------- | ---------------------------------------------------------------------------------- |
| `id`                | uuid             | Primary key                                                                        |
| `agent_id`          | uuid             | FK → Agent this TaskSource feeds events into                                       |
| `connection_id`     | uuid             | FK → Connection (auth boundary)                                                    |
| `provider_key`      | string(64)       | Provider identifier (denormalized from Connection for queries)                     |
| `trigger_key`       | string(128)      | Trigger template key (e.g., `outlook.new_email`, `aws_s3.new_object`)              |
| `name`              | string(255)      | User-visible label (e.g., "Support Inbox — New Email")                             |
| `description`       | text / null      | Optional description                                                               |
| `resource_config`   | jsonb            | What to watch — mailbox+folder / bucket+prefix / object+query                      |
| `filter_config`     | jsonb            | Conditions to narrow events — sender domains, attachment types, field filters      |
| `schedule_config`   | jsonb            | Interval/cron, jitter, backoff; also used for webhook health-check fallback        |
| `processing_config` | jsonb            | How to handle matched events — include body, download attachments, field selection |
| `enabled`           | bool             | Manual on/off toggle                                                               |
| `status`            | string(32)       | `ok` · `warn` · `error` · `auth_error`                                             |
| `cursor`            | jsonb            | Runtime polling state — delta token, timestamp, offset, history_id                 |
| `metadata`          | jsonb            | Operational context: polling metrics, adapter version, error history, rate limits  |
| `last_checked_at`   | timestamp / null | Last time the adapter ran for this TaskSource                                      |
| `last_success_at`   | timestamp / null | Last time the adapter successfully ingested events                                 |
| `error_count`       | int              | Consecutive error count for exponential backoff                                    |
| `last_error`        | text / null      | Last error message for debugging                                                   |
| `tags`              | jsonb            | Optional labels for filtering/grouping                                             |
| `deleted_at`        | timestamp / null | Soft delete timestamp (preserves audit trail)                                      |
| `created_at`        | timestamp        |                                                                                    |
| `updated_at`        | timestamp        |                                                                                    |

### SQLAlchemy 2.0 Model

```python
# backend/models/task_source.py
"""
TaskSource Model - Configured instance of a Trigger.

A TaskSource is the operational entity that polls/receives events from an external system
and routes them to an Agent. It binds a Trigger template to a Connection and Agent.
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import uuid

from backend.models.base import Base
from backend.registry import ALL_TRIGGERS


class TaskSource(Base):
    """
    Represents a configured event source (trigger instance).

    Examples:
    - "Support Inbox — New Email" (Outlook, polls support@company.com/Inbox)
    - "Invoices Drop — New File" (AWS S3, polls invoices/ prefix)
    - "Opportunities Changed" (Salesforce, polls Opportunity object)
    """
    __tablename__ = "task_sources"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Foreign Keys
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Identity
    provider_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Denormalized from connection for efficient queries"
    )

    trigger_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="References TRIGGERS registry (e.g., 'outlook.new_email')"
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="User-visible label"
    )

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Configuration (from Trigger template schemas)
    resource_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="What to watch: mailbox+folder, bucket+prefix, object+query"
    )

    filter_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Event filters: sender domains, attachment types, field conditions"
    )

    schedule_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Polling interval, cron, jitter, backoff"
    )

    processing_config: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Event processing: include body, download attachments, field selection"
    )

    # Status & Control
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
        comment="User-controlled on/off toggle"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        default="ok",
        index=True,
        comment="Health status: ok, warn, error, auth_error"
    )

    # Runtime State
    cursor: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Polling state: delta_token, timestamp, offset, history_id"
    )

    metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Operational context: polling_metrics, adapter_version, error_history, rate_limits"
    )

    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last adapter execution time"
    )

    last_success_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful event ingestion"
    )

    error_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Consecutive errors for exponential backoff"
    )

    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message for debugging"
    )

    # Metadata
    tags: Mapped[dict] = mapped_column(
        JSONB,
        default=list,
        comment="Optional labels for filtering/grouping"
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Soft delete timestamp for audit trail"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Validation
    @validates('trigger_key')
    def validate_trigger_key(self, key, value):
        """Validate trigger_key exists in the triggers registry."""
        if value not in ALL_TRIGGERS:
            raise ValueError(
                f"Invalid trigger_key: '{value}'. "
                f"Must be one of: {', '.join(sorted(ALL_TRIGGERS.keys()))}"
            )
        return value

    # Relationships
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="task_sources"
    )

    connection: Mapped["Connection"] = relationship(
        "Connection",
        back_populates="task_sources"
    )

    events: Mapped[list["EventInbox"]] = relationship(
        "EventInbox",
        back_populates="task_source",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TaskSource(id={self.id}, name='{self.name}', trigger='{self.trigger_key}', status='{self.status}')>"
```

### Key Design Decisions

1. **Config vs Runtime separation** — Clear distinction between user configuration (resource/filter/schedule/processing) and runtime state (cursor/timestamps/errors).

2. **Cursor on same row** — Polling state stored directly on TaskSource (not separate table) to avoid joins on every poll cycle.

3. **String status** — Health state as string enum (not JSONB like EventInbox) because TaskSource tracks health, not processing progress.

4. **Keep error columns** — `error_count` and `last_error` remain as columns (not moved to metadata) for exponential backoff logic and indexed queries.

5. **Registry validation** — `trigger_key` validated against `ALL_TRIGGERS` registry using `@validates` decorator.

6. **Soft deletes** — `deleted_at` preserves historical TaskSource data for audit trail and EventInbox references.

7. **Metadata for extensibility** — JSONB `metadata` field tracks operational context without schema changes.

### Metadata Structure

The `metadata` JSONB field stores operational context for monitoring and debugging:

```python
{
    # Polling performance
    "avg_poll_duration_ms": 850,
    "avg_events_per_poll": 12,
    "last_poll_duration_ms": 920,
    "total_polls": 1453,
    "total_events_ingested": 17436,

    # Health monitoring
    "health_checks_passed": 1450,
    "health_checks_failed": 3,
    "last_health_check_at": "2024-01-01T10:00:00Z",
    "uptime_percentage": 99.8,

    # Rate limiting
    "rate_limit_hits": 3,
    "last_rate_limit_at": "2024-01-01T09:30:00Z",
    "rate_limit_resets": 3,

    # Adapter context
    "adapter_version": "1.2.3",
    "delivery_mode": "poll",  # or "webhook"
    "supports_delta_sync": true,

    # Error history (detailed)
    "error_history": [
        {
            "timestamp": "2024-01-01T09:00:00Z",
            "error_type": "timeout",
            "error_message": "Connection timeout after 30s",
            "duration_ms": 30000,
            "recovered": true
        },
        {
            "timestamp": "2024-01-01T09:05:00Z",
            "error_type": "rate_limit",
            "retry_after": 60,
            "recovered": true
        }
    ],

    # Provider-specific
    "delta_token_refreshed_at": "2024-01-01T08:00:00Z",
    "subscription_id": "abc123",  # For webhook mode
    "webhook_health_check_interval": 3600
}
```

**Common fields:**

- `avg_poll_duration_ms` - Average polling duration
- `avg_events_per_poll` - Average events per poll cycle
- `total_events_ingested` - Lifetime event count
- `health_checks_passed/failed` - Health monitoring stats
- `rate_limit_hits` - Rate limiting incidents
- `adapter_version` - Adapter version for debugging
- `delivery_mode` - `poll` or `webhook`
- `error_history` - Detailed error tracking array

---

## 4. EventInbox Model

Intermediate event storage between ingestion and agent routing. Each row is a single event occurrence produced by a TaskSource. Deduplication is handled via `dedupe_key` — the adapter writes the event only if no existing row shares the same key.

### Table Schema

| Field               | Type             | Description                                                                        |
| ------------------- | ---------------- | ---------------------------------------------------------------------------------- |
| `id`                | uuid             | Primary key                                                                        |
| `task_source_id`    | uuid             | FK → TaskSource that produced this event                                           |
| `external_event_id` | string(255)      | Provider-native identifier (e.g., Graph message id, S3 object key+etag)            |
| `dedupe_key`        | string(255)      | Unique key for deduplication (indexed, unique constraint)                          |
| `payload`           | jsonb            | Normalized event data (what the agent processes)                                   |
| `metadata`          | jsonb            | Processing context: trace IDs, attempts history, routing, ingestion stats          |
| `status`            | jsonb            | Processing progress: state, attempts, last_attempt_at, errors, progress, worker_id |
| `processed_at`      | timestamp / null | When the event was successfully processed by the agent                             |
| `error_message`     | text / null      | Last error message (deprecated - use status.last_error)                            |
| `created_at`        | timestamp        | When the event was ingested                                                        |

### SQLAlchemy 2.0 Model

```python
# backend/models/event_inbox.py
"""
EventInbox Model - Intermediate event storage before agent routing.

Events are written here by trigger adapters and consumed by agent workers.
Deduplication ensures we don't process the same event twice.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import uuid

from backend.models.base import Base


class EventInbox(Base):
    """
    Represents an ingested event waiting to be processed by an agent.

    Events flow: External System → Adapter → EventInbox → Agent Worker → Task

    Status structure:
    {
        "state": "pending" | "processing" | "processed" | "failed",
        "attempts": 1,
        "last_attempt_at": "2024-01-01T10:00:00Z",
        "last_error": "timeout",
        "progress": 50,
        "worker_id": "worker-3"
    }
    """
    __tablename__ = "event_inbox"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Foreign Keys
    task_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Event Identity
    external_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Provider-native event ID (e.g., Graph message ID, S3 ETag)"
    )

    dedupe_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Unique key for deduplication (e.g., task_source_id:external_event_id)"
    )

    # Event Data
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Normalized event payload (what the agent processes)"
    )

    metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="Processing context: trace_ids, attempts_history, routing, ingestion_stats"
    )

    # Processing Status
    status: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {"state": "pending", "attempts": 0},
        nullable=False,
        comment="Processing progress: state, attempts, last_attempt_at, errors, progress, worker_id"
    )

    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the event was successfully processed"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message (deprecated - use status.last_error instead)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    # Relationships
    task_source: Mapped["TaskSource"] = relationship(
        "TaskSource",
        back_populates="events"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint('dedupe_key', name='uq_event_inbox_dedupe_key'),
    )

    def __repr__(self) -> str:
        state = self.status.get("state", "unknown") if isinstance(self.status, dict) else "unknown"
        return f"<EventInbox(id={self.id}, dedupe_key='{self.dedupe_key}', state='{state}')>"
```

### Status Structure

The `status` JSONB field tracks comprehensive processing progress:

```python
# Initial state (on insertion)
{
    "state": "pending",
    "attempts": 0
}

# During processing
{
    "state": "processing",
    "attempts": 1,
    "last_attempt_at": "2024-01-01T10:00:00Z",
    "worker_id": "worker-3",
    "progress": 50  # Optional: percentage complete
}

# On failure
{
    "state": "failed",
    "attempts": 3,
    "last_attempt_at": "2024-01-01T10:02:00Z",
    "last_error": "Connection timeout after 30s",
    "next_retry_at": "2024-01-01T10:05:00Z"
}

# On success
{
    "state": "processed",
    "attempts": 1,
    "last_attempt_at": "2024-01-01T10:00:00Z",
    "worker_id": "worker-3",
    "processing_duration_ms": 1250
}
```

**Common fields:**

- `state` (required): `"pending"` | `"processing"` | `"processed"` | `"failed"`
- `attempts` (required): Number of processing attempts
- `last_attempt_at` (optional): ISO timestamp of last attempt
- `worker_id` (optional): ID of the worker processing this event
- `progress` (optional): Percentage complete (0-100)
- `last_error` (optional): Last error message
- `next_retry_at` (optional): ISO timestamp for next retry
- `processing_duration_ms` (optional): How long processing took

### Metadata Structure

The `metadata` JSONB field stores operational context:

```python
{
    # Observability
    "trace_id": "abc123",
    "span_id": "def456",
    "correlation_id": "evt_789",

    # Ingestion stats
    "ingestion_latency_ms": 45,
    "adapter_version": "1.2.3",
    "poll_duration_ms": 1200,

    # Routing
    "priority": "high",
    "requires_manual_review": false,
    "matched_rules": ["urgent_keyword", "vip_sender"],

    # Event classification
    "event_type": "email.received",
    "category": "customer_support"
}
```

---

## 5. AgentTool Model

A tool binding — the instance of a Tool bound to an Agent and a Connection. This is the actions-side equivalent of TaskSource: it defines _what action_ the agent can perform, and _which credentials_ to use. Referred to simply as a "Tool" in the Agent config UI.

### Table Schema

| Field           | Type        | Description                                                            |
| --------------- | ----------- | ---------------------------------------------------------------------- |
| `id`            | uuid        | Primary key                                                            |
| `agent_id`      | uuid        | FK → Agent that can invoke this tool                                   |
| `connection_id` | uuid        | FK → Connection (auth boundary for tool execution)                     |
| `provider_key`  | string(64)  | Provider identifier (denormalized from Connection for queries)         |
| `tool_key`      | string(128) | Tool template key (e.g., `outlook.send_email`, `aws_s3.upload_object`) |
| `created_at`    | timestamp   |                                                                        |
| `updated_at`    | timestamp   |                                                                        |

### SQLAlchemy 2.0 Model

```python
# backend/models/agent_tool.py
"""
AgentTool Model - Tool binding for an agent.

An AgentTool binds a Tool template to an Agent via a Connection.
It's a pure binding — no config, no schedule, no cursor.
The agent provides all parameters at invocation time.
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
import uuid

from backend.models.base import Base


class AgentTool(Base):
    """
    Represents a tool (action) that an agent can invoke.

    Examples:
    - Agent can use "outlook.send_email" via "Support Outlook" connection
    - Agent can use "aws_s3.upload_object" via "Finance AWS" connection
    """
    __tablename__ = "agent_tools"

    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )

    # Foreign Keys
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Tool Identity
    provider_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Denormalized from connection for efficient queries"
    )

    tool_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="References TOOLS registry (e.g., 'outlook.send_email')"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="agent_tools"
    )

    connection: Mapped["Connection"] = relationship(
        "Connection",
        back_populates="agent_tools"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint('agent_id', 'tool_key', name='uq_agent_tool_key'),
    )

    def __repr__(self) -> str:
        return f"<AgentTool(id={self.id}, tool='{self.tool_key}')>"
```

---

## 6. Credential Encryption

Fernet-based symmetric encryption for connection credentials and tokens. Uses application-managed key stored in environment variable.

```python
# backend/utils/encryption.py
"""
Credential encryption utilities using Fernet symmetric encryption.

Security considerations:
- Encryption key must be securely stored (environment variable, secrets manager)
- Rotate encryption keys periodically
- Use different keys for dev/staging/prod environments
"""

from cryptography.fernet import Fernet
import json
import os
from typing import Dict, Any


class CredentialEncryption:
    """Handles encryption/decryption of connection credentials and tokens."""

    def __init__(self):
        """
        Initialize encryption cipher with key from environment.

        Generate a new key with: Fernet.generate_key()
        Store in ENCRYPTION_KEY environment variable.
        """
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            raise ValueError(
                "ENCRYPTION_KEY environment variable not set. "
                "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        self.cipher = Fernet(key.encode())

    def encrypt_credentials(self, credentials: Dict[str, Any]) -> str:
        """
        Encrypt credentials dict to base64 string.

        Args:
            credentials: Dict containing auth credentials (client_id, client_secret, etc.)

        Returns:
            Base64-encoded encrypted string suitable for database storage

        Example:
            >>> encryptor = CredentialEncryption()
            >>> creds = {"client_id": "abc123", "client_secret": "secret456"}
            >>> encrypted = encryptor.encrypt_credentials(creds)
            >>> # Store encrypted in database
        """
        json_bytes = json.dumps(credentials).encode()
        encrypted_bytes = self.cipher.encrypt(json_bytes)
        return encrypted_bytes.decode()

    def decrypt_credentials(self, encrypted_str: str) -> Dict[str, Any]:
        """
        Decrypt base64 string back to credentials dict.

        Args:
            encrypted_str: Base64-encoded encrypted string from database

        Returns:
            Dict containing decrypted credentials

        Raises:
            cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data)

        Example:
            >>> encryptor = CredentialEncryption()
            >>> encrypted = connection.encrypted_credentials
            >>> creds = encryptor.decrypt_credentials(encrypted)
            >>> print(creds["client_id"])
        """
        encrypted_bytes = encrypted_str.encode()
        decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
        return json.loads(decrypted_bytes.decode())


# Singleton instance
_encryptor = None


def get_encryptor() -> CredentialEncryption:
    """Get or create singleton encryption instance."""
    global _encryptor
    if _encryptor is None:
        _encryptor = CredentialEncryption()
    return _encryptor


# Usage examples:

# Encrypt and store credentials
def create_connection_with_creds(credentials: dict, token: dict = None):
    """Helper to create a connection with encrypted credentials."""
    encryptor = get_encryptor()

    connection = Connection(
        name="My Connection",
        provider_key="outlook",
        auth_schema_key="msft.oauth2.app_only",
        encrypted_credentials=encryptor.encrypt_credentials(credentials),
        encrypted_token=encryptor.encrypt_credentials(token) if token else None,
    )
    return connection


# Decrypt and use credentials
def get_connection_credentials(connection: Connection) -> Dict[str, Any]:
    """Helper to decrypt connection credentials."""
    encryptor = get_encryptor()
    return encryptor.decrypt_credentials(connection.encrypted_credentials)


def get_connection_token(connection: Connection) -> Dict[str, Any]:
    """Helper to decrypt connection OAuth tokens."""
    if not connection.encrypted_token:
        return None
    encryptor = get_encryptor()
    return encryptor.decrypt_credentials(connection.encrypted_token)
```

---

## 7. Database Indexes

Recommended indexes for query performance:

```sql
-- Connection indexes
CREATE INDEX idx_connections_provider_key ON connections(provider_key);
CREATE INDEX idx_connections_auth_status ON connections(auth_status) WHERE deleted_at IS NULL;
CREATE INDEX idx_connections_is_active ON connections(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_connections_deleted_at ON connections(deleted_at);
CREATE INDEX idx_connections_metadata_gin ON connections USING GIN (metadata);  -- Query metadata

-- TaskSource indexes
CREATE INDEX idx_task_sources_agent_id ON task_sources(agent_id);
CREATE INDEX idx_task_sources_connection_id ON task_sources(connection_id);
CREATE INDEX idx_task_sources_provider_key ON task_sources(provider_key);
CREATE INDEX idx_task_sources_trigger_key ON task_sources(trigger_key);
CREATE INDEX idx_task_sources_enabled ON task_sources(enabled);
CREATE INDEX idx_task_sources_status ON task_sources(status);
CREATE INDEX idx_task_sources_last_checked_at ON task_sources(last_checked_at) WHERE enabled = true;
CREATE INDEX idx_task_sources_metadata_gin ON task_sources USING GIN (metadata);  -- Query metadata
CREATE INDEX idx_task_sources_deleted_at ON task_sources(deleted_at);

-- EventInbox indexes
CREATE UNIQUE INDEX idx_event_inbox_dedupe_key ON event_inbox(dedupe_key);
CREATE INDEX idx_event_inbox_task_source_id ON event_inbox(task_source_id);
CREATE INDEX idx_event_inbox_status_state ON event_inbox((status->>'state'));  -- Query by state
CREATE INDEX idx_event_inbox_status_gin ON event_inbox USING GIN (status);     -- General JSONB queries
CREATE INDEX idx_event_inbox_metadata_gin ON event_inbox USING GIN (metadata); -- Query metadata
CREATE INDEX idx_event_inbox_created_at ON event_inbox(created_at);

-- AgentTool indexes
CREATE UNIQUE INDEX idx_agent_tool_agent_tool_key ON agent_tools(agent_id, tool_key);
CREATE INDEX idx_agent_tool_connection_id ON agent_tools(connection_id);
CREATE INDEX idx_agent_tool_provider_key ON agent_tools(provider_key);
```

---

## 8. Relationships Diagram

```
         ┌──────────────────────────────┐
         │   ALL_INTEGRATIONS Registry  │
         │      (Python In-Memory)      │
         └──────────────┬───────────────┘
                        │ validates
                        ▼
┌─────────────────────────┐
│     Connection          │◄──────── User (created_by)
│  (Auth Credentials)     │
│   provider_key          │
└─────┬───────────────┬───┘
      │ 1:N           │ 1:N
      ▼               ▼
┌─────────────┐  ┌─────────────┐
│ TaskSource  │  │  AgentTool  │
│ (Triggers)  │  │  (Actions)  │
│ provider_key│  │ provider_key│
└──────┬──────┘  └──────┬──────┘
       │ 1:N            │ N:1
       ▼                ▼
┌─────────────┐  ┌─────────────┐
│ EventInbox  │  │    Agent    │
│  (Events)   │  │             │
└─────────────┘  └─────────────┘

Legend:
- ALL_INTEGRATIONS: Python registry (single source of truth for metadata)
- Connection: Stores encrypted credentials; provider_key validated at runtime
- TaskSource: Configured trigger instances (inbound events)
- AgentTool: Tool bindings (outbound actions)
- EventInbox: Intermediate event storage before routing
- Agent: Receives events from TaskSources, invokes AgentTools
```

---

## Summary

This database schema provides:

✅ **Single source of truth** — Integration metadata in Python registries, not duplicated in database
✅ **Runtime validation** — `provider_key` validated against `ALL_INTEGRATIONS` registry using `@validates`
✅ **Proper referential integrity** — Foreign keys with cascade deletes, registry validation for provider_key
✅ **Security by default** — Fernet encryption for sensitive credentials
✅ **Audit trails** — Soft deletes, timestamps, activity tracking
✅ **Query performance** — Denormalized keys, strategic indexes
✅ **Production-ready** — Type hints, constraints, relationships, comments
✅ **No sync burden** — Changes to integration metadata only require code deployment, not database migrations

All models use SQLAlchemy 2.0 `Mapped` and `mapped_column` patterns for type safety and modern best practices.
