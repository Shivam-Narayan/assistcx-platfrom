import os


class NotificationConfig:
    """Centralized configuration for the notification system"""

    # Template settings
    DEFAULT_TEMPLATE = "TASK_NOTIFICATION_TEMPLATE"
    LOGO_SIZE = 50

    # Company information
    COMPANY_NAME = "Aexonic Pvt Ltd"
    COMPANY_COPYRIGHT = "© 2025 Aexonic Pvt Ltd"

    # URLs
    NEXTAUTH_URL = os.getenv("NEXTAUTH_URL")

    # Email defaults
    DEFAULT_TASK_NAME = "Unnamed Task"
    DEFAULT_TASK_SUMMARY = "Task completed successfully"
    DEFAULT_DETAILED_OUTPUT = "Task output details not available"

    # Email subjects
    TASK_COMPLETION_SUBJECT_PREFIX = "Execution Completed:"
    EMAIL_FAILURE_SUBJECT = "Email Failure Report"

    # Button text
    CONTINUE_CONVERSATION_TEXT = "Continue conversation"

    @classmethod
    def get_chat_url(cls, chat_id: str) -> str:
        """Build chat URL from chat_id"""
        return f"{cls.NEXTAUTH_URL}/assistant/chat/{chat_id}"

    @classmethod
    def get_task_subject(cls, task_title: str) -> str:
        """Build task completion email subject"""
        return f"{cls.TASK_COMPLETION_SUBJECT_PREFIX} {task_title}"
