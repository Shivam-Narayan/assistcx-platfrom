# Custom libraries
from db_pool import Base

# Default libraries
import uuid
from datetime import datetime
from typing import Optional

# Installed libraries
from sqlalchemy import ARRAY, DateTime, String, Text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.inspection import inspect
from sqlalchemy.sql import func

# Import for type hints
from models.task_source_v4 import TaskSource
from models.tool_binding_v4 import ToolBinding


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(CITEXT, unique=True, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    intent_class: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # deprecated
    style: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # behaviour
    goal: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # behaviour
    instructions: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # behaviour
    rules: Mapped[Optional[list]] = mapped_column(
        ARRAY(String), nullable=True
    )  # behaviour
    data_templates: Mapped[Optional[list]] = mapped_column(
        ARRAY(String), nullable=True
    )  # runtime
    success_criteria: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # behaviour
    tools: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    plan: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    knowledge_base: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # runtime
    agent_llm: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # agent_settings
    examples: Mapped[Optional[list]] = mapped_column(
        ARRAY(Text), nullable=True
    )  # deprecated
    agent_mailbox: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )  # assignment
    agent_config: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )  # agent_settings
    data_store: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # runtime
    reviewers: Mapped[Optional[list]] = mapped_column(
        ARRAY(String), nullable=True
    )  # agent_settings
    status: Mapped[str] = mapped_column(String, default="ACTIVE")
    response_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skills: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    class_groups: Mapped[Optional[list]] = mapped_column(
        ARRAY(String), nullable=True
    )  # runtime
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    emails: Mapped[list["Email"]] = relationship(  # type: ignore
        "Email", back_populates="agent"
    )
    agent_outputs: Mapped[list["AgentOutput"]] = relationship(  # type: ignore
        "AgentOutput", back_populates="agent"
    )
    agent_tasks: Mapped[list["AgentTask"]] = relationship(  # type: ignore
        "AgentTask", back_populates="agent"
    )
    tool_bindings: Mapped[list["ToolBinding"]] = relationship(  # type: ignore
        "ToolBinding", back_populates="agent", cascade="all, delete-orphan"
    )
    task_sources: Mapped[list["TaskSource"]] = relationship(  # type: ignore
        "TaskSource", back_populates="agent", cascade="all, delete-orphan"
    )

    def to_dict(self):
        """Return dictionary representation of model columns."""
        return {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}


"""
Comments:
=========
Added columns:
- plan
- reviewers
- response_schema

Modified columns:
- mailbox_trigger -> agent_mailbox
- expected_output -> success_criteria
"""

