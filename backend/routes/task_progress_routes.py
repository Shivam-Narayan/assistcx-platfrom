# # Custom libraries
# from logger import configure_logging
# from schemas.task_progress_schema import (
#     TaskProgressResponse,
# )
# from utils.schema_utils import get_schema_db

# # Database modules
# from repository.task_progress_repository import TaskProgressRepository
# from sqlalchemy.orm import Session

# # Default libraries
# from typing import Optional
# from uuid import UUID

# # Installed libraries
# from fastapi import APIRouter, Depends, HTTPException, Query, Request


# logger = configure_logging(__name__)

# task_progress_router = APIRouter(tags=["Task Progress"])


# @task_progress_router.get(
#     "/task-progress/{email_uuid}", response_model=TaskProgressResponse
# )
# def get_task_progress(
#     email_uuid: UUID,
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Retrieves task progress information for a specific email based on specified criteria.
#     """
#     try:
#         task_progress_repository = TaskProgressRepository(db)

#         filters = request.state.filters

#         # Fetch all task progress for an email
#         task_progress, total_execution_time, total = (
#             task_progress_repository.get_task_progress(
#                 email_uuid=email_uuid,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )
#         )

#         return TaskProgressResponse(
#             task_progress=task_progress,
#             total_execution_time=total_execution_time,
#             total=total,
#         )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @task_progress_router.get(
#     "/task-progress-search/{email_uuid}", response_model=TaskProgressResponse
# )
# def search_task_progress(
#     email_uuid: UUID,
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves task progress information for a specific email based on specified keyword.
#     """
#     try:
#         task_progress_repository = TaskProgressRepository(db)

#         filters = request.state.filters

#         # Search task progress
#         if keyword:
#             task_progress, total_execution_time, total = (
#                 task_progress_repository.search_task_progress(
#                     email_uuid=email_uuid,
#                     keyword=keyword,
#                     filters=filters,
#                     sort_by=sort_by,
#                     sort_order=sort_order,
#                 )
#             )

#             if task_progress:
#                 return TaskProgressResponse(
#                     task_progress=task_progress,
#                     total_execution_time=total_execution_time,
#                     total=total,
#                 )
#             else:
#                 raise HTTPException(
#                     status_code=404,
#                     detail="No matching Task Progress found. Please check and retry.",
#                 )
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# # @task_progress_router.get(
# #     "/task-progress/{email_uuid}/search", response_model=TaskProgressResponse
# # )
# # def search_task_progress(
# #     email_uuid: UUID,
# #     keyword: str = Query(None, description="Search keyword"),
# #     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
# #     page: int = Query(1, description="Page number", gt=0),
# #     page_size: int = Query(10, description="Number of items per page", gt=0),
# #     sort_by: str = Query("updated_at", description="Field to sort by"),
# #     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
# #     db: Session = Depends(get_schema_db),
# #     request: Request = None,
# # ):
# #     """
# #     Searches and retrieves task progress information for a specific email based on specified keyword.
# #     """
# #     try:
# #         task_progress_repository = TaskProgressRepository(db)

# #         filters = request.state.filters

# #         # Search task progress
# #         if keyword:
# #             task_progress, total_execution_time, total = (
# #                 task_progress_repository.search_task_progress(
# #                     email_uuid=email_uuid,
# #                     keyword=keyword,
# #                     page=page,
# #                     page_size=page_size,
# #                     filters=filters,
# #                     sort_by=sort_by,
# #                     sort_order=sort_order,
# #                 )
# #             )

# #             if task_progress:
# #                 return TaskProgressResponse(
# #                     task_progress=task_progress,
# #                     total_execution_time=total_execution_time,
# #                     total=total,
# #                 )
# #             else:
# #                 raise HTTPException(
# #                     status_code=404,
# #                     detail="No matching Task Progress found. Please check and retry.",
# #                 )
# #         else:
# #             raise HTTPException(
# #                 status_code=400,
# #                 detail="No keyword provided",
# #             )

# #     except HTTPException as http_error:
# #         # Catch FastAPI HTTPExceptions
# #         logger.error(f"HTTPException occurred: {http_error.detail}")
# #         raise http_error
# #     except Exception as e:
# #         # Catch other exceptions
# #         logger.error(f"An error occurred: {e}")
# #         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
