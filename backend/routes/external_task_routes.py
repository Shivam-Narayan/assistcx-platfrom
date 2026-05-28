# Custom libraries
from logger import configure_logging
from schemas.external_task_schema import ExternalTaskCreate, TaskConfigs
from schemas.user_schema import Message
from utils.common_utils import (
    configure_data_parsing_configs,
    get_storage_region,
    sanitize_data_store,
)
from utils.external_task import ExternalTask
from utils.schema_utils import get_current_schema, get_schema_db

# Database modules
from repository.agent_repository import AgentRepository
from repository.configuration_repository import ConfigurationRepository
from sqlalchemy.orm import Session

# Default libraries
import base64
from typing import List

# Installed libraries
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError


logger = configure_logging(__name__)

task_router = APIRouter(tags=["Tasks"])

MAX_ATTACHMENTS = 5


@task_router.post("/tasks", response_model=Message)
@task_router.post("/task-api/tasks", response_model=Message)
def create_external_task(
    task_data: str = Form(...),
    task_attachments: List[UploadFile] = File([]),
    db: Session = Depends(get_schema_db),
):
    """
    Endpoint to create a task with optional file uploads.
    task_data: JSON string matching ExternalTaskCreate schema.
    task_attachments: Optional file uploads (max 5).
    """
    try:
        organization_schema = get_current_schema(db)

        # Parse and validate JSON metadata
        try:
            external_task_data = ExternalTaskCreate.model_validate_json(task_data)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid task_data JSON: {e}",
            )

        # Validate attachment count
        if task_attachments and len(task_attachments) > MAX_ATTACHMENTS:
            raise HTTPException(
                status_code=422,
                detail=f"Attachment limit reached: You can attach a maximum of {MAX_ATTACHMENTS} files per request.",
            )

        # Convert uploaded files to the existing format: [{file_name, content (base64)}]
        attachment_list = None
        if task_attachments:
            attachment_list = []
            for upload_file in task_attachments:
                file_bytes = upload_file.file.read()
                attachment_list.append(
                    {
                        "file_name": upload_file.filename,
                        "content": base64.b64encode(file_bytes).decode("utf-8"),
                    }
                )

        # Receiver: always use org default_email; folder always "inbox"
        configuration_repository = ConfigurationRepository(db)
        configuration = configuration_repository.get_configuration()
        default_email = (
            configuration.preferences.get("default_email")
            if configuration and configuration.preferences
            else None
        )

        receiver_email = default_email if default_email else None

        external_task_data = external_task_data.model_copy(
            update={
                "receiver_email": receiver_email,
            }
        )

        if external_task_data.task_configs:
            task_configs_data = configure_data_parsing_configs(
                external_task_data.task_configs.model_dump()
            )
            external_task_data.task_configs = TaskConfigs(**task_configs_data)

        # data_store is required only when there are attachments
        has_attachments = bool(attachment_list)
        if has_attachments and not external_task_data.data_store:
            raise HTTPException(
                status_code=422,
                detail="data_store is required when task_attachments are provided. Please provide a data_store object.",
            )

        if external_task_data.data_store:
            sanitized_data_store = sanitize_data_store(
                external_task_data.data_store.model_dump()
            )
            external_task_data.data_store = external_task_data.data_store.model_copy(
                update=sanitized_data_store
            )
            if external_task_data.data_store.storage_type == "remote":
                storage_region = get_storage_region(
                    db=db, data_store=external_task_data.data_store.model_dump()
                )
                if storage_region:
                    external_task_data.data_store.storage_region = storage_region
                else:
                    raise HTTPException(
                        status_code=422,
                        detail="Unable to retrieve storage region. Please check and retry.",
                    )

        if external_task_data.agent_id:
            agent_repository = AgentRepository(db)
            agent = agent_repository.get_agent(external_task_data.agent_id)
            if not agent:
                raise HTTPException(
                    status_code=404,
                    detail="Agent not found. Please check and retry.",
                )

        external_task = ExternalTask(db=db, organization_schema=organization_schema)

        # Convert to dict and inject attachments in the existing format
        task_dict = external_task_data.model_dump()
        task_dict["task_attachments"] = attachment_list

        return external_task.external_task_handler(task_dict)

    except HTTPException as http_error:
        # Catch and re-raise FastAPI HTTPExceptions
        logger.error(f"HTTPException occurred: {http_error.detail}")
        raise http_error
    except Exception as e:
        logger.error(f"Error in create_external_task: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