"""
---------------------------------------------------------------------
class Agent(Base):
    __tablename__ = "agents"

    # --- Identity / indexed ---
    id:             Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
                        primary_key=True, default=uuid.uuid4, index=True)
    name:           Mapped[Optional[str]] = mapped_column(CITEXT, unique=True, nullable=True)
    description:    Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status:         Mapped[str]           = mapped_column(String, default="ACTIVE", index=True)
    icon:           Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Tools (kept flat: validated, central, frequently inspected) ---
    tools:          Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    #   [{ name, action, description, human_review, review_rules }]

    # --- Plan: the sequence of actions to be taken ---
    plan:           Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    #   [{ step_name, condition, action, rules, tool }]

    # --- Response schema: the schema of the response to be returned ---
    response_schema: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    #   [{ field, type, description }]

    # --- Skills: the skills of the agent ---
    skills:         Mapped[Optional[list[dict]]] = mapped_column(JSONB, nullable=True)
    #   [{name, descrption, storage_reference}]

    # --- Behavior: everything that shapes the system prompt ---
    behavior:       Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    #   {
    #     "style":             str,
    #     "goal":              str, //Expertise
    #     "instructions":      str,
    #     "rules":             [str],
    #     "success_criteria":  str,
    #   }

    # --- Runtime: external resources resolved during graph init / tool calls ---
    runtime:        Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    #   {
    #     "knowledge_base":   [ {collection_id, name, index_name} ],
    #     "data_templates":   [template_id, ...],
    #     "class_groups":     [class_group_id, ...]
    #   }
    # Note: storage location no longer lives here. Each tool's read/write
    # scope is on its ToolBinding row (connection_id + tool_config.path +
    # tool_config.role). See ToolBinding for the binding-level shape.

    # --- Assignment type: how this agent receives tasks ---
    assignment_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    #   One of: "Integration name eg: Outlook, Gmail or S3" | "webhook" | "schedule" | "ai" | "task_api"

    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    #   One of: "Mailbox" | "Task_api" | "AI_Assignment" | "Assistant" | "Schedule" | External_Apps | "Agent"

    source_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # source_config = { source_id, any other useful property }

    # --- Orchestration: task factory / worker / review gating decisions ---
    agent_settings:   Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    #   {
    #     "agent_llm":                 str,
    #     "split_task_by_attachments": bool,
    #     "retry_incomplete_tasks":    bool,
    #     "allow_task_followup":       bool,
    #     "vision_data_extraction":    bool,
    #     "human_reviewers":           [str]
    #   }

    # --- Timestamps ---
    created_at, updated_at ..

=====================================================================
Planning notes, will be removed once the model is finalized:
=====================================================================
Rationale:
  - Keep SQL-queryable fields FLAT so indexes and ILIKE searches still work.
  - Group the rest by *lifecycle concern*, not by "anything that isn't a column".
  - Three blobs with crisp boundaries:
      behaviour      -> what goes into the system prompt
      runtime       -> external resources the agent/tool-runtime resolves
      agent_settings  -> decisions consumed by task factory / worker / UI

Columns that MUST stay flat (have real SQL consumers today):
  id, name, description, status, icon,
  tools, plan, response_schema, skills, created_at, updated_at
  - name: unique + equality lookups
  - description: ILIKE in search_agents()
  - status: filtered in every list query (ACTIVE vs ARCHIVED)
  - icon: tiny, UI-only, cheap as a column
  - tools: rich Pydantic schema + central to every execution path;
           blob-ifying loses per-tool validation with no clear upside
  - plan: complex, core to every execution path; blob-ifying loses
          per-step validation with no clear upside
  - response_schema: rich, core to every execution path; blob-ifying
                      loses per-field validation with no clear upside
  - skills: rich, core to every execution path; blob-ifying loses
            per-skill validation with no clear upside
  - created_at, updated_at: timestamps

Assignment / how tasks reach an agent (replaces agent_mailbox +
agent_config.ai_assignment + agent_config.external_task_api):

  One column on the agent: `assignment_type` (str, indexed).
  Values: "mailbox" | "webhook" | "schedule" | "ai" | "task_api".

  - For trigger types (mailbox / webhook / schedule), the actual config
    lives in TaskSource rows — see task_source_v4.py. Each row holds
    connection_id, trigger_key, resource/filter/schedule config, and
    polling state (cursor, error_count, last_checked_at).
        mailbox:  trigger_key="outlook.new_email",  resource={folder}
        webhook:  trigger_key="webhook.<provider>", connection holds secret
        schedule: trigger_key="schedule.cron",      schedule={cron}
    An agent can still have N TaskSource rows under one assignment_type
    (e.g. "mailbox" agent watching multiple folders).

  - For non-trigger types (ai / task_api), no TaskSource is needed —
    they're routing modes, not pollers. No creds, no schedule, no cursor.

  Why one column, not flags or a JSONB array:
    - Each agent has a *primary* assignment type; the column captures it
      cleanly and is indexable for lists ("show all mailbox agents").
    - Flags (ai_routable, accepts_external_api) duplicated this. The
      column subsumes them — drop the flags.
    - For trigger types, TaskSource already gives multi-channel via N
      rows + first-class queries (GIN index by trigger_key, connection
      FK cascade, partial unique on (trigger_key, mailbox)).

  Mailbox uniqueness: enforce via partial UNIQUE on TaskSource
  (trigger_key, resource_config->>'mailbox') WHERE deleted_at IS NULL,
  or keep the application-level check in create/update_agent.

Dropped / migrated out:
  - intent_class         -> deprecated; drop after migrating callers
                            (get_agent/delete_agent currently accept it
                             as an alternate key)
  - agent_mailbox        -> dropped from agent. Backfill into a TaskSource
                            row (trigger_key="outlook.new_email") per
                            existing agent_mailbox value AND set
                            assignment_type="mailbox" on the agent.
                            Then drop the column. Symmetric with
                            data_store -> ToolBinding.
  - examples             -> deprecated; drop after migrating callers
  - style, goal, success_criteria, instructions, rules -> moved into `behaviour`
  - knowledge_base, data_templates, class_groups -> moved into `runtime`
  - data_store           -> dropped from agent entirely. Scope (path + role)
                            moves to ToolBinding.tool_config; the connection
                            link already lives on ToolBinding.connection_id.
                            Symmetric with TaskSource.resource_config, which
                            already holds "where to read events from."
                            Rationale: bindings are first-class rows in v4;
                            keeping data_store as a JSONB blob on agent
                            duplicates connection_id and breaks that pattern.
  - reviewers            -> moved into `agent_settings` (never queried at SQL)
  - ai_assignment        -> dropped. Set assignment_type="ai" on agents
                            where this flag was true.
  - external_task_api    -> dropped. Set assignment_type="task_api"
                            on agents where this flag was true.

Search-path note: search_agents() also ILIKEs style/goal. On migration,
either (a) keep style/goal flat, or (b) rewrite search to use
`behaviour->>'goal'` + a GIN index on `behaviour`. Option (b) is preferred
long-term; option (a) is a safe intermediate step.

.
---------------------------------------------------------------------

Migration sequence (safe order):
  1. Add behavior/runtime columns (nullable), keep old columns in place.
  2. Dual-write in the create/update paths; backfill existing rows.
  3. Switch readers (executor._initialize_graph, executor_helper,
     task_factory) to read from the new blobs.
  4. Update Pydantic schemas + AgentBuilder output shape (or flatten
     on serialization to avoid a frontend break).
  5. Rewrite search_agents() to use JSONB operators if style/goal move.
  6. Drop legacy columns + intent_class in one follow-up migration.

Trade-offs to accept before committing:
  + fewer ALTER TABLEs when adding new behavior/runtime keys
  + clearer mental model for agent builder UI (behavior vs runtime tabs)
  - loses column-level NOT NULL on goal/instructions (enforce in Pydantic)
  - JSONB partial updates need merge logic; concurrent PATCH writers
    need `jsonb_set` or row locks to avoid last-write-wins on sibling keys
=====================================================================
"""

