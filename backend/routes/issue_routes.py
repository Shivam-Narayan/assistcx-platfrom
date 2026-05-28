# Custom libraries
from logger import configure_logging
from schemas.issue_schema import (
    AgentTaskPreview,
    IssueCreate,
    IssueDetail,
    IssueFilters,
    IssueProgressUpdate,
    IssueUpdate,
    IssueUserFilter,
)
from schemas.issue_comment_schema import (
    IssueCommentCreate,
    IssueCommentDetail,
    IssueCommentUpdate,
)
from schemas.user_schema import Message
from utils.common_utils import get_current_user
from utils.notification import Notification
from utils.schema_utils import get_schema_db

# Database Modules
from repository.issue_repository import IssueRepository
from sqlalchemy.orm import Session

# Default libraries
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

# Installed libraries
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request


logger = configure_logging(__name__)

issue_router = APIRouter(tags=["Issues"])


# ==================== Issue Routes ====================


@issue_router.get("/issues", response_model=List[IssueDetail])
def get_issues(
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    from_date: float = Query(None, description="Start date as Unix timestamp"),
    to_date: float = Query(None, description="End date as Unix timestamp"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves all issues.
    """
    try:
        issue_repository = IssueRepository(db)

        filters = request.state.filters

        # Fetch all issues
        issues = issue_repository.get_all_issues(
            page=page,
            page_size=page_size,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            from_date=(datetime.fromtimestamp(from_date) if from_date else None),
            to_date=(datetime.fromtimestamp(to_date) if to_date else None),
        )

        return [IssueDetail.model_validate(issue) for issue in issues]

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_issues: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.get("/issues/search", response_model=List[IssueDetail])
def search_issues(
    keyword: str = Query(None, description="Search keyword"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    from_date: float = Query(None, description="Start date as Unix timestamp"),
    to_date: float = Query(None, description="End date as Unix timestamp"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches all issues by keyword.
    """
    try:
        issue_repository = IssueRepository(db)

        filters = request.state.filters

        if keyword:
            issues = issue_repository.search_all_issues(
                keyword=keyword,
                page=page,
                page_size=page_size,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
                from_date=(datetime.fromtimestamp(from_date) if from_date else None),
                to_date=(datetime.fromtimestamp(to_date) if to_date else None),
            )
            return [IssueDetail.model_validate(issue) for issue in issues] if issues else []
        else:
            raise HTTPException(
                status_code=400,
                detail="No keyword provided.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in search_issues: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.get("/issues/filters", response_model=IssueFilters)
def get_issues_filters(
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    sort_by: str = Query("issue_count", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves issues filters based on specified criteria.
    """
    try:
        issue_repository = IssueRepository(db)

        issue_filters = issue_repository.get_issue_filters(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return issue_filters

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_issues_filters: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.get("/issues/filters/search", response_model=IssueFilters)
def search_issues_filters(
    keyword: str = Query(None, description="Search keyword for user name"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("issue_count", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves issue filters based on specified keyword.
    """
    try:
        issue_repository = IssueRepository(db)

        filters = request.state.filters

        if keyword:
            issue_filters = issue_repository.search_issue_filters(
                keyword=keyword,
                page=page,
                page_size=page_size,
                filters=filters,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            return issue_filters
        else:
            raise HTTPException(
                status_code=400,
                detail="No keyword provided.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in search_issues_filters: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.get("/issues/{issue_uuid}", response_model=IssueDetail)
def get_issue(
    issue_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves issue information based on issue_uuid.
    """
    try:
        issue_repository = IssueRepository(db)

        issue = issue_repository.get_issue_by_id(issue_uuid)

        if issue:
            return IssueDetail.model_validate(issue)
        else:
            raise HTTPException(
                status_code=404,
                detail="Issue not found. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_issue: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.get(
    "/issues/{issue_uuid}/agent-tasks", response_model=List[AgentTaskPreview]
)
def get_agent_tasks_details_by_issue(
    issue_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves all agent tasks linked to a specific issue.
    """
    try:
        issue_repository = IssueRepository(db)

        tasks = issue_repository.get_agent_tasks_details_by_issue_id(issue_uuid)

        return [AgentTaskPreview.model_validate(task) for task in tasks] if tasks else []

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_agent_tasks_by_issue: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.get(
    "/agent-tasks/{agent_task_uuid}/issues", response_model=List[IssueDetail]
)
def get_issues_by_agent_task(
    agent_task_uuid: UUID,
    keyword: Optional[str] = Query(None, description="Optional search keyword"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves all issues for a specific agent task. Optionally search by keyword.
    """
    try:
        issue_repository = IssueRepository(db)

        filters = request.state.filters

        issues = issue_repository.get_issues_by_agent_task_id(
            agent_task_id=agent_task_uuid,
            page=page,
            page_size=page_size,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            keyword=keyword,
        )

        return [IssueDetail.model_validate(issue) for issue in issues] if issues else []

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_issues_by_agent_task: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.get(
    "/emails/{email_uuid}/issues", response_model=List[IssueDetail]
)
def get_issues_by_email(
    email_uuid: UUID,
    keyword: Optional[str] = Query(None, description="Optional search keyword"),
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves all issues for a specific email. Optionally search by keyword.
    """
    try:
        issue_repository = IssueRepository(db)

        filters = request.state.filters

        issues = issue_repository.get_issues_by_email_id(
            email_uuid=email_uuid,
            page=page,
            page_size=page_size,
            filters=filters,
            sort_by=sort_by,
            sort_order=sort_order,
            keyword=keyword,
        )

        return [IssueDetail.model_validate(issue) for issue in issues] if issues else []

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_issues_by_email: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.get(
    "/issues/{issue_uuid}/comments", response_model=List[IssueCommentDetail]
)
def get_comments_by_issue(
    issue_uuid: UUID,
    page: int = Query(1, description="Page number", gt=0),
    page_size: int = Query(10, description="Number of items per page", gt=0),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("asc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves all comments for a specific issue.
    """
    try:
        issue_repository = IssueRepository(db)

        comments = issue_repository.get_comments_by_issue_id(
            issue_id=issue_uuid,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return [IssueCommentDetail.model_validate(comment) for comment in comments] if comments else []

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_comments_by_issue: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.post("/issues", response_model=IssueDetail)
def create_issue(
    issue_data: IssueCreate = Body(...),
    db: Session = Depends(get_schema_db),
    current_user = Depends(get_current_user),
):
    """
    Creates a new issue.
    """
    try:
        user_uuid = current_user["user_uuid"]
        user_name = current_user["user_name"]

        issue_repository = IssueRepository(db)

        result_issue = issue_repository.create_issue(
            issue_data=issue_data,
            user_id=user_uuid,
            user_name=user_name,
        )

        if result_issue:
            logger.info(f"Issue created successfully: {result_issue.id}")
            
            return IssueDetail.model_validate(result_issue)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Issue.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_issue: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.patch("/issues/{issue_uuid}", response_model=IssueDetail)
def update_issue(
    issue_uuid: UUID,
    issue_data: IssueUpdate = Body(...),
    db: Session = Depends(get_schema_db),
    current_user = Depends(get_current_user),
):
    """
    Updates an existing issue based on its issue_uuid.
    Only updates non-progress fields (title, description, tag_ids, etc.)
    """
    try:
        user_uuid = current_user["user_uuid"]
        user_name = current_user["user_name"]

        issue_repository = IssueRepository(db)

        result_issue = issue_repository.update_issue(
            issue_uuid=issue_uuid,
            issue_data=issue_data,
            user_id=user_uuid,
            user_name=user_name,
        )

        if result_issue:
            logger.info(f"Issue updated successfully: {result_issue.id}")

            # Send notification to subscribers (excluding editor)
            try:
                notification_service = Notification(db)
                notification_service.notify_issue(
                    issue=result_issue,  # Issue object
                    event_type="edited",  # Event type
                    actor_user_id=str(user_uuid),  # User who edited
                    edited_by_name=user_name,  # Name of editor
                    changes_summary="Issue details were updated",  # Summary of changes
                )
            except Exception as notify_err:
                logger.error(f"Failed to send issue edited notification: {notify_err}")

            return IssueDetail.model_validate(result_issue)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Issue. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_issue: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.put("/issues/{issue_uuid}/progress", response_model=IssueDetail)
def update_issue_progress(
    issue_uuid: UUID,
    progress_data: IssueProgressUpdate = Body(...),
    db: Session = Depends(get_schema_db),
    current_user = Depends(get_current_user),
):
    """
    Updates the progress of an existing issue.
    Appends a new progress entry with status, reason, user info and timestamp.
    """
    try:
        user_uuid = current_user["user_uuid"]
        user_name = current_user["user_name"]

        issue_repository = IssueRepository(db)

        result_issue = issue_repository.update_issue_progress(
            issue_uuid=issue_uuid,
            progress_data=progress_data,
            user_id=user_uuid,
            user_name=user_name,
        )

        if result_issue:
            logger.info(f"Issue progress updated successfully: {result_issue.id}")

            # Send status change notification to subscribers
            try:
                notification_service = Notification(db)
                new_status = progress_data.status
                old_status = (
                    result_issue.progress[-2].get("status", "N/A")
                    if result_issue.progress and len(result_issue.progress) > 1
                    else "N/A"
                )
                notification_service.notify_issue(
                    issue=result_issue,  # Issue object
                    event_type="status_changed",  # Event type
                    actor_user_id=str(user_uuid),  # User who changed status
                    old_status=old_status,  # Previous status
                    new_status=new_status,  # New status
                    reason=progress_data.reason,  # Reason for change
                    changed_by_name=user_name,  # Name of changer
                )
            except Exception as notify_err:
                logger.error(f"Failed to send issue progress notification: {notify_err}")

            return IssueDetail.model_validate(result_issue)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Issue progress. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_issue_progress: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.delete("/issues/{issue_uuid}", response_model=Message)
def delete_issue(
    issue_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing issue based on its issue_uuid.
    """
    try:
        issue_repository = IssueRepository(db)

        deleted_issue = issue_repository.delete_issue(issue_uuid)

        if deleted_issue:
            logger.info(f"Issue deleted successfully: {issue_uuid}")
            return {"message": "Issue deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Issue. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_issue: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.patch("/issues/{issue_uuid}/{action}", response_model=IssueDetail)
def subscribe_unsubscribe_issue(
    issue_uuid: UUID,
    action: str,
    db: Session = Depends(get_schema_db),
    current_user=Depends(get_current_user),
):
    """
    Subscribe or unsubscribe the current user to/from an issue.

    - action = "subscribe"  → adds user to the subscribed list (no duplicates)
    - action = "unsubscribe" → removes user from the subscribed list
    """
    try:
        user_uuid = current_user["user_uuid"]

        if action not in ("subscribe", "unsubscribe"):
            raise HTTPException(
                status_code=400,
                detail="Invalid action. Use 'subscribe' or 'unsubscribe'.",
            )

        issue_repository = IssueRepository(db)

        result_issue = issue_repository.set_issue_subscription(
            issue_uuid=issue_uuid,
            user_id=user_uuid,
            subscribed=(action == "subscribe"),
        )

        if result_issue:
            logger.info(f"Issue {action}d successfully for user {user_uuid}: {issue_uuid}")
            return IssueDetail.model_validate(result_issue)
        else:
            raise HTTPException(
                status_code=404,
                detail="Issue not found. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in subscribe_unsubscribe_issue: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# ==================== Comment Routes ====================
@issue_router.get("/comments/{comment_uuid}", response_model=IssueCommentDetail)
def get_comment(
    comment_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves comment information based on comment_uuid.
    """
    try:
        issue_repository = IssueRepository(db)

        comment = issue_repository.get_issue_comment_by_id(comment_uuid)

        if comment:
            return IssueCommentDetail.model_validate(comment)
        else:
            raise HTTPException(
                status_code=404,
                detail="Comment not found. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in get_comment: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.post("/comments", response_model=IssueCommentDetail)
def create_comment(
    comment_data: IssueCommentCreate = Body(...),
    db: Session = Depends(get_schema_db),
    current_user = Depends(get_current_user),
):
    """
    Creates a new comment for an issue.
    """
    try:
        user_uuid = current_user["user_uuid"]

        issue_repository = IssueRepository(db)

        result_comment = issue_repository.create_issue_comment(
            comment_data=comment_data,
            user_id=user_uuid,
        )

        if result_comment:
            logger.info(f"Comment created successfully: {result_comment.id}")

            # Send notification to subscribers (excluding commenter)
            try:
                issue = issue_repository.get_issue_by_id(comment_data.issue_id)
                if issue:
                    notification_service = Notification(db)
                    notification_service.notify_issue(
                        issue=issue,  # Issue object
                        event_type="comment",  # Event type
                        actor_user_id=str(user_uuid),  # User who commented
                        comment=result_comment,  # Comment object
                        commenter_name=current_user["user_name"],  # Name of commenter
                    )
            except Exception as notify_err:
                logger.error(f"Failed to send comment notification: {notify_err}")

            return IssueCommentDetail.model_validate(result_comment)
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to create Comment.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_comment: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.patch("/comments/{comment_uuid}", response_model=IssueCommentDetail)
def update_comment(
    comment_uuid: UUID,
    comment_data: IssueCommentUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing comment based on its comment_uuid.
    """
    try:
        issue_repository = IssueRepository(db)

        result_comment = issue_repository.update_issue_comment(
            comment_uuid=comment_uuid,
            comment_data=comment_data,
        )

        if result_comment:
            logger.info(f"Comment updated successfully: {result_comment.id}")
            return IssueCommentDetail.model_validate(result_comment)
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to update Comment. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in update_comment: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@issue_router.delete("/comments/{comment_uuid}", response_model=Message)
def delete_comment(
    comment_uuid: UUID,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing comment based on its comment_uuid.
    """
    try:
        issue_repository = IssueRepository(db)

        deleted_comment = issue_repository.delete_issue_comment(comment_uuid)

        if deleted_comment:
            logger.info(f"Comment deleted successfully: {comment_uuid}")
            return {"message": "Comment deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete Comment. Please check and retry.",
            )

    except HTTPException as http_error:
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_comment: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
