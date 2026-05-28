# backend/configs/triggers.py
"""
Triggers Configuration
======================
Event trigger definitions for integrations.

Each trigger defines:
- What event to listen for
- Which integration it belongs to
- How to poll for changes
- What the user needs to configure
- Which handler code to execute

Triggers use POLLING (not webhooks) for air-gapped compatibility.
"""

from typing import Dict, Any, List


# =============================================================================
# OUTLOOK TRIGGERS
# =============================================================================

OUTLOOK_TRIGGERS: List[Dict[str, Any]] = [
    {
        "slug": "outlook_new_email",
        "name": "New Email Received",
        "description": "Triggers when a new email arrives in the specified Outlook mailbox folder. Uses Microsoft Graph delta queries for efficient incremental sync.",
        "integration_key": "outlook",
        "is_enabled": True,
        "handler": {
            "module": "integrations.office_365.triggers_v4",
            "class": "OutlookTriggers",
            "method": "poll_new_emails",
        },
        "trigger_config": {
            "polling_method": "delta_query",
            "default_polling_interval": 300,  # 5 minutes
            "min_polling_interval": 60,  # 1 minute minimum
            "max_polling_interval": 3600,  # 1 hour maximum
        },
        "input_schema": {
            "type": "object",
            "title": "Email Trigger Configuration",
            "properties": {
                "mailbox_email": {
                    "type": "string",
                    "title": "Mailbox Email",
                    "description": "The email address of the mailbox to monitor",
                },
                "folder": {
                    "type": "string",
                    "title": "Folder",
                    "description": "The folder to monitor for new emails",
                    "default": "Inbox",
                    "enum": ["Inbox", "Drafts", "SentItems", "Archive", "JunkEmail"],
                },
            },
            "required": ["mailbox_email"],
        },
    },
]


# =============================================================================
# COMBINED TRIGGERS
# =============================================================================

ALL_TRIGGERS: List[Dict[str, Any]] = OUTLOOK_TRIGGERS

# Add more as needed:
# ALL_TRIGGERS = OUTLOOK_TRIGGERS + AWS_S3_TRIGGERS + SHAREPOINT_TRIGGERS