"""
style - friendly, professional, formal, casual, creative, balanced, minimalist
----------------------------------------------------
The 'tools' data contains an array of dictionaries, 
with information about various tools required by the agent to complete the task.

Each tool has the following keys:
- 'name': A string representing the name of the tool (e.g., 'Upload to S3').
- 'action': A string describing the action or purpose of the tool (e.g., 'upload_data_to_s3').
- 'function': A string indicating the specific function or method that implements the tool's action (e.g., 's3_upload_tool').

Example:
tools = [
    {
        'name': 'Upload to S3',
        'action': 'upload_data_to_s3',
        'human_review': False
    },
    # More tools here
]
----------------------------------------------------------
The 'knowledge_base' is a list of dictionary, each dictionary representing meta data of 1 file.

Each knowledge_base has the following keys:
- 'collection_id': UUID of the collection.
- 'name': Name of the collection.

Example:
knowledge_base = [
    {
        'collection_id': '123e4567-e89b-12d3-a456-426614174000',
        'name': 'Collection Name',
    },
    # More collections here
]
----------------------------------------------------------
The 'agent_config' column is used as an additional config for agents which is used for decision making in task factory. 

split_task_by_records - Creates n number of tasks for n number of records
split_task_by_attachments - Creates n number of tasks for n number of attachments

Example : 
"agent_config": {
    "split_task_by_records": Flase,
    "split_task_by_attachments": False,
    "All info related to knowledge"
    "planning_and_evaluation": False,
    "human_collaboration": False,
    "structured_output": False,

}
----------------------------------------------------------
Storage location (read/write scope) is no longer modeled on the agent.

Old shape (deprecated, single dict on agent.data_store):
    data_store = {
        'storage_type':   'remote' | 'local',
        'storage_bucket': 'assistcx-data',
        'storage_folder': 'files',
        'storage_region': 'ap-south-1'
    }

New shape: scope lives on each ToolBinding row, symmetric with how
TaskSource.resource_config holds "where to read events from."

    ToolBinding {
        agent_id:      <fk>,
        tool_key:      'filesystem.create_structured_file',
        connection_id: <fk to Connection>,        # provider + creds + bucket/region
        tool_config: {                             # NEW JSONB
            'path': 'files/invoices/',             # relative to connection root
        }
    }

Why on ToolBinding and not on agent:
- Connection (provider, creds, bucket, region) already lives on Connection;
  ToolBinding.connection_id already links it. Repeating those fields on the
  agent would duplicate state.
- Multiple tools with different scopes -> multiple ToolBinding rows. No
  alias-resolution layer needed; the binding row IS the alias.
- The unique (agent_id, tool_key) constraint already enforces one config
  per tool per agent.
- Adding GDrive/SharePoint/SFTP later changes nothing here: a new provider
  registers in ALL_INTEGRATIONS, gets its own Connection rows, and
  ToolBinding.tool_config stays the same shape.

Path semantics (kept simple, role-driven):
- role = 'destination':  path is a folder to write into; tool generates
                         the filename and joins it to path.
- path is ALWAYS relative to the connection's root scope (bucket/drive/site).
  Never absolute, never includes provider/host info.

----------------------------------------------------------
Where today's data_store fields end up (AWS S3 + FileSystem)
----------------------------------------------------------
Both aws_s3_v4.AWSS3V4 and file_system.FileSystem read three keys today:
storage_bucket, storage_folder, storage_region. They split cleanly:

  - bucket / region / mount_alias -> Connection.connection_config
    (stable per credential set — one bucket per S3 connection)
  - folder + role                 -> ToolBinding.tool_config
    (varies per tool — same connection, different scopes per binding)

    # AWS S3 connection
    Connection.connection_config = {
        "bucket": "assistcx-data",     # was data_store.storage_bucket
        "region": "ap-south-1"         # was data_store.storage_region
    }

    # Local/mounted filesystem connection (no creds)
    Connection.connection_config = {
        "host_path": "/home/hp/Projects/assistcx-platform/storage"
        # was data_store.storage_bucket. Matches the "host" field in
        # mounts.json (STORAGE_MOUNT_POINTS env). file_system.py looks
        # this up to resolve the container mount it actually writes to.
        # UI-friendly: shows the user the real host path they configured.
    }

    # ToolBinding.tool_config (same shape for both providers)
    {
        "path": "files/invoices/",     # was data_store.storage_folder
    }
    # tool_config can be {} when path/role don't apply (e.g. outlook.move_email
    # — the tool just needs the connection, no scope).

----------------------------------------------------------


{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "name": "Invoice Data Agent",
  "description": "Agent to extract and upload new invoice data to the system.",
  "status": "ACTIVE",
  "icon": "shapes",
  "tools": [
    {
      "name": "Extract Structured Data",
      "action": "extract_structured_data",
      "description": "",
      "human_review": False,
      "review_rules": None
    },
    {
      "name": "Create Structured File in Filesystem",
      "action": "filesystem_create_structured_file",
      "description": "",
      "human_review": False,
      "review_rules": None
    },
    {
      "name": "Move Email in Outlook",
      "action": "outlook_move_email",
      "description": "",
      "human_review": False,
      "review_rules": None
    }
  ],
  "plan": [
    {
      "id": 0,
      "step_name": "Extraction",
      "tool": [
        "extract_structured_data"
      ],
      "action": [
        "Extract all relevant information and data from attachment using data template assigned"
      ],
      "rules": [
        "If the email body mentions of multiple invoices present as an attachment, do not extract the data of same attachment multiple times.",
        "If the email body mentions of multiple invoices present as an attachment, do not upload the data of same attachment multiple times."
      ],
      "condition": ""
    },
    {
      "id": 1,
      "step_name": "Upload File",
      "tool": [
        "filesystem_create_structured_file"
      ],
      "action": [
        "Use the file name mentioned in the file_url to write the file using \"create_file_in_filesystem\" and make sure to upload the final output json."
      ],
      "rules": [
        "Create field \"agent_notes\" and save all details for which decisions are made by the agent.",
        "Read file_url and extract the substring after the final “/”. Remove the file extension (everything from the last “.” onward). From the remaining string, extract the 10-character identifier immediately before the “-X_of_Y” portion if present. If a multi-file indicator (“-X_of_Y”) exists, append the sequence number X to the identifier. Construct file_name as <identifier><sequence>.json, or <identifier>.json if no sequence exists.",
        "Make sure these fields are included: sender_email, mailbox_email, email_subject, received_date, received_time, attachment_file_url, json_file_name, task_id, email_uuid",
        "Use the file name mentioned in the file_url to write to file. If there are multiple invoices, then make sure use distinct file name for JSON data by using count and ensure that all invoices are uploaded one by one",
        "Extract the file name from file_url (removing its extension), slice exactly the first 50 characters (starting from index 0), then append the sap_po_number if present (separated by _) for uniqueness, and add the .json extension. Upload all invoices before providing the final answer."
      ],
      "condition": ""
    },
    {
      "id": 2,
      "step_name": "Move File to Folder",
      "tool": [],
      "action": [
        "If \"zarchive\" is included in the instructions, use the tool \"Move in Outlook\" to move the email from the folder \"incomplete\" to \"resolved\".",
        "If \"resolved\" is included in the instructions, use the tool \"Move in Outlook\" to move the email from the folder \"incomplete\" to \"done\".",
        "If the task is retried after being incomplete and the file is uploaded, use the tool \"Move in Outlook\" to move the email from the folder \"incomplete\" to \"done\".",
        "After the file is been uploaded, use the tool \"Move in Outlook\" to move the email from the folder \"Inbox\" to \"done\".",
        "If no file upload, use the tool \"Move in Outlook\" to move the email from the folder \"Inbox\" to \"incomplete\"."
      ],
      "rules": [
        "If any file is uploaded regardless of invoice type, move to done"
      ],
      "condition": ""
    }
  ],
  "response_schema": [
    {
      "name": "sap_po_gr_numbers",
      "data_type": "list",
      "description": "List with first entry sap_po_number and sap_gr_number, and then the list from additional_po_gr. Have labels of PO# and GR# for each line. Example of first line: PO#: 37005913, GR#: 5000416261, 5000316339, 5000316340."
    },
    {
      "name": "file_name",
      "data_type": "text",
      "description": "List the file_url from the JSON that is uploaded to filesystem. Example: \"CINTAS_123_19_0h4np.json\""
    },
    {
      "name": "list_items",
      "data_type": "list",
      "description": "give the list of items with labels including description, price, quantity, unspsc code"
    },
    {
      "name": "vendor_name",
      "data_type": "text",
      "description": "give the vendor name"
    }
  ],
  "skills": None, # Plan
  "behavior": {
    "goal": "Post vendor invoice",
    "style": "analytical",
    "instructions": "Your objective is to extract the vendor invoice data from the email attachment and upload file for further processing.",
    "success_criteria": "Invoice data is extracted from the attachment properly and contains all the required fields. Extracted invoice is properly uploaded./nEnsure that  sap_po_number and sap_gr_number number are extracted and uploaded in final json to be uploaded.",
    "rules": [
      "Use email and environment to find the right data for action_input in each step and and try to pass all parameters you can find."
    ]
  },
  "runtime": {
    "knowledge_base": [
        {
            "collection_id": "123e4567-e89b-12d3-a456-426614174000",
            "name": "Collection 1",
            "index_name": "collection_1"
        }
    ],
    "data_templates": [
      "vendor_invoice"
    ],
    "class_groups": []
    # storage scope is NOT here anymore — see ToolBinding rows below
  },
  # ToolBinding rows for this agent (separate table, shown here for clarity):
  # [
  #   {
  #     "tool_key":      "filesystem.create_structured_file",
  #     "connection_id": "<assistcx-data S3 connection uuid>",
  #     "tool_config":   { "path": "files/invoices/", "role": "destination" }
  #   },
  #   {
  #     "tool_key":      "outlook.move_email",
  #     "connection_id": "<outlook mailbox connection uuid>",
  #     "tool_config":   {}   # no path scope needed for this tool
  #   }
  # ],
  "assignment_type": "mailbox",
  # Trigger config lives in TaskSource rows (separate table, shown for clarity):
  # [
  #   {
  #     "trigger_key":     "outlook.new_email",
  #     "connection_id":   "<outlook mailbox connection uuid>",
  #     "resource_config": { "mailbox": "agent@aexonic.com", "folder": "Inbox" },
  #     "schedule_config": { "interval_seconds": 60 }
  #   }
  # ]
  "agent_settings": {
    "agent_llm": "gpt-4o-mini",
    "split_task_by_attachments": True,
    "retry_incomplete_tasks": True,
    "allow_task_followup": True,
    "vision_data_extraction": True, # Do we need it or should it be default on
    "human_reviewers": ["123e4567-e89b-12d3-a456-426614174000"]
  }
}

"""
