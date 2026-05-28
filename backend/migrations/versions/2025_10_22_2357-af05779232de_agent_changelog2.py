"""add status column to agents table

Revision ID: af05779232de
Revises: a160e97b6383
Create Date: 2025-10-22 23:57:47.513791

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "af05779232de"
down_revision: Union[str, None] = "a160e97b6383"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Add status column to agents ---
    op.add_column(
        "agents",
        sa.Column("status", sa.String(), nullable=True, server_default="ACTIVE"),
    )

    # --- Add task_metadata column to agent_tasks ---
    op.add_column(
        "agent_tasks",
        sa.Column(
            "task_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    # --- Add token_usage column to agent_outputs ---
    op.add_column(
        "agent_outputs",
        sa.Column("token_usage", JSON, nullable=True),
    )

    # --- Add output_metadata column to agent_outputs ---
    op.add_column(
        "agent_outputs",
        sa.Column(
            "output_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    # --- Add attachment_metadata column to attachments ---
    op.add_column(
        "attachments",
        sa.Column(
            "attachment_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.alter_column(
        "attachments",
        "structured_output",
        type_=postgresql.JSON(),
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="structured_output::json",
    )

    # Rename attachment_id → external_id
    op.alter_column(
        "attachments",
        "attachment_id",
        new_column_name="external_id",
        existing_type=sa.String(),
    )

    # --- Drop old ai_output, mapping_data, ocr_corrections and ocr_content fields ---
    op.drop_column("attachments", "ai_output")
    op.drop_column("attachments", "mapping_data")
    op.drop_column("attachments", "ocr_corrections")
    op.drop_column("attachments", "ocr_content")

    # --- Add class_groups column to agents table ---
    op.add_column(
        "agents", sa.Column("class_groups", sa.ARRAY(sa.String()), nullable=True)
    )

    # --- Add skills column to agents table ---
    op.add_column(
        "agents",
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # --- Add tag_entity column to tags table ---
    op.add_column("tags", sa.Column("tag_entity", sa.String(), nullable=True))

    # --- Add token_usage column to chat_messages ---
    op.add_column(
        "chat_messages",
        sa.Column("token_usage", JSON, nullable=True),
    )

    # --- Add credits_used column to chat_messages ---
    op.add_column(
        "chat_messages",
        sa.Column("credits_used", sa.Integer(), nullable=True),
    )

    # --- Create issues table ---
    op.create_table(
        "issues",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("progress", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("tag_ids", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("agent_task_ids", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column(
            "issue_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("subscribed", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_issues_created_by"), "issues", ["created_by"], unique=False
    )
    op.create_index(op.f("ix_issues_id"), "issues", ["id"], unique=False)

    # --- Create issue_comments table ---
    op.create_table(
        "issue_comments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("issue_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column(
            "comment_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_issue_comments_id"), "issue_comments", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_issue_comments_issue_id"), "issue_comments", ["issue_id"], unique=False
    )

    # --- Create api_keys table ---
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hint", sa.String(length=24), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=True)
    op.create_index(
        op.f("ix_api_keys_key_hint"), "api_keys", ["key_hint"], unique=False
    )

    # --- Alter activity_logs table ---
    op.alter_column(
        "activity_logs", "user_id", existing_type=sa.VARCHAR(), nullable=True
    )


def downgrade() -> None:
    # --- Alter activity_logs table ---
    op.alter_column(
        "activity_logs", "user_id", existing_type=sa.VARCHAR(), nullable=False
    )

    # --- Drop api_keys table ---
    op.drop_index(op.f("ix_api_keys_key_hint"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_key_hash"), table_name="api_keys")
    op.drop_table("api_keys")

    # --- Drop issue_comments table ---
    op.drop_index(op.f("ix_issue_comments_issue_id"), table_name="issue_comments")
    op.drop_index(op.f("ix_issue_comments_id"), table_name="issue_comments")
    op.drop_table("issue_comments")

    # --- Drop issues table ---
    op.drop_index(op.f("ix_issues_id"), table_name="issues")
    op.drop_index(op.f("ix_issues_created_by"), table_name="issues")
    op.drop_table("issues")

    # --- Remove credits_used column from chat_messages ---
    op.drop_column("chat_messages", "credits_used")

    # --- Remove token_usage column from chat_messages ---
    op.drop_column("chat_messages", "token_usage")

    # --- Remove tag_entity column from tags table ---
    op.drop_column("tags", "tag_entity")

    # --- Remove skills column from agents table ---
    op.drop_column("agents", "skills")

    # --- Remove class_groups column from agents table ---
    op.drop_column("agents", "class_groups")

    # --- Recreate dropped fields first ---
    op.add_column(
        "attachments", sa.Column("ocr_content", sa.ARRAY(sa.Text), nullable=True)
    )
    op.add_column(
        "attachments",
        sa.Column("ocr_corrections", sa.Text(), nullable=True),
    )
    op.add_column(
        "attachments",
        sa.Column(
            "mapping_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "attachments",
        sa.Column("ai_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.alter_column(
        "attachments",
        "structured_output",
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_type=postgresql.JSON(),
        postgresql_using="structured_output::jsonb",
    )

    # Reverse rename external_id → attachment_id
    op.alter_column(
        "attachments",
        "external_id",
        new_column_name="attachment_id",
        existing_type=sa.String(),
    )

    # --- Drop attachment_metadata column from attachments ---
    op.drop_column("attachments", "attachment_metadata")

    # --- Drop output_metadata column from agent_outputs ---
    op.drop_column("agent_outputs", "output_metadata")

    # --- Drop token_usage column from agent_outputs ---
    op.drop_column("agent_outputs", "token_usage")

    # --- Drop task_metadata column from agent_tasks ---
    op.drop_column("agent_tasks", "task_metadata")

    # --- Drop status column from agents ---
    op.drop_column("agents", "status")
