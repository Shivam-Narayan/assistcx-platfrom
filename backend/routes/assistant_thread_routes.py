"""
Chat Threads & Messages routes.
"""

from agents.assistant_services.query_service import AssistantQueryService
from logger import configure_logging
from schemas.chat_message_schema import (
    ChatMessageCreate,
    ChatMessageDetail,
    ChatMessageUpdate,
    GraphStateContext,
)
from schemas.chat_thread_schema import (
    ChatHistoryCreate,
    ChatHistoryDetail,
    ChatHistoryUpdate,
)
from schemas.user_schema import Message
from utils.schema_utils import get_schema_db

from repository.chat_thread_repository import ChatThreadRepository
from sqlalchemy.orm import Session

from typing import List, Optional
from uuid import UUID, uuid4
import os
import time

from asgiref.sync import sync_to_async
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt import decode


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """Extract user_id from JWT token."""
    decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
    return decoded_token["sub"]


# =============================================================================
# SECTION 3: CHAT THREADS & MESSAGES  (tag: "Assistant Threads")
# =============================================================================

thread_router = APIRouter(tags=["Assistant Threads"])


@thread_router.get("/assistant/chat-threads", response_model=List[ChatHistoryDetail])
@thread_router.get(
    "/assistant/chat-threads/search",
    response_model=List[ChatHistoryDetail],
    deprecated=True,
    include_in_schema=False,
)
def get_chat_threads(
    keyword: Optional[str] = Query(None, description="Search keyword (optional)"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
    request: Request = None,
):
    """List or search chat threads for the authenticated user.

    If keyword is provided, searches threads by keyword. Otherwise lists all threads.
    """
    try:
        user_uuid = get_current_user_id(token)
        chat_thread_repository = ChatThreadRepository(db)
        request_filters = request.state.filters

        if keyword:
            chat_threads = chat_thread_repository.search_chat_threads_by_user_id(
                user_id=user_uuid,
                keyword=keyword,
                page=page,
                page_size=page_size,
                filters=request_filters,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            return chat_threads if chat_threads else []
        else:
            return chat_thread_repository.get_chat_threads_by_user_id(
                user_id=user_uuid,
                page=page,
                page_size=page_size,
                filters=request_filters,
                sort_by=sort_by,
                sort_order=sort_order,
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_chat_threads: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@thread_router.get(
    "/assistant/chat-threads/{chat_thread_identifier}", response_model=ChatHistoryDetail
)
def get_chat_thread(
    chat_thread_identifier: UUID,
    db: Session = Depends(get_schema_db),
):
    """Retrieves a chat thread by its identifier."""
    try:
        chat_thread_repository = ChatThreadRepository(db)

        if chat_thread_identifier:
            chat_thread = chat_thread_repository.get_chat_thread_by_id(
                chat_thread_identifier
            )
            if chat_thread:
                return chat_thread
            else:
                raise HTTPException(
                    status_code=404,
                    detail="Chat Thread not found. Please check and retry.",
                )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_chat_thread: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@thread_router.get(
    "/assistant/chat-threads/{chat_thread_uuid}/chat-messages",
    response_model=List[ChatMessageDetail],
)
async def get_chat_messages_by_chat_thread(
    chat_thread_uuid: UUID,
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """Retrieves chat messages with enriched graph state context for assistant messages."""
    try:
        chat_thread_repository = ChatThreadRepository(db)
        org_schema = getattr(request.state, "org_id", "public")
        user_id = getattr(request.state, "user_id", None)

        request_filters = request.state.filters

        messages = await sync_to_async(chat_thread_repository.get_thread_messages)(
            chat_thread_uuid, page, page_size, request_filters
        )

        if not messages:
            return []

        # Use AssistantQueryService for observe_query_execution
        assistant_service = AssistantQueryService(
            db=db, org_schema=org_schema, user_id=user_id
        )

        enriched_messages = []

        for message in messages:
            message_with_state = ChatMessageDetail(
                id=message.id,
                chat_history_id=message.chat_history_id,
                role=message.role,
                content=message.content,
                context=message.context,
                feedback=message.feedback,
                message_metadata=message.message_metadata,
                token_usage=message.token_usage,
                credits_used=message.credits_used,
                created_at=message.created_at,
                updated_at=message.updated_at,
                graph_state=None,
            )

            if message.role == "assistant" and message.context:
                graph_thread_id = message.context.get("graph_thread_id")

                if graph_thread_id:
                    try:
                        async for (
                            state_data
                        ) in assistant_service.observe_query_execution(
                            thread_id=graph_thread_id, poll_interval=None
                        ):
                            if state_data.get("type") != "error":
                                message_with_state.graph_state = GraphStateContext(
                                    graph_thread_id=graph_thread_id,
                                    original_query=state_data.get("original_query"),
                                    relevant_sources=state_data.get("relevant_sources"),
                                    research_knowledge=state_data.get(
                                        "research_knowledge"
                                    ),
                                    suggested_queries=state_data.get(
                                        "suggested_queries"
                                    ),
                                    query_type=state_data.get("query_type"),
                                    title=state_data.get("title"),
                                    messages=state_data.get("messages"),
                                    metadata=state_data.get("metadata"),
                                    research_complete=state_data.get("research_complete"),
                                )
                            break
                    except Exception as observe_error:
                        logger.warning(
                            f"Failed to observe graph state for thread {graph_thread_id}: {observe_error}"
                        )

            enriched_messages.append(message_with_state)

        return enriched_messages

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_chat_messages_by_chat_thread: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@thread_router.post("/assistant/chat-threads", response_model=ChatHistoryDetail)
def create_chat_thread(
    chat_thread_data: ChatHistoryCreate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """Creates a new chat thread."""
    try:
        decoded_token = decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
        user_uuid = UUID(decoded_token["sub"])

        chat_thread_repository = ChatThreadRepository(db)

        chat_thread = chat_thread_data.model_dump()
        chat_thread["user_id"] = str(user_uuid)
        chat_thread["id"] = uuid4()
        chat_thread["external_id"] = (
            f"thread-{chat_thread['id']}-{int(time.time() * 1000)}"
        )

        result_chat_thread = chat_thread_repository.create_chat_thread(chat_thread)

        if result_chat_thread:
            logger.info(f"Chat Thread created successfully: {result_chat_thread.id}")
            return ChatHistoryDetail.model_validate(result_chat_thread)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Chat Thread.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_chat_thread: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@thread_router.patch(
    "/assistant/chat-threads/{chat_thread_uuid}", response_model=ChatHistoryDetail
)
def update_chat_thread(
    chat_thread_uuid: UUID,
    chat_thread_data: ChatHistoryUpdate = Body(...),
    db: Session = Depends(get_schema_db),
    token: str = Depends(oauth2_scheme),
):
    """Updates an existing chat thread."""
    try:
        chat_thread_repository = ChatThreadRepository(db)

        update_data = {
            k: v for k, v in chat_thread_data.model_dump().items() if v is not None
        }
        update_data["chat_thread_uuid"] = chat_thread_uuid

        result_chat_thread = chat_thread_repository.update_chat_thread(update_data)

        if result_chat_thread:
            logger.info(f"Chat Thread updated successfully: {result_chat_thread.id}")
            return ChatHistoryDetail.model_validate(result_chat_thread)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Chat Thread. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_chat_thread: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@thread_router.post("/assistant/chat-messages", response_model=ChatMessageDetail)
def create_chat_message(
    chat_message_data: ChatMessageCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """Creates a new chat message."""
    try:
        chat_thread_repository = ChatThreadRepository(db)

        result_chat_message = chat_thread_repository.create_thread_message(
            chat_message_data.model_dump()
        )

        if result_chat_message:
            logger.info(f"Chat Message created successfully: {result_chat_message.id}")
            return ChatMessageDetail.model_validate(result_chat_message)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Chat Message.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_chat_message: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@thread_router.patch(
    "/assistant/chat-messages/{chat_message_uuid}", response_model=ChatMessageDetail
)
def update_chat_message(
    chat_message_uuid: UUID,
    chat_message_data: ChatMessageUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """Updates an existing chat message."""
    try:
        chat_thread_repository = ChatThreadRepository(db)

        update_data = {
            k: v for k, v in chat_message_data.model_dump().items() if v is not None
        }
        update_data["chat_message_uuid"] = chat_message_uuid

        result_chat_message = chat_thread_repository.update_chat_message(update_data)

        if result_chat_message:
            logger.info(f"Chat Message updated successfully: {result_chat_message.id}")
            return ChatMessageDetail.model_validate(result_chat_message)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Chat Message. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_chat_message: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@thread_router.post(
    "/assistant/chat-threads/{chat_thread_uuid}/{action}", response_model=Message
)
def archive_or_unarchive_chat_thread(
    chat_thread_uuid: UUID,
    action: str = Path(..., description="Action to perform: 'archive' or 'unarchive'"),
    db: Session = Depends(get_schema_db),
):
    """Archive or unarchive a chat thread."""
    try:
        if action not in ["archive", "unarchive"]:
            raise HTTPException(status_code=400, detail="Not found.")

        is_archived = True if action == "archive" else False

        chat_thread_repository = ChatThreadRepository(db)

        chat_thread = chat_thread_repository.get_chat_thread_by_id(chat_thread_uuid)

        if not chat_thread:
            raise HTTPException(
                status_code=404,
                detail="Chat Thread not found. Please check and retry.",
            )

        result_chat_thread = chat_thread_repository.update_chat_thread(
            {"chat_thread_uuid": chat_thread_uuid, "is_archived": is_archived}
        )

        if result_chat_thread:
            return {"message": f"Chat Thread is {action}d successfully."}
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to {action} Chat Thread.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in archive_or_unarchive_chat_thread: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@thread_router.delete(
    "/assistant/chat-threads/{chat_thread_identifier}", response_model=Message
)
def delete_chat_thread(
    chat_thread_identifier: UUID = None,
    db: Session = Depends(get_schema_db),
):
    """Deletes a chat thread and its associated messages."""
    try:
        chat_thread_repository = ChatThreadRepository(db)

        deleted_chat_thread = chat_thread_repository.delete_chat_thread(
            chat_thread_identifier
        )

        if deleted_chat_thread:
            logger.info(f"Chat Thread deleted successfully: {chat_thread_identifier}")
            return {"message": "Chat Thread deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Chat Thread. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_chat_thread: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
