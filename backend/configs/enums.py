######################################################
### STALE REFERENCE, NOT BEING ACTIVELY MAINTAINED ###
######################################################
from enum import Enum


class APIType:
    REST = "REST"
    GraphQL = "GraphQL"
    SOAP = "SOAP"
    gRPC = "gRPC"
    OData = "OData"


class AuthType:
    None_ = "None"
    Basic = "Basic"
    Bearer = "Bearer"
    OAuth2 = "OAuth2"
    APIKey = "APIKey"


class EventType:
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    FAILURE = "FAILURE"


class HTTPMethod:
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class StepStatus:
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    INCOMPLETE = "INCOMPLETE"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"


class TaskStatus:
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    INCOMPLETE = "INCOMPLETE"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class ToolType:
    BASE_TOOL = "BASE_TOOL"
    REST_TOOL = "REST_TOOL"
    ODATA_TOOL = "ODATA_TOOL"
    MAIL_TOOL = "MAIL_TOOL"


class PollingStatus:
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


class NotificationType(str, Enum):
    TASK_FAILURE = "task_failure"
    TASK_INCOMPLETE = "task_incomplete"
    # TASK_UPDATED = "task_updated"

    # TASK_REVIEW_PENDING = "task_review_pending"
    # TASK_COMPLETED = "task_completed"
    # TASK_ASSIGNED = "task_assigned"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    # IN_APP = "in_app"
    # MS_TEAMS = "ms_teams"
    # SMS = "sms"
    # SLACK = "slack"
    # WEBHOOK = "webhook"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class DataFileStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    PARSING = "parsing"
    INDEXING = "indexing"
    SUCCESSFUL = "successful"
    FAILED = "failed"
