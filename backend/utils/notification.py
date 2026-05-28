# Custom libraries
from configs.notification_config import NotificationConfig
from configs.email_templates import (
    EMAIL_FAILURE_NOTIFICATION,
    TASK_FAILURE_NOTIFICATION,
    TASK_NOTIFICATION_TEMPLATE,
    ISSUE_NOTIFICATION_TEMPLATE,
    TASK_PAUSED_NOTIFICATION,
)
from integrations.office_365.outlook import Outlook
from logger import configure_logging

# Default libraries
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
import base64
import html
import pytz
import os
from uuid import UUID

# Database modules
from repository.agent_repository import AgentRepository
from repository.agent_task_repository import AgentTaskRepository
from repository.attachment_repository import AttachmentRepository
from repository.configuration_repository import ConfigurationRepository
from repository.mailbox_polling_repository import MailboxPollingRepository
from repository.email_repository import EmailRepository
from repository.user_repository import UserRepository
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# Installed libraries
from premailer import transform
import markdown


logger = configure_logging(__name__)


class Notification:
    """
    Manages notification events related to emails and tasks.

    This class handles:
      - Email failure notifications
      - Task failure notifications
      - Scheduled task completion notifications

    Attributes:
        db [Session]: Database session.
    """

    def __init__(self, db: Session = None):
        self.db = db

    def _apply_defaults(self, task_details: Dict) -> Dict:
        """
        Applies default task values and injects logo/button UI components.

        Args:
            task_details (Dict): Dict of task-related details, which may include optional values.

        Returns:
            Dict[str, Any]: Task details with defaults and UI components applied.
        """
        svg_data_uri = self._process_logo()

        defaults = {
            "task_name": task_details.get(
                "task_name", NotificationConfig.DEFAULT_TASK_NAME
            ),
            "task_summary": task_details.get(
                "task_summary", NotificationConfig.DEFAULT_TASK_SUMMARY
            ),
            "execution_time": task_details.get(
                "execution_time", datetime.now().strftime("%I:%M %p")
            ),
            "execution_date": task_details.get(
                "execution_date", datetime.now().strftime("%B %d, %Y")
            ),
            "detailed_output_content": task_details.get(
                "detailed_output_content", NotificationConfig.DEFAULT_DETAILED_OUTPUT
            ),
            "assistcx_logo": svg_data_uri,
        }

        continue_chat_url = task_details.get("continue_chat_url", "#")
        task_details["button_section"] = self._generate_button_html(continue_chat_url)

        for key, default_value in defaults.items():
            if key not in task_details:
                task_details[key] = default_value

        return task_details

    def _generate_button_html(self, continue_chat_url: str) -> str:
        """
        Generates clickable or disabled button based on URL availability.

        Args:
            continue_chat_url (str): URL for continuing the chat. If None or '#', a disabled button is generated.

        Returns:
            str: HTML string for the button section.
        """
        if continue_chat_url and continue_chat_url != "#":
            return """
            <tr>
            <td class="button-cell">
                <a href="{}" class="continue-btn">{}</a>
            </td>
            </tr>
            """.format(
                continue_chat_url, NotificationConfig.CONTINUE_CONVERSATION_TEXT
            )
        else:
            return """
            <tr>
            <td class="button-cell">
                <span class="continue-btn" style="background-color: #ccc; cursor: not-allowed; color: #666;">{}</span>
            </td>
            </tr>
            """.format(
                NotificationConfig.CONTINUE_CONVERSATION_TEXT
            )
        
    def _prepare_failure_notification_email(self, notification_details):
        """
        Generates failure notification email HTML by processing data and rendering template.
        
        Args:
            notification_details (Dict): Details about the failure event.

        Returns:
            str: Rendered HTML email content.
        """
        template = (
            TASK_FAILURE_NOTIFICATION
            if notification_details.get("task_id")
            else EMAIL_FAILURE_NOTIFICATION
        )
        return self._render_template(template, notification_details)

    def _prepare_paused_notification_email(self, notification_details):
        """
        Generates paused-task notification email HTML by rendering the template.

        Args:
            notification_details (Dict): Details about the paused task event.

        Returns:
            str: Rendered HTML email content.
        """
        return self._render_template(TASK_PAUSED_NOTIFICATION, notification_details)

    def _prepare_task_email(self, task_details):
        """
        Generates task notification email HTML by processing data and rendering template.
        
        Args:
            task_details (Dict): Details about the task event.

        Returns:
            str: Rendered HTML email content.
        """
        template = TASK_NOTIFICATION_TEMPLATE
        processed_data = self._apply_defaults(task_details)
        return self._render_template(template, processed_data)

    def _process_logo(self) -> str:
        """
        Converts SVG logo to base64 for email compatibility.
        
        Returns:
            str: HTML img tag with embedded base64 SVG logo.
        """
        svg_bytes = '<svg width="256" height="256" viewBox="0 0 256 256" fill="none" xmlns="http://www.w3.org/2000/svg"><g clip-path="url(#clip0_805_2)"> <circle cx="128" cy="128" r="128" fill="#0F172A"/><path d="M195.085 173H66.915L131 62L195.085 173Z" stroke="white" stroke-width="26"/><path d="M83.6531 206.262L173 50" stroke="#0F172A" stroke-width="36"/></g><defs><clipPath id="clip0_805_2"><rect width="256" height="256" fill="white"/></clipPath></defs></svg>'.encode("utf-8")
        svg_base64 = base64.b64encode(svg_bytes).decode("utf-8")
        logo_size = NotificationConfig.LOGO_SIZE
        return f'<img src="data:image/svg+xml;base64,{svg_base64}" alt="AssistCX Logo" style="width: {logo_size}px; height: {logo_size}px; display: block;">'

    def _render_template(self, template_content: str, data: Dict) -> str:
        """
        Renders the email template by replacing placeholders with actual data.

        Args:
            template_content (str): Email template content with placeholders.
            data (Dict): Dict containing data to replace in the template.

        Returns:
            str: Rendered email content.
        """
        template = template_content
        for key, value in data.items():
            placeholder = f"{{{key}}}"
            if placeholder in template:
                template = template.replace(placeholder, str(value))
            else:
                logger.warning(f"Placeholder {placeholder} not found in template")
        return template

    @staticmethod
    def markdown_to_email_html(markdown_text: str) -> str:
        """
        Converts markdown to email-safe HTML.
        
        Args:
            markdown_text (str): Input markdown text.

        Returns:
            str: Email-safe HTML content.
        """
        try:
            html = markdown.markdown(
                markdown_text, extensions=["extra", "codehilite", "toc", "nl2br"]
            )
            email_safe_html = transform(
                html,
                strip_important=False,
                css_text="""
                /* Headers */
                h1 { 
                    color: #1d1d1f; 
                    margin: 20px 0 15px 0; 
                    font-size: 24px; 
                    font-weight: 600;
                    line-height: 1.3;
                }
                h2 { 
                    color: #1d1d1f; 
                    margin: 18px 0 12px 0; 
                    font-size: 20px; 
                    font-weight: 600;
                    line-height: 1.3;
                }
                h3 { 
                    color: #1d1d1f; 
                    margin: 15px 0 10px 0; 
                    font-size: 18px; 
                    font-weight: 600;
                    line-height: 1.3;
                }
                h4, h5, h6 { 
                    color: #1d1d1f; 
                    margin: 12px 0 8px 0; 
                    font-weight: 600;
                    line-height: 1.3;
                }
                
                /* Paragraphs */
                p { 
                    margin: 12px 0; 
                    line-height: 1.6; 
                    color: #1d1d1f;
                }
                
                /* Lists */
                ul, ol { 
                    margin: 12px 0; 
                    padding-left: 25px; 
                    color: #1d1d1f;
                }
                li { 
                    margin: 6px 0; 
                    line-height: 1.5;
                }
                
                /* Text formatting */
                strong, b { 
                    font-weight: 700; 
                    color: #1d1d1f;
                }
                em, i { 
                    font-style: italic;
                }
                
                /* Code formatting */
                code { 
                    background-color: #f5f5f7; 
                    padding: 3px 6px; 
                    border-radius: 4px; 
                    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
                    font-size: 14px;
                    color: #d73a49;
                    border: 1px solid #e1e4e8;
                }
                
                /* Code blocks */
                pre { 
                    background-color: #f6f8fa; 
                    padding: 16px; 
                    border-radius: 6px; 
                    overflow-x: auto;
                    margin: 16px 0;
                    border: 1px solid #e1e4e8;
                }
                pre code {
                    background: none;
                    padding: 0;
                    border: none;
                    color: #24292e;
                }
                
                /* Tables */
                table {
                    border-collapse: collapse;
                    width: 100%;
                    margin: 16px 0;
                    border: 1px solid #e1e4e8;
                }
                th, td {
                    border: 1px solid #e1e4e8;
                    padding: 8px 12px;
                    text-align: left;
                }
                th {
                    background-color: #f6f8fa;
                    font-weight: 600;
                }
                
                /* Blockquotes */
                blockquote {
                    margin: 16px 0;
                    padding: 0 16px;
                    color: #6a737d;
                    border-left: 4px solid #dfe2e5;
                    background-color: #f6f8fa;
                    padding: 16px;
                    border-radius: 0 6px 6px 0;
                }
                
                /* Links */
                a {
                    color: #0366d6;
                    text-decoration: none;
                }
                a:hover {
                    text-decoration: underline;
                }
                
                /* Horizontal rules */
                hr {
                    border: none;
                    height: 1px;
                    background-color: #e1e4e8;
                    margin: 24px 0;
                }
                """,
            )
            return email_safe_html
        except Exception as e:
            logger.error(f"Markdown conversion failed: {e}")
            fallback_html = markdown_text.replace("\n\n", "</p><p>").replace(
                "\n", "<br>"
            )
            return f"<p>{fallback_html}</p>".replace("<p></p>", "")

    def notify_email_failure(self, email_id, failed_process):
        """
        Sends a failure notification email when email processing fails.

        Args:
            email_id (UUID): UUID of the email that failed processing.
            failed_process (str): Description of the failed process (e.g., "Attachment Processing", "Task Dispatch").
        """
        try:
            email_repository = EmailRepository(self.db)
            email = email_repository.get_email_by_id(email_id)
            if not email:
                logger.warning(f"Email not found: {email_id}")
                return

            task_name = f"{email.mailbox_email}|{email.mailbox_folder}"
            mailbox_polling_repository = MailboxPollingRepository(self.db)
            mailbox_polling = mailbox_polling_repository.get_mailbox_polling(task_name)
            polling_config = mailbox_polling.polling_config if mailbox_polling else None

            if not polling_config or not polling_config.get("send_notifications"):
                logger.info(f"Notifications are disabled for email: {email_id}")
                return

            notification_recipients = polling_config.get("notification_recipients", [])
            if not notification_recipients:
                logger.info(f"Notification recipients not found for email: {email_id}")
                return

            attachment_repository = AttachmentRepository(self.db)
            attachment_details = attachment_repository.list_attachment_by_email(
                email_id
            )
            attachments = attachment_details.get("attachments", [])
            attachment_names = (
                ", ".join(attachment.file_name for attachment in attachments)
                if attachments
                else "None"
            )

            if failed_process == "Attachment Processing":
                failure_reason = (
                    "likely caused by an unsupported format or errors "
                    "encountered while extracting the attachment’s content"
                )
            elif failed_process == "Task Dispatch":
                failure_reason = "likely due to an error while dispatching the email"

            # Prepare email link
            frontend_base = os.getenv("NEXTAUTH_URL")
            email_link = (
                f'<a href="{frontend_base}/inbox/{email.id}">View Email</a>'
                if frontend_base
                else "URL not available"
            )

            # Prepare notification details
            notification_details = {
                "sender_email": email.email_id,
                "mailbox_email": email.mailbox_email,
                "mailbox_folder": email.mailbox_folder,
                "subject": email.subject,
                "failed_process": failed_process,
                "failure_reason": failure_reason,
                "received_at": email.received_at,
                "email_id": email.id,
                "email_status": email.status,
                "attachment_names": attachment_names,
                "email_link": email_link,
            }

            subject = f"Email Failure Report | Email ID : {email_id}"
            email_body = self._prepare_failure_notification_email(notification_details)
            email_data = {"body": email_body, "subject": subject}

            outlook = Outlook(self.db)
            outlook.send_email(
                email.mailbox_email,
                notification_recipients,
                email_data,
            )
            logger.info(
                f"Email failure notification sent to {notification_recipients} for email: {email_id}"
            )

        except Exception as e:
            logger.error(f"An error occurred in notify_email_failure: {e}")

    def notify_task_failure(self, email_id, task_id, failed_process):
        """
        Sends a failure notification email when task processing fails.

        Args:
            task_id (UUID): UUID of the task that failed processing.
            failed_process (str): Description of the failed process (e.g., "Task Execution").
        """
        try:
            email_repository = EmailRepository(self.db)
            email = email_repository.get_email_by_id(email_id)
            if not email:
                logger.warning(f"Email not found: {email_id}")
                return

            agent_task_repository = AgentTaskRepository(self.db)
            agent_task = agent_task_repository.get_task_by_id(task_id)
            if not agent_task:
                logger.warning(f"Agent Task not found: {task_id}")
                return

            task_name = f"{email.mailbox_email}|{email.mailbox_folder}"
            mailbox_polling_repository = MailboxPollingRepository(self.db)
            mailbox_polling = mailbox_polling_repository.get_mailbox_polling(task_name)
            polling_config = mailbox_polling.polling_config if mailbox_polling else None

            if not polling_config or not polling_config.get("send_notifications"):
                logger.info(f"Notifications are disabled for email: {email_id}")
                return

            notification_recipients = polling_config.get("notification_recipients", [])
            if not notification_recipients:
                logger.info(f"Notification recipients not found for email: {email_id}")
                return

            agent_repository = AgentRepository(self.db)
            agent = agent_repository.get_agent(agent_task.agent_id)

            task_status = (
                agent_task.progress[-1]["status"] if agent_task.progress else None
            )

            attachment_names = (
                ", ".join(
                    attachment.get("name") for attachment in agent_task.attachments
                )
                if agent_task.attachments
                else "None"
            )

            # Prepare task link
            frontend_base = os.getenv("NEXTAUTH_URL")
            task_link = (
                f'<a href="{frontend_base}/inbox/tasks/{agent_task.id}">View Task</a>'
                if frontend_base
                else "URL not available"
            )

            # Prepare notification details
            notification_details = {
                "sender_email": email.email_id,
                "mailbox_email": email.mailbox_email,
                "mailbox_folder": email.mailbox_folder,
                "subject": email.subject,
                "failed_process": failed_process,
                "assigned_agent": agent.name,
                "received_at": email.received_at,
                "task_id": agent_task.id,
                "task_status": task_status,
                "attachment_names": attachment_names,
                "task_order": agent_task.task_order,
                "task_link": task_link,
            }

            subject = f"Task Failure Report | Task ID : {task_id}"
            email_body = self._prepare_failure_notification_email(notification_details)
            email_data = {"body": email_body, "subject": subject}

            outlook = Outlook(self.db)
            outlook.send_email(
                email.mailbox_email,
                notification_recipients,
                email_data,
            )
            logger.info(
                f"Email failure notification sent to {notification_recipients} for task: {task_id}"
            )

        except Exception as e:
            logger.error(f"An error occurred in notify_task_failure: {e}")

    def notify_task_paused(self, task_id, agent_data, task_data, pending_review, reviewer_user_ids):
        """
        Sends a notification email to the agent's configured reviewers when a task
        is paused for human review.

        Args:
            task_id (UUID): UUID of the paused task.
            agent_data (AgentDetail): Agent record that owns the task.
            task_data (AgentTaskDetail): The task that was paused.
            pending_review (Dict): Interrupt payload from the graph containing
                tool_name, tool_call_id, tool_args, review_rules, and question.
            reviewer_user_ids (List[str]): List of user UUIDs from agent_config.human_review_users.
        """
        try:
            configuration_repository = ConfigurationRepository(self.db)
            configuration = configuration_repository.get_configuration()

            default_email = (
                configuration.preferences.get("default_email")
                if configuration
                else None
            )
            if not default_email:
                logger.warning("No default email configured - paused task notification not sent")
                return

            attachment_names = (
                ", ".join(
                    attachment.get("name") for attachment in task_data.attachments
                )
                if task_data.attachments
                else "None"
            )

            # Prepare task url
            frontend_base = os.getenv("NEXTAUTH_URL")
            task_url = (
                f"{frontend_base}/inbox/tasks/{task_id}"
                if frontend_base
                else "#"
            )

            # Prepare base notification details (shared across all reviewers)
            notification_details_base = {
                "agent_name": agent_data.name,
                "task_title": task_data.title or "Untitled Task",
                "task_id": str(task_id),
                "tool_name": pending_review.get("tool_name", "N/A") if pending_review else "N/A",
                "review_question": (
                    pending_review.get("question") or "No question provided"
                    if pending_review
                    else "N/A"
                ),
                "task_status": "PAUSED",
                "attachment_names": attachment_names,
                "paused_at": datetime.now().strftime("%B %d, %Y %I:%M %p"),
                "task_url": task_url,
            }

            user_repository = UserRepository(self.db)
            outlook = Outlook(self.db)
            sent_count = 0
            subject = f"Task Paused Report | Task ID : {task_id}"

            for uid in reviewer_user_ids:
                try:
                    user = user_repository.get_user_by_id(UUID(str(uid)))
                    if not user or not getattr(user, "email", None):
                        logger.warning(f"Reviewer user not found or has no email: {uid}")
                        continue

                    # Build personalized name with fallback
                    reviewer_name = (user.first_name or "").strip() or "Team"

                    # Prepare notification details
                    notification_details = {**notification_details_base, "reviewer_name": reviewer_name}

                    email_body = self._prepare_paused_notification_email(notification_details)
                    email_data = {"body": email_body, "subject": subject}

                    outlook.send_email(default_email, [user.email], email_data)
                    sent_count += 1

                except (ValueError, TypeError):
                    logger.warning(f"Invalid reviewer user id: {uid}")

            if sent_count == 0:
                logger.info(
                    f"Notification recipients not found for task: {task_id}"
                )
                return

            logger.info(
                f"Task paused notification sent to {sent_count} reviewer(s) for task: {task_id}"
            )

        except Exception as e:
            logger.error(f"An error occurred in notify_task_paused: {e}")

    def prepare_task_notification_data(
        self, answer: str, title: str, task_prompt: str
    ) -> Dict:
        """
        Prepares scheduled task data for sending email notifications.

        Args:
            answer (str): Detailed answer or output from the task.
            title (str): Title of the task.
            task_prompt (str): Prompt or summary of the task.

        Returns:
        Dict: Details of structured task notification data including:
            - task_name (str): Task title.
            - task_summary (str): Task summary or prompt.
            - execution_time (str): Time the task was executed.
            - execution_date (str): Date the task was executed.
            - detailed_output_content (str)): HTML-formatted detailed output of the task.
        """
        try:
            current_time = datetime.now()

            # Use task_prompt as the summary (main box content) instead of extracting from answer
            task_summary = (
                task_prompt if task_prompt else NotificationConfig.DEFAULT_TASK_SUMMARY
            )

            # Process detailed content
            if answer:
                detailed_output = Notification.markdown_to_email_html(answer)
            else:
                detailed_output = f"<p><strong>Task executed successfully</strong></p>"

            return {
                "task_name": title,
                "task_summary": task_summary,
                "execution_time": current_time.strftime("%I:%M %p"),
                "execution_date": current_time.strftime("%B %d, %Y"),
                "detailed_output_content": detailed_output,
            }

        except Exception as e:
            logger.error(f"Failed to prepare notification data: {e}")
            raise
    
    def send_task_notification(self, notification_recipients, task_details):
        """
        Sends a notification email for scheduled task responses.

        Args:
            notification_recipients (List[str]): List of email addresses to notify.
            task_details (Dict): Details of the scheduled task.
        """
        try:
            configuration_repository = ConfigurationRepository(self.db)
            configuration = configuration_repository.get_configuration()

            default_email = (
                configuration.preferences.get("default_email")
                if configuration
                else None
            )

            if not default_email:
                logger.warning("No default email configured - notification not sent")
                return

            subject = NotificationConfig.get_task_subject(
                task_details.get("task_name", NotificationConfig.DEFAULT_TASK_NAME)
            )
            email_body = self._prepare_task_email(task_details)
            email_data = {"body": email_body, "subject": subject}

            outlook = Outlook(self.db)
            outlook.send_email(default_email, notification_recipients, email_data)
            logger.info(f"Task notification sent to {notification_recipients}")

        except Exception as e:
            logger.error(f"Failed to send task notification: {e}")

    def send_platform_alert_notification(self, notification_recipients: list, alert_payload: Dict) -> bool:
        """
        Sends a notification email for platform alerts (e.g., Grafana alerts).

        Args:
            notification_recipients (List[str]): List of email addresses to notify.
            alert_payload (Dict): The alert payload received from the monitoring system.

        Returns:
            bool: True if email was sent successfully, False otherwise.
        """
        try:
            configuration_repository = ConfigurationRepository(self.db)
            configuration = configuration_repository.get_configuration()

            default_email = (
                configuration.preferences.get("default_email")
                if configuration
                else None
            )

            if not default_email:
                logger.warning("No default email configured - alert notification not sent")
                return False

            # Format the JSON payload into a readable email body
            import json
            formatted_alert = json.dumps(alert_payload, indent=2)

            email_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; }}
                    .alert-container {{ background-color: #f5f5f5; padding: 20px; border-radius: 5px; }}
                    pre {{ background-color: #ffffff; padding: 15px; border: 1px solid #ddd; border-radius: 3px; overflow-x: auto; }}
                </style>
            </head>
            <body>
                <div class="alert-container">
                    <h2>Platform Alert Notification</h2>
                    <p>A new alert has been received from the monitoring system:</p>
                    <pre>{formatted_alert}</pre>
                </div>
            </body>
            </html>
            """

            subject = "Platform Alert Notification"
            email_data = {"body": email_body, "subject": subject}

            outlook = Outlook(self.db)
            email_sent = outlook.send_email(default_email, notification_recipients, email_data)

            if email_sent:
                logger.info(f"Platform alert notification sent to {notification_recipients}")
            else:
                logger.error(f"Failed to send platform alert notification to {notification_recipients}")

            return email_sent

        except Exception as e:
            logger.error(f"Failed to send platform alert notification: {e}")
            return False

    # ==================== Issue Notification Methods ====================

    def notify_issue(
        self,
        issue,
        event_type: str,
        actor_user_id: str,
        **event_data,
    ) -> None:
        """
        Send issue notification (comment, status_changed, or edited).
        Recipients from issue.subscribed; actor excluded. Event time from DB (like task received_at).
        """
        try:
            configuration_repository = ConfigurationRepository(self.db)
            configuration = configuration_repository.get_configuration()
            default_email = configuration.preferences.get("default_email") if configuration else None
            if not default_email:
                logger.warning("No default email configured - issue notification not sent")
                return

            subscribed_user_ids = issue.subscribed or []
            recipient_ids = [
                uid for uid in subscribed_user_ids
                if str(uid) != str(actor_user_id)
            ]
            user_repository = UserRepository(self.db)
            recipient_emails = []
            for uid in recipient_ids:
                try:
                    user_id = UUID(str(uid))
                    user = user_repository.get_user_by_id(user_id)
                    if user and getattr(user, "email", None):
                        recipient_emails.append(user.email)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid user id: {uid}")
            if not recipient_emails:
                logger.info("No recipients to notify for issue: %s", issue.id)
                return

            frontend_base = os.getenv("NEXTAUTH_URL")
            issue_link = (
                f'<a href="{frontend_base}/issues/{issue.id}">View Issue</a>'
                if frontend_base
                else "URL not available"
            )
            issue_title_escaped = html.escape(issue.title)

            # Get timezone from configuration (default to UTC if not set)
            config_timezone = configuration.preferences.get("timezone", "UTC") if configuration else "UTC"
            if event_type == "comment":
                comment = event_data.get("comment")
                issue_event_at = getattr(comment, "created_at", None) if comment else None
            else:
                issue_event_at = getattr(issue, "updated_at", None)
            try: 
                tz = pytz.timezone(config_timezone or "UTC")
                issue_event_at_str = issue_event_at.astimezone(tz).strftime("%B %d, %Y") if issue_event_at else "N/A"
            except Exception:
                issue_event_at_str = issue_event_at.strftime("%B %d, %Y") if issue_event_at else "N/A"

            if event_type == "comment":
                comment = event_data.get("comment")
                commenter_name = event_data.get("commenter_name", "")
                comment_content = (comment.comment or "No content") if comment else "No content"
                subject = f"Issue Comment Report: {issue.title}"
                issue_heading = "New Comment on Issue"
                issue_intro = f'<strong>{html.escape(commenter_name)}</strong> added a comment to "<strong>{issue_title_escaped}</strong>".'
                issue_highlight = f'<div class="highlight-box"><strong>Comment:</strong><br/>{html.escape(comment_content)}</div>' if comment_content else ""
                issue_detail_rows = [
                    ("Issue Title", issue.title),
                    ("Comment By", commenter_name),
                    # ("Commented At", issue_event_at_str),
                ]

            elif event_type == "status_changed":
                old_status = event_data.get("old_status", "").title()
                new_status = event_data.get("new_status", "").title()
                reason = event_data.get("reason") or "No reason provided"
                changed_by_name = event_data.get("changed_by_name", "")
                subject = f"Issue Status Report: {issue.title}"
                issue_heading = "Issue Status Changed"
                issue_intro = f'Status of "<strong>{issue_title_escaped}</strong>" was changed by <strong>{html.escape(changed_by_name)}</strong>.'
                issue_highlight = (
                    f'<div class="highlight-box">'
                    f'<span class="status-old">{html.escape(old_status)}</span> → <span class="status-new">{html.escape(new_status)}</span><br/>'
                    f'<strong>Reason:</strong> {html.escape(reason)}</div>'
                )
                issue_detail_rows = [
                    ("Issue Title", issue.title),
                    ("Previous Status", old_status),
                    ("New Status", new_status),
                    ("Reason", reason),
                    ("Changed By", changed_by_name),
                    # ("Event At", issue_event_at_str),
                ]

            else:
                edited_by_name = event_data.get("edited_by_name", "")
                changes_summary = event_data.get("changes_summary") or "Issue details were updated."
                subject = f"Issue Edit Report: {issue.title}"
                issue_heading = "Issue Edited"
                issue_intro = f'Issue "<strong>{issue_title_escaped}</strong>" was edited by <strong>{html.escape(edited_by_name)}</strong>.'
                issue_highlight = f'<div class="highlight-box"><strong>Changes:</strong><br/>{html.escape(changes_summary)}</div>' if changes_summary else ""
                issue_detail_rows = [
                    ("Issue Title", issue.title),
                    ("Description", issue.description or "No description"),
                    ("Edited By", edited_by_name),
                    # ("Event At", issue_event_at_str),
                ]

            issue_details_rows = "\n        ".join(
                f'<tr><td>{html.escape(str(label))}</td><td>{html.escape(str(value))}</td></tr>'
                for label, value in issue_detail_rows
            )
            template_data = {
                "issue_heading": issue_heading,
                "issue_intro": issue_intro,
                "issue_highlight": issue_highlight,
                "issue_details_rows": issue_details_rows,
                "issue_link": issue_link,
            }
            email_body = self._render_template(ISSUE_NOTIFICATION_TEMPLATE, template_data)
            email_data = {"body": email_body, "subject": subject}

            outlook = Outlook(self.db)
            outlook.send_email(default_email, recipient_emails, email_data)
            logger.info("Issue notification sent to %s for issue: %s", recipient_emails, issue.id)
        except Exception as e:
            logger.error("An error occurred in notify_issue: %s", e)
