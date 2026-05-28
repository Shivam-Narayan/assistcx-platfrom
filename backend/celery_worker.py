import os
from celery import Celery
from logger import configure_logging

logger = configure_logging(__name__)

# Configure the broker URL and backend (Redis)
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
WORKER_TASK_TIMEOUT = int(os.getenv("WORKER_TASK_TIMEOUT", "3600"))

# Create the Celery app
celery = Celery(
    "celery_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_prefetch_multiplier=1,
)

# Redis connection pool settings
# Increased for handling 500+ email bursts with chords
celery.conf.broker_pool_limit = 300  # Support high-volume chord operations
celery.conf.redis_max_connections = 300  # Max Redis connections
celery.conf.broker_connection_max_retries = None  # Infinite retries (never give up)
celery.conf.broker_connection_retry = True  # Enable retries
celery.conf.broker_connection_timeout = 30  # Connection timeout
celery.conf.broker_heartbeat = 30  # Match the timeout

# Task processing configuration
celery.conf.task_acks_late = True
celery.conf.task_reject_on_worker_lost = True
celery.conf.worker_prefetch_multiplier = 1
celery.conf.task_track_started = True

# Task timeout and retry controls
celery.conf.task_time_limit = WORKER_TASK_TIMEOUT  # Hard limit from env
celery.conf.task_soft_time_limit = int(WORKER_TASK_TIMEOUT * 0.9)  # 90% of hard limit
celery.conf.task_default_retry_delay = 30  # 30 seconds retry delay
celery.conf.task_max_retries = 1  # Retry once (2 total attempts)
celery.conf.worker_disable_rate_limits = False

# Task routing configuration with priorities
# NOTE: In Celery, lower number = HIGHER priority (0=highest, 9=lowest)
celery.conf.task_routes = {
    "process_attachment": {"queue": "attachment_queue"},
    "parse_attachment": {"queue": "attachment_queue"},
    "process_task_attachments": {"queue": "attachment_queue"},
    "dispatch_task": {"queue": "agent_queue"},
    "execute_task": {"queue": "agent_queue"},
    "finalize_email": {"queue": "agent_queue"},
    "index_document": {"queue": "knowledge_queue", "priority": 9},  # Low priority
    "extract_knowledge": {"queue": "knowledge_queue", "priority": 0},  # High priority
}

# Broker transport options
# Using 2 priority levels for simplicity: 0=high, 9=low
celery.conf.broker_transport_options = {
    "priority_steps": [0, 9],  # 2 levels only
    "sep": ":",
    "queue_order_strategy": "priority",
    "visibility_timeout": 7200,  # 2 hours
    "fanout_prefix": True,
    "fanout_patterns": True,
}

# Task serializer
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.accept_content = ["json"]

# RedBeat specific configuration
celery.conf.beat_scheduler = "redbeat.RedBeatScheduler"
celery.conf.redbeat_redis_url = CELERY_BROKER_URL
celery.conf.beat_max_loop_interval = 30
celery.conf.task_send_sent_event = True
celery.conf.broker_connection_retry_on_startup = True

# Result expiration - CRITICAL for chord reliability
celery.conf.result_expires = 14400  # 4 hours

# Import tasks from worker modules
celery.autodiscover_tasks(
    [
        "workers.backend_worker",
        "workers.attachment_worker",
        "workers.agent_worker",
        "workers.knowledge_worker",
        "workers.task_source_worker_v4",
    ]
)


