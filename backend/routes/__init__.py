import os

from fastapi import FastAPI

from configs.module_registry import ENABLED_MODULES
from utils.rbac_utils import find_matching_modules
from logger import configure_logging

from .activity_log_routes import activity_log_router
from .agent_llm_routes import agent_llm_router
from .agent_output_routes import agent_output_router
from .agent_routes import agent_router
from .agent_task_routes import agent_task_router
from .agent_tool_routes import agent_tool_router
from .api_key_routes import api_key_router
from .asset_routes import asset_router
from .assistant_vector_store_routes import vector_store_router, knowledge_router
from .assistant_thread_routes import thread_router
from .assistant_task_routes import assistant_task_router
from .assistant_query_routes import query_router
from .attachment_routes import attachment_router
from .authentication_routes import authentication_router
from .class_group_routes import class_group_router
from .configuration_routes import configuration_router
from .connection_routes_v4 import connection_router
from .dashboard_routes import dashboard_router
from .data_collection_routes import data_collection_router
from .data_file_routes import data_file_router
from .data_template_routes import data_template_router
from .event_inbox_routes_v4 import event_inbox_router
from .external_task_routes import task_router
from .integration_catalog_routes_v4 import integration_catalog_router
from .integration_routes import integration_router
# from .intent_routes import intent_router
from .issue_routes import issue_router
from .knowledge_topic_routes import knowledge_topics_router
from .license_routes import lisence_router
from .mailbox_polling_routes import mailbox_polling_router
from .mailbox_routes import mailbox_router
from .notification_routes import notification_router
from .organization_routes import organization_router
from .user_profile_routes import user_profile_router
from .root_routes import root_router
from .sharepoint_routes import sharepoint_router
from .smart_field_routes import smart_field_router
from .task_event_routes import task_event_router

# from .task_progress_routes import task_progress_router
from .tag_routes import tag_router
from .task_source_routes_v4 import task_source_router
from .tool_binding_routes_v4 import tool_binding_router
from .user_group_routes import user_group_router
from .user_role_routes import user_role_router
from .user_routes import user_router
from .version_history_routes import version_history_router

logger = configure_logging(__name__)


def all_routers(app: FastAPI):
    routers = [
        activity_log_router,
        agent_llm_router,
        agent_output_router,
        agent_task_router,
        agent_router,
        api_key_router,
        asset_router,
        vector_store_router,
        knowledge_router,
        thread_router,
        assistant_task_router,
        query_router,
        attachment_router,
        authentication_router,
        class_group_router,
        configuration_router,
        connection_router,
        dashboard_router,
        data_collection_router,
        data_file_router,
        data_template_router,
        event_inbox_router,
        integration_catalog_router,
        integration_router,
        # intent_router,
        issue_router,
        knowledge_topics_router,
        lisence_router,
        mailbox_polling_router,
        mailbox_router,
        notification_router,
        organization_router,
        root_router,
        sharepoint_router,
        smart_field_router,
        task_event_router,
        # task_progress_router,
        task_router,
        tag_router,
        task_source_router,
        tool_binding_router,
        agent_tool_router,
        user_group_router,
        user_profile_router,
        user_role_router,
        user_router,
        version_history_router,
    ]

    registered = 0
    for router in routers:
        # Determine which modules own this router by checking its route paths
        owning_modules = set()
        for route in router.routes:
            if hasattr(route, "path"):
                owning_modules.update(find_matching_modules(route.path))

        # Register if: infrastructure (no module match) OR any owning module enabled
        if not owning_modules or owning_modules & ENABLED_MODULES:
            app.include_router(router)
            registered += 1

    edition = os.getenv("PLATFORM_EDITION", "full")
    logger.info(
        f"Edition: {edition} | Registered {registered}/{len(routers)} routers"
    )
