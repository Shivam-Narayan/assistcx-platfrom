# Custom libraries
from logger import configure_logging
from integrations.office_365.outlook import Outlook
from schemas.mailbox_polling_schema import (
    MailboxPollingCreate,
    MailboxPollingDetail,
    MailboxPollingResponse,
    MailboxPollingUpdate,
)
from schemas.user_schema import Message
from utils.common_utils import (
    configure_data_parsing_configs,
    get_storage_region,
    parse_identifier,
    sanitize_data_store,
    get_human_reviewers_by_uuid,
)
from utils.schema_utils import get_current_schema, get_schema_db
from utils.environment import environment
from utils.integration_utils import IntegrationValidator
from configs.integrations import AUTH_SCHEMA_FIELDS, INTEGRATIONS

# Database modules
from repository.mailbox_polling_repository import MailboxPollingRepository
from repository.integration_repository import IntegrationRepository
from sqlalchemy.orm import Session

# Default libraries
from typing import Optional, Union
from uuid import UUID
from datetime import datetime

# Installed libraries
from celery.schedules import schedule
from celery_worker import celery
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from redbeat import RedBeatSchedulerEntry, schedulers


logger = configure_logging(__name__)

mailbox_polling_router = APIRouter(tags=["Mailbox Pollings"])


@mailbox_polling_router.get("/pollings", response_model=MailboxPollingResponse)
def get_mailbox_pollings(
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Retrieves mailbox polling information based on specified criteria.
    """
    try:
        mailbox_polling_repository = MailboxPollingRepository(db)

        filters = request.state.filters

        mailbox_pollings, total = mailbox_polling_repository.get_all_mailbox_pollings(
            filters=filters,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        return MailboxPollingResponse(mailbox_pollings=mailbox_pollings, total=total)

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.get("/pollings/search", response_model=MailboxPollingResponse)
def search_mailbox_pollings(
    keyword: str = Query(None, description="Search keyword"),
    filters: Optional[str] = Query(None, description="JSON-formatted filters"),
    page: Optional[int] = Query(None, description="Page number"),
    page_size: Optional[int] = Query(None, description="Number of items per page"),
    sort_by: str = Query("updated_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order (asc or desc)"),
    db: Session = Depends(get_schema_db),
    request: Request = None,
):
    """
    Searches and retrieves mailbox polling information based on specified keyword.
    """
    try:
        mailbox_polling_repository = MailboxPollingRepository(db)

        filters = request.state.filters

        # Search mailbox pollings with filtering and sorting.
        if keyword:
            mailbox_pollings, total = mailbox_polling_repository.search_mailbox_polling(
                keyword=keyword,
                filters=filters,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

            if mailbox_pollings:
                return MailboxPollingResponse(
                    mailbox_pollings=mailbox_pollings, total=total
                )
            else:
                return MailboxPollingResponse(mailbox_pollings=[], total=0)
        else:
            raise HTTPException(
                status_code=400,
                detail="No keyword provided.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.get(
    "/pollings/{polling_identifier}", response_model=MailboxPollingResponse
)
def get_polling(
    polling_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Retrieves mailbox polling information based on its polling_identifier.
    """
    try:
        mailbox_polling_repository = MailboxPollingRepository(db)

        mailbox_polling = mailbox_polling_repository.get_mailbox_polling(
            parse_identifier(polling_identifier)
        )

        if mailbox_polling:
            detail = MailboxPollingDetail.model_validate(mailbox_polling)
            polling_config = detail.polling_config
            notification_recipients = (
                polling_config.notification_recipients if polling_config else None
            )
            user_summaries = get_human_reviewers_by_uuid(db, notification_recipients)
            if user_summaries:
                polling_data = detail.model_dump()
                polling_config_data = dict(polling_data.get("polling_config") or {})
                polling_config_data["notification_recipients"] = user_summaries
                polling_data["polling_config"] = polling_config_data
                detail = MailboxPollingDetail.model_validate(polling_data)
            return MailboxPollingResponse(
                mailbox_pollings=[detail],
                total=1,
            )
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Mailbox Polling not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.post("/pollings", response_model=MailboxPollingDetail)
def pollings(
    request: MailboxPollingCreate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Creates or updates polling tasks using Celery Redbeat scheduler.
    """
    try:
        # Convert email id and folder name to lowercase in the request object
        request.email_id = request.email_id.lower()
        request.folder = request.folder.lower()

        if request.polling_config:
            polling_config = configure_data_parsing_configs(
                request.polling_config.model_dump()
            )
            request.polling_config = polling_config

        data_store = sanitize_data_store(
            request.data_store.model_dump() if request.data_store else None
        )

        if data_store["storage_type"] == "remote":
            storage_region = get_storage_region(db=db, data_store=data_store)
            if storage_region:
                data_store["storage_region"] = storage_region
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Unable to retrieve storage region. Please check and retry.",
                )

        outlook = Outlook(db)
        polling_status = outlook.verify_polling_request(
            email_id=request.email_id, folder=request.folder
        )

        if polling_status:
            # Construct task_name from email_id and folder
            task_name = f"{request.email_id}|{request.folder}"
            task_action = "process_mailbox"
            schedule = request.frequency if request.frequency else 60.0

            # Celery RedBeat scheduler entry
            # entry = RedBeatSchedulerEntry(
            #     name=task_name,
            #     task=task_action,
            #     schedule=schedule,
            #     args=[
            #         request.email_id,
            #         request.folder,
            #         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            #     ],
            #     app=celery,
            # )
            # entry.save()

            mailbox_data = {
                k: v for k, v in request.model_dump().items() if v is not None
            }
            mailbox_data["task_name"] = task_name
            mailbox_data["frequency"] = schedule
            mailbox_data["status"] = "CREATED"
            mailbox_data["data_store"] = data_store

            mailbox_polling_repository = MailboxPollingRepository(db)

            polling_entry = mailbox_polling_repository.create_mailbox_polling(
                mailbox_data
            )

            if polling_entry:
                logger.info(f"Mailbox Polling created successfully: {polling_entry.id}")
                return MailboxPollingDetail.model_validate(polling_entry)
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Failed to create or update mailbox polling entry.",
                )
        else:
            raise HTTPException(
                status_code=422,
                detail="Mailbox verification failed. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.patch(
    "/pollings/{polling_identifier}", response_model=MailboxPollingDetail
)
def update_polling(
    polling_identifier: Union[UUID, str] = None,
    polling_data: MailboxPollingUpdate = Body(...),
    db: Session = Depends(get_schema_db),
):
    """
    Updates an existing mailbox polling based on its polling_identifier.
    """
    try:
        if polling_data.polling_config:
            polling_config = configure_data_parsing_configs(
                polling_data.polling_config.model_dump()
            )
            polling_data.polling_config = polling_config

        if polling_data.data_store and polling_data.data_store.storage_type == "remote":
            storage_region = get_storage_region(
                db=db, data_store=polling_data.data_store.model_dump()
            )
            if storage_region:
                polling_data.data_store.storage_region = storage_region
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Unable to retrieve storage region. Please check and retry.",
                )

        update_data = {
            k: v
            for k, v in polling_data.model_dump().items()
            if v is not None and k != "status"
        }

        mailbox_polling_repository = MailboxPollingRepository(db)

        result_polling = mailbox_polling_repository.update_mailbox_polling(
            parse_identifier(polling_identifier), update_data
        )

        try:
            entry = RedBeatSchedulerEntry.from_key(
                f"redbeat:{result_polling.task_name}|{result_polling.id}", app=celery
            )
            if entry:
                entry.schedule = schedule(run_every=result_polling.frequency)
                entry.save()
        except Exception as e:
            logger.warning(f"Failed to update RedBeat entry: {e}")

        if result_polling:
            logger.info(f"Mailbox Polling updated successfully: {result_polling.id}")
            return MailboxPollingDetail.model_validate(result_polling)
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Mailbox Polling not found. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.post(
    "/pollings/{polling_identifier}/start", response_model=MailboxPollingDetail
)
def pollings(
    polling_identifier: Union[UUID, str] = None,
    polling_start_time: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_schema_db),
):
    """
    Creates or updates polling tasks using Celery Redbeat scheduler for a specific task based on its polling_identifier.
    Validates default LLM access before starting the polling task.
    """
    try:
        # Validate polling_start_time format if provided
        if polling_start_time:
            try:
                # Validate ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ
                datetime.strptime(polling_start_time, "%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid polling_start_time format. Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g., '2025-10-08T09:20:00Z')",
                )
        mailbox_polling_repository = MailboxPollingRepository(db)
        polling_entry = mailbox_polling_repository.get_mailbox_polling(
            identifier=parse_identifier(polling_identifier)
        )
        if not polling_entry:
            raise HTTPException(
                status_code=404,
                detail=f"Mailbox Polling not found. Please check and retry.",
            )

        # Get organization schema to pass as an argument to the task
        organization_schema = get_current_schema(db=db)

        # Validate default LLM access before starting polling
        logger.info(
            f"Validating default LLM access for organization: {organization_schema}"
        )

        # Get organization preferences to find default LLM
        org_preferences = environment.get_preferences(organization_schema)
        if not org_preferences or "default_llm" not in org_preferences:
            raise HTTPException(
                status_code=422,
                detail="No default LLM has been configured yet. Please set one up in Settings > Account > Account Preferences.",
            )

        # Parse default LLM key to get provider (e.g., "openai/gpt-4o" -> "openai")
        default_llm_key = org_preferences.get("default_llm")
        try:
            llm_provider_key, _ = default_llm_key.split("/", maxsplit=1)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"The default LLM '{default_llm_key}' has an invalid format. Please update it in Settings > Account > Account Preferences.",
            )

        # Get the integration for this LLM provider
        integration_repository = IntegrationRepository(db)
        integration = integration_repository.get_integration(
            identifier=llm_provider_key, decrypt_credentials=True
        )

        if not integration:
            raise HTTPException(
                status_code=422,
                detail=f"The {llm_provider_key} integration is not set up. Please activate it in Settings > Integrations.",
            )

        if not integration.is_active:
            raise HTTPException(
                status_code=422,
                detail=f"The {llm_provider_key} integration is currently inactive. Please enable it in Settings > Integrations.",
            )

        if not integration.credentials:
            raise HTTPException(
                status_code=422,
                detail=f"The {llm_provider_key} integration is missing credentials. Please reconfigure it in Settings > Integrations.",
            )

        # Validate credentials using existing IntegrationValidator
        # This makes an actual API call, same as integration activation
        validator = IntegrationValidator(
            auth_schema=AUTH_SCHEMA_FIELDS,
            preset=integration.auth_schema_fields.get("preset", {}),
            integrations=INTEGRATIONS,
        )

        is_valid, error_message = validator.validate_credentials(
            integration.key, integration.credentials
        )

        if not is_valid:
            raise HTTPException(
                status_code=422,
                detail=f"Unable to connect to {llm_provider_key}: {error_message}. Please verify your credentials in Settings > Integrations.",
            )

        outlook = Outlook(db)
        # split incoming task name to create email_id and folder
        email_id, folder = polling_entry.task_name.split("|")
        logger.info(f"Validating mailbox => email:{email_id}, folder:{folder}")
        polling_status = outlook.verify_polling_request(
            email_id=email_id, folder=folder
        )

        if not polling_status:
            raise HTTPException(
                status_code=422,
                detail="Mailbox verification failed. Please check and retry.",
            )

        mailbox_polling_repository.update_mailbox_polling(
            identifier=parse_identifier(polling_identifier),
            update_data={"status": "RUNNING"},
        )

        # Construct task_name from email_id and folder
        task_action = "process_mailbox"
        schedule = polling_entry.frequency

        # Celery RedBeat scheduler entry
        entry = RedBeatSchedulerEntry(
            name=f"{polling_entry.task_name}|{polling_entry.id}",
            task=task_action,
            schedule=schedule,
            args=[
                organization_schema,
                email_id,
                folder,
                polling_start_time,
            ],
            app=celery,
        )
        entry.save()

        return MailboxPollingDetail.model_validate(polling_entry)
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.post(
    "/pollings/{polling_identifier}/stop", response_model=Message
)
def stop_polling(
    polling_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Stops mailbox polling for a specific task based on its polling_identifier.
    """
    try:
        update_data = {
            "status": "STOPPED",
            "delta_link": "",
        }

        mailbox_polling_repository = MailboxPollingRepository(db)

        polling_entry = mailbox_polling_repository.update_mailbox_polling(
            parse_identifier(polling_identifier), update_data
        )

        if polling_entry:
            key = f"redbeat:{polling_entry.task_name}|{polling_entry.id}"

            try:
                entry = RedBeatSchedulerEntry.from_key(key, app=celery)
            except Exception as e:
                # Handle the case where the task doesn't exist
                return {"message": f"Task is not running: {polling_entry.task_name}"}

            if entry:
                entry.delete()
                return {
                    "message": f"Task stopped successfully: {polling_entry.task_name}"
                }
            else:
                return {"message": f"Task not found: {polling_entry.task_name}"}
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Mailbox Polling not found. Please check and retry.",
            )
    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.delete("/pollings/{polling_identifier}", response_model=Message)
def delete_mailbox_polling(
    polling_identifier: Union[UUID, str] = None,
    db: Session = Depends(get_schema_db),
):
    """
    Deletes an existing mailbox polling based on its polling_identifier. Only allowed for root user.
    """
    try:
        mailbox_polling_repository = MailboxPollingRepository(db)

        deleted_polling = mailbox_polling_repository.delete_mailbox_polling(
            parse_identifier(polling_identifier)
        )

        if deleted_polling:
            logger.info(f"Mailbox polling deleted successfully: {polling_identifier}")
            return {"message": "Mailbox polling deleted successfully."}
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete mailbox polling. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in delete_mailbox_polling: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.get("/redbeat-tasks")
def redbeat_tasks():
    """
    Retrieves details of all redbeat tasks.
    """
    try:
        redis = schedulers.get_redis(celery)
        keys = redis.keys("redbeat:*")

        # Filter and decode keys
        task_keys = [
            key.decode("utf-8") if isinstance(key, bytes) else key
            for key in keys
            if "::" not in (key.decode("utf-8") if isinstance(key, bytes) else key)
        ]

        # Process and return details of each scheduled task
        tasks = []
        for key_str in task_keys:
            # Fetch the RedBeat entry using the key
            entry = RedBeatSchedulerEntry.from_key(key_str, app=celery)
            task_info = {
                "name": entry.name,
                "task": entry.task,
                "schedule": str(entry.schedule),
                "args": entry.args,
                "kwargs": entry.kwargs,
                "enabled": entry.enabled,
                "last_run_at": (
                    entry.last_run_at.isoformat() if entry.last_run_at else None
                ),
                "total_run_count": entry.total_run_count,
            }
            tasks.append(task_info)

        if tasks:
            return tasks
        else:
            raise HTTPException(
                status_code=404,
                detail="Failed to retrieve details of scheduled tasks. Please check and retry.",
            )

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@mailbox_polling_router.delete("/task-history")
def purge_task_history():
    """
    Purges task history by deleting keys in the Redis database.
    """
    try:
        redis = schedulers.get_redis(celery)
        prefix = "celery-task-meta-*"

        # Find keys to delete
        keys_to_delete = redis.keys(prefix)
        for key in keys_to_delete:
            redis.delete(key)

        return {"message": f"Deleted {len(keys_to_delete)} keys."}

    except HTTPException as http_error:
        # Catch FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        # Catch other exceptions
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @polling_router.get("/schedule_job")
# def schedule_job(
#     email_id: str = Query(...),
#     folder: str = Query(...),
#     db: Session = Depends(get_schema_db),
#
# ):
#     """
#     Schedules periodic mailbox polling using APScheduler.
#     """
#     try:
#
#
#         trigger = IntervalTrigger(seconds=150)
#         job_id = f"{email_id}|{folder}"
#         scheduler.add_job(
#             func=process_mailbox,
#             trigger=trigger,
#             id=job_id,
#             args=[email_id, folder, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())],
#             replace_existing=True,  # Replace existing job with same id if exists
#             # kwargs={"custome_attribute": "value"},
#         )
#         return {"message": "Mailbox polling scheduled successfully."}
#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @polling_router.get("/list_jobs")
# def list_jobs(
#     db: Session = Depends(get_schema_db),
#
# ):
#     """
#     Retrieves a list of scheduled jobs from APScheduler.
#     """
#     try:
#
#
#         jobs = scheduler.get_jobs()
#         job_list = []
#         for job in jobs:
#             job_details = {
#                 "id": job.id,
#                 "name": job.name,
#                 "next_run_time": job.next_run_time,
#                 "trigger": str(job.trigger),
#                 "args": job.args,
#                 # "custome_attribute": job.kwargs.get("custome_attribute", "N/A"),
#             }
#             job_list.append(job_details)
#         if job_list:
#             return {"jobs": job_list}
#         else:
#             raise HTTPException(
#                 status_code=404,
#                 detail="Failed to retrieve list of scheduled jobs.",
#             )
#     except HTTPException as http_error:
#         # Catch FastAPI HTTPExceptions
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         # Catch other exceptions
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @mailbox_polling_router.get("/v1/pollings", response_model=MailboxPollingResponse)
# def get_paginated_mailbox_pollings(
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Retrieves paginated mailbox polling information based on specified criteria.
#     """
#     try:
#         mailbox_polling_repository = MailboxPollingRepository(db)

#         filters = request.state.filters

#         pollings, total = mailbox_polling_repository.paginated_get_all_mailbox_pollings(
#             page=page,
#             page_size=page_size,
#             filters=filters,
#             sort_by=sort_by,
#             sort_order=sort_order,
#         )

#         return MailboxPollingResponse(mailbox_pollings=pollings, total=total)

#     except HTTPException as http_error:
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @mailbox_polling_router.get(
#     "/v1/pollings-search", response_model=MailboxPollingResponse
# )
# def search_paginated_mailbox_pollings(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves paginated mailbox polling information based on specified keyword.
#     """
#     try:
#         mailbox_polling_repository = MailboxPollingRepository(db)

#         filters = request.state.filters

#         # Search mailbox pollings
#         if keyword:
#             mailbox_pollings, total = (
#                 mailbox_polling_repository.paginated_search_mailbox_polling(
#                     keyword=keyword,
#                     page=page,
#                     page_size=page_size,
#                     filters=filters,
#                     sort_by=sort_by,
#                     sort_order=sort_order,
#                 )
#             )

#             if mailbox_pollings:
#                 return MailboxPollingResponse(
#                     mailbox_pollings=mailbox_pollings, total=total
#                 )
#             else:
#                 return MailboxPollingResponse(mailbox_pollings=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


# @mailbox_polling_router.get("/pollings/search", response_model=MailboxPollingResponse)
# def search_mailbox_pollings(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves mailbox polling information based on specified keyword.
#     """
#     try:
#         mailbox_polling_repository = MailboxPollingRepository(db)

#         filters = request.state.filters

#         # Search mailbox pollings with filtering and sorting.
#         if keyword:
#             mailbox_pollings, total = mailbox_polling_repository.search_mailbox_polling(
#                 keyword=keyword,
#                 filters=filters,
#                 sort_by=sort_by,
#                 sort_order=sort_order,
#             )

#             if mailbox_pollings:
#                 return MailboxPollingResponse(
#                     mailbox_pollings=mailbox_pollings, total=total
#                 )
#             else:
#                 return MailboxPollingResponse(mailbox_pollings=[], total=0)
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


# @mailbox_polling_router.get(
#     "/v1/pollings/search", response_model=MailboxPollingResponse
# )
# def search_paginated_mailbox_pollings(
#     keyword: str = Query(None, description="Search keyword"),
#     filters: Optional[str] = Query(None, description="JSON-formatted filters"),
#     page: int = Query(1, description="Page number", gt=0),
#     page_size: int = Query(10, description="Number of items per page", gt=0),
#     sort_by: str = Query("updated_at", description="Field to sort by"),
#     sort_order: str = Query("desc", description="Sort order (asc or desc)"),
#     db: Session = Depends(get_schema_db),
#     request: Request = None,
# ):
#     """
#     Searches and retrieves paginated mailbox polling information based on specified keyword.
#     """
#     try:
#         mailbox_polling_repository = MailboxPollingRepository(db)

#         filters = request.state.filters

#         # Search mailbox pollings
#         if keyword:
#             mailbox_pollings, total = (
#                 mailbox_polling_repository.paginated_search_mailbox_polling(
#                     keyword=keyword,
#                     page=page,
#                     page_size=page_size,
#                     filters=filters,
#                     sort_by=sort_by,
#                     sort_order=sort_order,
#                 )
#             )

#             if mailbox_pollings:
#                 return MailboxPollingResponse(
#                     mailbox_pollings=mailbox_pollings, total=total
#                 )
#             else:
#                 return MailboxPollingResponse(mailbox_pollings=[], total=0)
#         else:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No keyword provided.",
#             )

#     except HTTPException as http_error:
#         logger.error(f"HTTPException occurred: {http_error.detail}")
#         raise http_error
#     except Exception as e:
#         logger.error(f"An error occurred: {e}")
#         raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
