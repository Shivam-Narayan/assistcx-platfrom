"""
Query Execution & Streaming routes.
"""

from agents.assistant_services.query_service import AssistantQueryService
from agents.live_agent.schemas import HumanReviewInput
from logger import configure_logging
from schemas.assistant_query_schema import AssistantQueryRequest
from utils.schema_utils import get_schema_db, set_schema

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer


logger = configure_logging(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="authorize")


def handle_query_error(
    e: Exception, thread_id: Optional[str] = None
) -> HTTPException:
    """Convert query/research errors to appropriate HTTP exceptions."""
    if isinstance(e, TimeoutError):
        return HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Query execution timed out",
        )
    elif isinstance(e, ValueError) and "No active query" in str(e):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active query found for thread {thread_id}",
        )
    elif isinstance(e, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    else:
        logger.error(f"Unexpected query error: {e}", exc_info=True)
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


async def get_assistant_service(
    request: Request, db=Depends(get_schema_db)
) -> AssistantQueryService:
    """Get Assistant service instance."""
    try:
        user_id = getattr(request.state, "user_id", None)
        org_schema = getattr(request.state, "org_id", "public")
        return AssistantQueryService(db=db, org_schema=org_schema, user_id=user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create Assistant service: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service initialization failed",
        )


# =============================================================================
# SECTION 5: QUERY EXECUTION & STREAMING  (tag: "Assistant Queries")
# =============================================================================

query_router = APIRouter(tags=["Assistant Queries"])


@query_router.post("/assistant/query")
async def execute_query(
    request: Request,
    query_request: AssistantQueryRequest,
    assistant_service: AssistantQueryService = Depends(get_assistant_service),
):
    """Execute an Assistant query and return the response."""
    logger.info(f"Received query: {query_request.query[:100]}...")

    user_id = getattr(request.state, "user_id")

    try:
        response = await assistant_service.execute_query_direct(
            query=query_request.query,
            user_id=user_id,
            mode=query_request.mode,
            chat_id=query_request.chat_id,
            agent_id=query_request.agent_id,
            collections=query_request.collections,
            attachments=query_request.attachments,
            user_context=query_request.user_context,
            web_search_enabled=query_request.web_search_enabled,
            timeout=query_request.timeout,
        )

        response["question"] = query_request.query
        response["mode"] = query_request.mode
        response["status"] = "completed"
        response["timestamp"] = datetime.now(timezone.utc).isoformat()
        return response

    except Exception as e:
        raise handle_query_error(e, query_request.chat_id)


@query_router.post("/assistant/stream")
@query_router.post("/research/stream", deprecated=True, include_in_schema=False)
async def stream_query(
    request: Request,
    query_request: AssistantQueryRequest,
) -> StreamingResponse:
    """Stream an Assistant query execution with background completion guarantee.

    Supports modes: research, agent. The mode is set via the request body.
    The agent execution runs in a background task that continues even if the client
    disconnects, ensuring the complete answer is always saved.

    The deprecated /research/stream endpoint routes here with mode defaulting to 'research'.
    """
    logger.info(
        f"Received streaming query: {query_request.query[:100]}..., "
        f"mode={query_request.mode}, agent_id={query_request.agent_id}"
    )

    user_id = getattr(request.state, "user_id")
    org_schema = getattr(request.state, "org_id", "public")

    # Queue for passing updates from background task to streaming response
    update_queue: asyncio.Queue = asyncio.Queue()

    async def background_execution():
        """Execute query in background with its own DB session.

        This task runs independently of the SSE connection, ensuring the query
        completes and saves even if the client disconnects mid-stream.
        """
        db_session = None
        chat_id = query_request.chat_id
        try:
            db_context = set_schema(org_schema)
            db_session = db_context.__enter__()

            service = AssistantQueryService(
                db=db_session, org_schema=org_schema, user_id=user_id
            )

            async for update in service.execute_query_stream(
                query=query_request.query,
                user_id=user_id,
                mode=query_request.mode,
                chat_id=query_request.chat_id,
                agent_id=query_request.agent_id,
                collections=query_request.collections,
                attachments=query_request.attachments,
                user_context=query_request.user_context,
                web_search_enabled=query_request.web_search_enabled,
            ):
                if update.get("chat_id"):
                    chat_id = update["chat_id"]
                await update_queue.put(update)

        except Exception as e:
            logger.error(
                f"Background execution error for chat_id={chat_id}: {e}",
                exc_info=True,
            )
            await update_queue.put(
                {
                    "type": "error",
                    "error": str(e),
                    "chat_id": chat_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        finally:
            await update_queue.put(None)
            if db_session is not None:
                try:
                    db_context.__exit__(None, None, None)
                except Exception as cleanup_error:
                    logger.error(
                        f"Error closing background DB session: {cleanup_error}"
                    )
            logger.info(f"Background execution completed for chat_id={chat_id}")

    # Start background task — continues even if client disconnects
    asyncio.create_task(background_execution())

    async def event_generator():
        """Read updates from queue and stream to client as SSE."""
        stream_chat_id = query_request.chat_id
        try:
            while True:
                update = await update_queue.get()

                if update is None:
                    break

                if update.get("chat_id"):
                    stream_chat_id = update["chat_id"]

                try:
                    event_data = json.dumps(update, default=str)
                    yield f"data: {event_data}\n\n"
                except (TypeError, ValueError) as json_error:
                    logger.error(f"JSON serialization error: {json_error}")
                    error_event = {
                        "error": "Serialization error in stream",
                        "type": "error",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield f"data: {json.dumps(error_event)}\n\n"

        except asyncio.CancelledError:
            logger.info(
                f"Stream cancelled by client for chat_id={stream_chat_id}, "
                "background execution continues"
            )
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            error_event = {
                "error": str(e),
                "type": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@query_router.post("/assistant/stream/resume")
async def resume_agent_stream(
    request: Request,
    resume_request: HumanReviewInput,
    assistant_service: AssistantQueryService = Depends(get_assistant_service),
) -> StreamingResponse:
    """Resume a paused live agent execution after human review."""
    logger.info(
        f"Resume agent stream: chat_id={resume_request.chat_id}, "
        f"action={resume_request.action}, "
        f"graph_thread_id={resume_request.graph_thread_id}"
    )

    user_id = getattr(request.state, "user_id")

    human_input = {
        "action": resume_request.action,
        "feedback": resume_request.feedback,
    }

    async def event_generator():
        """Generate Server-Sent Events for resumed agent execution."""
        try:
            async for update in assistant_service.resume_agent_stream(
                chat_id=resume_request.chat_id,
                agent_id=resume_request.agent_id,
                graph_thread_id=resume_request.graph_thread_id,
                human_input=human_input,
                user_id=user_id,
            ):
                try:
                    event_data = json.dumps(update, default=str)
                    yield f"data: {event_data}\n\n"
                except (TypeError, ValueError) as json_error:
                    logger.error(f"JSON serialization error: {json_error}")
                    error_event = {
                        "error": "Serialization error in stream",
                        "type": "error",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield f"data: {json.dumps(error_event)}\n\n"

        except asyncio.CancelledError:
            logger.info("Resume stream cancelled by client")
            cancel_event = {
                "type": "cancelled",
                "message": "Stream cancelled by client",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(cancel_event)}\n\n"
        except Exception as e:
            logger.error(f"Resume stream error: {e}", exc_info=True)
            error_event = {
                "error": str(e),
                "type": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@query_router.get("/assistant/stream/{thread_id}")
@query_router.get("/research/observe/{thread_id}", deprecated=True, include_in_schema=False)
async def observe_or_stream_by_thread_id(
    request: Request,
    thread_id: str,
    poll_interval: float = 0.5,
    assistant_service: AssistantQueryService = Depends(get_assistant_service),
) -> StreamingResponse:
    """Observe or stream updates from an existing query by thread_id.

    Polls the LangGraph checkpointer for state updates on research threads.
    """
    logger.info(f"Streaming/observing thread: {thread_id}")

    if len(thread_id) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid thread_id format"
        )

    async def event_generator():
        """Stream state updates via observe or direct stream."""
        try:
            # Use observe_query_execution for reconnection (works for research threads)
            async for update in assistant_service.observe_query_execution(
                thread_id=thread_id,
                poll_interval=poll_interval,
            ):
                try:
                    event_data = json.dumps(update, default=str)
                    yield f"data: {event_data}\n\n"
                except (TypeError, ValueError) as json_error:
                    logger.error(f"JSON serialization error: {json_error}")
                    error_event = {
                        "error": "Serialization error in stream",
                        "type": "error",
                        "thread_id": thread_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield f"data: {json.dumps(error_event)}\n\n"

                if update.get("type") == "error":
                    break
                if update.get("final_answer"):
                    break

        except asyncio.CancelledError:
            logger.info(f"Observe stream cancelled for thread_id={thread_id}")
        except Exception as e:
            logger.error(f"Observe error for thread_id={thread_id}: {e}", exc_info=True)
            error_event = {
                "error": str(e),
                "type": "error",
                "thread_id": thread_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@query_router.get("/assistant/health")
async def health_check(
    assistant_service: AssistantQueryService = Depends(get_assistant_service),
) -> Dict[str, Any]:
    """Health check endpoint for monitoring."""
    try:
        health_data = await assistant_service.health_check()

        if health_data.get("status") == "healthy":
            return health_data
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=health_data
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "error": str(e)},
        )
