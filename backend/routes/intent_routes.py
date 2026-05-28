# # Custom libraries
# from logger import configure_logging
# from schemas.intent_schema import (
#     IntentCreate,
#     IntentDetail,
#     IntentResponse,
#     IntentUpdate,
# )
# from schemas.user_schema import Message
# from utils.common_utils import parse_identifier
# from utils.schema_utils import get_schema_db

# # Database modules
# from repository.intent_repository import IntentRepository
# from sqlalchemy.orm import Session

# # Default libraries
# from typing import Optional, Union
# from uuid import UUID

# # Installed libraries
# from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request


# logger = configure_logging(__name__)

# intent_router = APIRouter(tags=["Intents"])


# @intent_router.get("/intents", response_model=IntentResponse)
# def get_intents(
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: Optional[int] = Query(None, description="Page number"),
#     page_size: Optional[int] = Query(None, description="Number of items per page"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Retrieves intent information based on specified criteria.
#     """
#     try:
#         intent_repository = IntentRepository(db)

#         filters = request.state.filters

#         # Fetch all intents with filters and sorting
#         intents, total = intent_repository.get_all_intents(
#             filters=filters,
#             page=page,
#             page_size=page_size,
#             sort_by=sort_by,
#             sort_order=sort_order,
#         )

#         return IntentResponse(intents=intents, total=total)

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @intent_router.get("/intents-search", response_model=IntentResponse)
# def search_intents(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: Optional[int] = Query(None, description="Page number"),
#     page_size: Optional[int] = Query(None, description="Number of items per page"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves intent information based on specified keyword.
#     """
#     try:
#         intent_repository = IntentRepository(db)

#         filters = request.state.filters

#         # Search intents with sorting
#         if keyword:
#             intents, total = intent_repository.search_intent(
#                 keyword=keyword,
#                 filters=filters,
#                 page=page,
#                 page_size=page_size,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if intents:
#                 return IntentResponse(intents=intents, total=total)
#             else:
#                 return IntentResponse(intents=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @intent_router.get("/intents/{intent_identifier}", response_model=IntentResponse)
# def get_intent(
#     intent_identifier: Union[UUID, str] = None,
#     db: Session = Depends(get_schema_db),
# ):
#     """
#     Retrieves intent information based on intent_identifier.
#     """
#     try:
#         intent_repository = IntentRepository(db)

#         if intent_identifier:
#             # Fetch a single intent by ID or intent_class
#             intent = intent_repository.get_intent(parse_identifier(intent_identifier))
#             if intent is not None:
#                 return IntentResponse(intents=[intent], total=1)
#             else:
#                 raise HTTPException(
#                     status_code=404,
#                     detail="Intent not found. Please check and retry.",
#                 )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @intent_router.post("/intents", response_model=IntentDetail)
# def create_intent(
#     intent_data: IntentCreate = Body(...),
#     db: Session = Depends(get_schema_db),
# ):
#     """
#     Creates a new intent.
#     """
#     try:
#         intent_repository = IntentRepository(db)

#         result_intent = intent_repository.create_intent(intent_data)

#         if result_intent:
#             logger.info(f"Intent created successfully: {result_intent.id}")
#             return IntentDetail.model_validate(result_intent)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Failed to create Intent.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @intent_router.post("/intents/{intent_uuid}", response_model=IntentDetail)
# def update_intent(
#     intent_uuid: UUID,
#     intent_data: IntentUpdate = Body(...),
#     db: Session = Depends(get_schema_db),
# ):
#     """
#     Updates an existing intent based on its intent_uuid.
#     """
#     try:
#         intent_repository = IntentRepository(db)

#         update_data = {
#             k: v for k, v in intent_data.model_dump().items() if v is not None
#         }

#         # Append intent_uuid to update_data
#         update_data["intent_uuid"] = intent_uuid

#         result_intent = intent_repository.update_intent(update_data)

#         if result_intent:
#             logger.info(f"Intent updated successfully: {result_intent.id}")
#             return IntentDetail.model_validate(result_intent)
#         else:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Failed to update Intent. Please check and retry.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @intent_router.delete("/intents/{intent_identifier}", response_model=Message)
# def delete_intent(
#     intent_identifier: Union[UUID, str] = None,
#     db: Session = Depends(get_schema_db),
# ):
#     """
#     Deletes an existing intent based on its intent_identifier.
#     """
#     try:
#         intent_repository = IntentRepository(db)

#         deleted_intent = intent_repository.delete_intent(
#             parse_identifier(intent_identifier)
#         )

#         if deleted_intent:
#             logger.info(f"Intent deleted successfully: {intent_identifier}")
#             return {"message": "Intent deleted successfully."}
#         else:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Failed to delete Intent. Please check and retry.",
#             )

