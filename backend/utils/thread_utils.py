# Custom libraries
from logger import configure_logging

# Default libraries
import time
from uuid import uuid4

# Database modules
from repository.chat_thread_repository import ChatThreadRepository

logger = configure_logging(__name__)


def create_child_thread_for_execution(
    parent_thread_id: str, user_id: str, title: str, db
) -> str:
    """
    Create a child thread for Assistant task execution
    Returns the child thread ID
    """
    try:
        chat_thread_repository = ChatThreadRepository(db)

        # Get parent thread to inherit metadata
        parent_thread = chat_thread_repository.get_chat_thread_by_id(parent_thread_id)
        if not parent_thread:
            raise Exception(f"Parent thread {parent_thread_id} not found")

        # Extract parent metadata
        parent_metadata = parent_thread.chat_metadata or {}
        
        # Inherit relevant metadata from parent
        child_metadata = {}
        inherit_keys = ["web_search_enabled", "collections", "task_prompt"]
        for key in inherit_keys:
            if key in parent_metadata:
                child_metadata[key] = parent_metadata[key]

        # Generate execution timestamp for unique title
        timestamp = int(time.time() * 1000)

        child_thread_data = {
            "id": uuid4(),
            "title": f"{title}",
            "user_id": user_id,
            "parent_id": parent_thread_id,
            "is_archived": False,
            "chat_metadata": child_metadata,
            "chat_type": "task",
        }

        # Generate external_id
        child_thread_data["external_id"] = f"thread-{child_thread_data['id']}-{timestamp}"

        # Create the child thread
        result_child_thread = chat_thread_repository.create_chat_thread(
            child_thread_data
        )

        if not result_child_thread:
            raise Exception("Failed to create child thread")

        logger.info(
            f"Created child thread {result_child_thread.id} for parent {parent_thread_id} with metadata: {child_metadata}"
        )
        return str(result_child_thread.id)

    except Exception as e:
        logger.error(f"Error creating child thread: {e}")
        raise e