#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         logger.error(f"Error in delete_intent: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# # Deprecated
# # @intent_router.get("/v1/intents", response_model=IntentResponse)
# # def get_paginated_intents(
# #     page: int = Query(1, description="Page number", gt=0),
# #     page_size: int = Query(10, description="Number of items per page", gt=0),
# #     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
# #     sort_by: str = Query("updated_at", description="Field to sort by"),
# #     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
# #     db: Session = Depends(get_schema_db),
# #     request: Request = None,
# # ):
# #     """
# #     Retrieves paginated intent information based on specified criteria.
# #     """
# #     try:
# #         intent_repository = IntentRepository(db)

# #         filters = request.state.filters

# #         # Fetch paginated intents
# #         intents, total = intent_repository.get_paginated_intents(
# #             page=page,
# #             page_size=page_size,
# #             filters=filters,
# #             sort_by=sort_by,
# #             sort_order=sort_order,
# #         )

# #         return IntentResponse(intents=intents, total=total)

# #     except HTTPException as http_error:
# #         logger.error(f"HTTPException occurred: {http_error.detail}")
# #         raise http_error
# #     except Exception as e:
# #         logger.error(f"An error occurred: {e}")
# #         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# # @intent_router.get("/v1/intents-search", response_model=IntentResponse)
# # def search_paginated_intents(
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
# #     Searches and retrieves paginated intent information based on specified keyword.
# #     """
# #     try:
# #         intent_repository = IntentRepository(db)

# #         filters = request.state.filters

# #         # Search intents
# #         if keyword:
# #             intents, total = intent_repository.search_paginated_intent(
# #                 keyword=keyword,
# #                 page=page,
# #                 page_size=page_size,
# #                 filters=filters,
# #                 sort_by=sort_by,
# #                 sort_order=sort_order,
# #             )

# #             if intents:
# #                 return IntentResponse(intents=intents, total=total)
# #             else:
# #                 return IntentResponse(intents=[], total=0)
# #         else:
# #             raise HTTPException(
# #                 status_code=400,
# #                 detail="No keyword provided.",
# #             )

# #     except HTTPException as http_error:
# #         # Catch FastAPI HTTPExceptions
# #         logger.error(f"HTTPException occurred: {http_error.detail}")
# #         raise http_error
# #     except Exception as e:
# #         # Catch other exceptions
# #         logger.error(f"An error occurred: {e}")
# #         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# # @intent_router.get("/intents/search", response_model=IntentsResponse)
# # def search_intents(
# #     keyword: str = Query(None, description="Search keyword"),
# #     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
# #     sort_by: str = Query("updated_at", description="Field to sort by"),
# #     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
# #     db: Session = Depends(get_schema_db),
# #     request: Request = None,
# # ):
# #     """
# #     Searches and retrieves intent information based on specified keyword.
# #     """
# #     try:
# #         intent_repository = IntentRepository(db)

# #         filters = request.state.filters

# #         # Search intents with sorting
# #         if keyword:
# #             intents = intent_repository.search_intent(
# #                 keyword=keyword, filters=filters, sort_by=sort_by, sort_order=sort_order
# #             )

# #             if intents:
# #                 return IntentsResponse(intents=intents, total=len(intents))
# #             else:
# #                 return IntentsResponse(intents=[], total=0)
# #         else:
# #             raise HTTPException(
# #                 status_code=400,
# #                 detail="No keyword provided.",
# #             )

# #     except HTTPException as http_error:
# #         # Catch FastAPI HTTPExceptions
# #         logger.error(f"HTTPException occurred: {http_error.detail}")
# #         raise http_error
# #     except Exception as e:
# #         # Catch other exceptions
# #         logger.error(f"An error occurred: {e}")
# #         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# # @intent_router.get("/v1/intents/search", response_model=IntentsResponse)
# # def search_paginated_intents(
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
# #     Searches and retrieves paginated intent information based on specified keyword.
# #     """
# #     try:
# #         intent_repository = IntentRepository(db)

# #         filters = request.state.filters

# #         # Search intents
# #         if keyword:
# #             intents, total = intent_repository.search_paginated_intent(
# #                 keyword=keyword,
# #                 page=page,
# #                 page_size=page_size,
# #                 filters=filters,
# #                 sort_by=sort_by,
# #                 sort_order=sort_order,
# #             )

# #             if intents:
# #                 return IntentsResponse(intents=intents, total=total)
# #             else:
# #                 return IntentsResponse(intents=[], total=0)
# #         else:
# #             raise HTTPException(
# #                 status_code=400,
# #                 detail="No keyword provided.",
# #             )

# #     except HTTPException as http_error:
# #         # Catch FastAPI HTTPExceptions
# #         logger.error(f"HTTPException occurred: {http_error.detail}")
# #         raise http_error
# #     except Exception as e:
# #         # Catch other exceptions
# #         logger.error(f"An error occurred: {e}")
# #         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
