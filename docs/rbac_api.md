# RBAC API Endpoint Matrix

## Agents Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View agents | - `GET/agents`<br>- `GET/agents/search`<br>- `GET/agents/{agent_identifier}`<br>- `GET/agents/{agent_identifier}/export`<br>- `GET/agent-tools/{agent_tool_identifier}`<br>- `GET/agent/{agent_uuid}/agent-tools`<br>- `GET/version-histories`<br>- `GET/version-histories/{version_history_identifier}`<br>- `WEB/agents` | `name` | View AI agents on the platform |
| Create and update agents | - `GET/agents`<br>- `GET/agents/search`<br>- `GET/agents/{agent_identifier}`<br>- `GET/agents/{agent_identifier}/export`<br>- `POST/agents`<br>- `PUT/agents/{agent_uuid}`<br>- `POST/agents/import`<br>- `POST/agents/build`<br>- `POST/agents/archive`<br>- `GET/agent-tools`<br>- `GET/agent-tools/search`<br>- `GET/agent-tools/{agent_tool_identifier}`<br>- `GET/agent/{agent_uuid}/agent-tools`<br>- `GET/collections`<br>- `GET/collections/search`<br>- `GET/data-templates`<br>- `GET/data-templates/search`<br>- `GET/intents`<br>- `GET/intents-search`<br>- `GET/pollings`<br>- `GET/pollings/search`<br>- `GET/storage-mounts`<br>- `GET/version-histories`<br>- `GET/version-histories/{version_history_identifier}`<br>- `GET/integrations/llms`<br>- `WEB/agents` | None | Create and update agents |

## Agent LLMs Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View agent LLMs | - `GET/agent-llms` | None | View agent LLMs on the platform |

## Agent Tools Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View agent tools | - `GET/agent-tools`<br>- `GET/agent-tools/search`<br>- `GET/agent-tools/{agent_tool_identifier}`<br>- `GET/agent/{agent_uuid}/agent-tools`<br>- `GET/agent-tools/filters`<br>- `WEB/tools` | None | View tools used by AI agents |
| Create and update agent tools | - `GET/agent-tools`<br>- `GET/agent-tools/search`<br>- `GET/agent-tools/{agent_tool_identifier}`<br>- `GET/agent/{agent_uuid}/agent-tools`<br>- `POST/agent-tools`<br>- `PATCH/agent-tools/{agent_tool_uuid}`<br>- `POST/agent-tools/{agent_tool_identifier}/test`<br>- `WEB/tools` | None | Create and update agent tools |
| Delete agent tools | - `GET/agent-tools`<br>- `GET/agent-tools/search`<br>- `GET/agent-tools/{agent_tool_identifier}`<br>- `GET/agent/{agent_uuid}/agent-tools`<br>- `DELETE/agent-tools/{agent_tool_identifier}`<br>- `WEB/tools` | None | Delete agent tools |

## API Keys Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| Manage API keys | - `GET/api-keys`<br>- `GET/api-keys/search`<br>- `GET/api-keys/{api_key_identifier}`<br>- `POST/api-keys`<br>- `PATCH/api-keys/{api_key_uuid}`<br>- `DELETE/api-keys/{api_key_identifier}`<br>- `WEB/settings/api-keys` | None | Manage API keys used for accessing the platform via external systems |

## Assistant Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| Assistant chats | - `POST/assistant/query`<br>- `GET/assistant/stream/{thread_id}`<br>- `GET/research/observe/{thread_id}`<br>- `POST/assistant/stream`<br>- `POST/research/stream`<br>- `GET/assistant/chat-threads`<br>- `GET/assistant/chat-threads/search`<br>- `GET/assistant/chat-threads/{chat_thread_identifier}`<br>- `GET/assistant/chat-threads/{chat_thread_uuid}/chat-messages`<br>- `POST/assistant/chat-threads`<br>- `PATCH/assistant/chat-threads/{chat_thread_uuid}`<br>- `POST/assistant/chat-messages`<br>- `PATCH/assistant/chat-messages/{chat_message_uuid}`<br>- `POST/assistant/chat-threads/{chat_thread_uuid}/{action}`<br>- `DELETE/assistant/chat-threads/{chat_thread_identifier}`<br>- `GET/assistant/private-data-collection`<br>- `GET/assistant/private-data-collection/search`<br>- `POST/assistant/private-data-files`<br>- `GET/assistant/collections`<br>- `GET/embedding-models`<br>- `GET/assistant/collections/search`<br>- `GET/assistant/collections/{collection_uuid}`<br>- `POST/assistant/collections`<br>- `PATCH/assistant/collections/{collection_uuid}`<br>- `POST/assistant/collections/{collection_uuid}/sharepoint-sites`<br>- `DELETE/assistant/collections/{collection_uuid}`<br>- `GET/assistant/data-files/{data_file_uuid}`<br>- `GET/assistant/data-files/{data_file_uuid}/knowledge`<br>- `GET/assistant/data-files/{data_file_uuid}/chunks`<br>- `GET/assistant/data-files/{data_file_uuid}/download`<br>- `POST/assistant/data-files`<br>- `POST/assistant/data-files/{data_file_uuid}/rename`<br>- `POST/assistant/data-files/{data_file_uuid}/reindex`<br>- `DELETE/assistant/data-files` | None | Assistant chats |
| Scheduled tasks | - `GET/assistant/tasks`<br>- `GET/assistant/tasks/search`<br>- `GET/assistant/tasks/{chat_thread_id}`<br>- `GET/assistant/tasks/{thread_uuid}/tasks`<br>- `POST/assistant/tasks`<br>- `PATCH/assistant/tasks/{chat_thread_id}`<br>- `POST/assistant/tasks/{chat_thread_id}/pause`<br>- `POST/assistant/tasks/{chat_thread_id}/resume`<br>- `DELETE/assistant/tasks/{chat_thread_id}`<br>- `GET/assistant/collections`<br>- `GET/assistant/collections/search`<br>- `GET/assistant/collections/{collection_uuid}`<br>- `POST/assistant/collections`<br>- `PATCH/assistant/collections/{collection_uuid}`<br>- `POST/assistant/collections/{collection_uuid}/sharepoint-sites`<br>- `DELETE/assistant/collections/{collection_uuid}`<br>- `GET/assistant/data-files/{data_file_uuid}`<br>- `GET/assistant/data-files/{data_file_uuid}/knowledge`<br>- `GET/assistant/data-files/{data_file_uuid}/chunks`<br>- `GET/assistant/data-files/{data_file_uuid}/download`<br>- `POST/assistant/data-files`<br>- `POST/assistant/data-files/{data_file_uuid}/rename`<br>- `POST/assistant/data-files/{data_file_uuid}/reindex`<br>- `DELETE/assistant/data-files` | None | Scheduled tasks |

## Class Groups Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View class groups | - `GET/class-groups`<br>- `GET/class-groups/search`<br>- `GET/class-groups/{class_group_identifier}`<br>- `WEB/settings/class-group` | None | View class groups |
| Create and update class groups | - `GET/class-groups`<br>- `GET/class-groups/search`<br>- `GET/class-groups/{class_group_identifier}`<br>- `POST/class-groups`<br>- `PATCH/class-groups/{class_group_uuid}`<br>- `WEB/settings/class-group` | None | Create and update class groups |
| Delete class groups | - `GET/class-groups`<br>- `GET/class-groups/search`<br>- `GET/class-groups/{class_group_identifier}`<br>- `DELETE/class-groups/{class_group_identifier}`<br>- `WEB/settings/class-group` | None | Delete class groups |

## Collections Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View collections | - `GET/collections`<br>- `GET/collections/search`<br>- `GET/collections/{collection_uuid}`<br>- `GET/data-files/{data_file_uuid}`<br>- `GET/data-files/{data_file_uuid}/knowledge`<br>- `GET/data-files/{data_file_uuid}/chunks`<br>- `GET/collections/{collection_uuid}/knowledge-topics`<br>- `GET/collections/{collection_uuid}/smart-fields`<br>- `WEB/knowledge` | `name` | View collections and data files |
| Create and update collections | - `GET/collections`<br>- `GET/collections/search`<br>- `GET/collections/{collection_uuid}`<br>- `GET/data-files/{data_file_uuid}`<br>- `GET/data-files/{data_file_uuid}/knowledge`<br>- `GET/data-files/{data_file_uuid}/chunks`<br>- `GET/collections/{collection_uuid}/knowledge-topics`<br>- `GET/collections/{collection_uuid}/smart-fields`<br>- `GET/embedding-models`<br>- `POST/collections`<br>- `PATCH/collections/{collection_uuid}`<br>- `POST/collections/{collection_uuid}/sharepoint-sites`<br>- `GET/sharepoint/sites/{site_id}/objects`<br>- `GET/sharepoint/sites/{site_uuid}/{folder_id}/objects`<br>- `POST/sharepoint/files/import`<br>- `POST/data-files`<br>- `POST/data-files/{data_file_uuid}/rename`<br>- `POST/data-files/{data_file_uuid}/reindex`<br>- `GET/data-files/{data_file_uuid}/download`<br>- `POST/collections/{collection_uuid}/knowledge-topics`<br>- `PUT/collections/{collection_uuid}/knowledge-topics`<br>- `DELETE/collections/{collection_uuid}/knowledge-topics`<br>- `POST/collections/{collection_uuid}/smart-fields`<br>- `PUT/collections/{collection_uuid}/smart-fields`<br>- `DELETE/collections/{collection_uuid}/smart-fields`<br>- `GET/storage-mounts`<br>- `WEB/knowledge` | None | Create and update collections and data files |
| Delete collections | - `GET/collections`<br>- `GET/collections/search`<br>- `GET/collections/{collection_uuid}`<br>- `GET/data-files/{data_file_uuid}`<br>- `GET/data-files/{data_file_uuid}/knowledge`<br>- `GET/data-files/{data_file_uuid}/chunks`<br>- `GET/collections/{collection_uuid}/knowledge-topics`<br>- `GET/collections/{collection_uuid}/smart-fields`<br>- `DELETE/collections/{collection_uuid}`<br>- `DELETE/data-files`<br>- `WEB/knowledge` | None | Delete collections and data files |

## Connections Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View connections | - `GET/connections`<br>- `GET/connections/{connection_id}`<br>- `WEB/connections` | `name`, `provider_key`, `auth_schema_key` | View integration connections |
| Create and update connections | - `GET/connections`<br>- `GET/connections/{connection_id}`<br>- `GET/connections/{connection_id}/credentials`<br>- `POST/connections`<br>- `POST/connections/{connection_id}/test`<br>- `PATCH/connections/{connection_id}`<br>- `WEB/connections` | None | Create and update integration connections |
| Delete connections | - `GET/connections`<br>- `GET/connections/{connection_id}`<br>- `GET/connections/{connection_id}/credentials`<br>- `DELETE/connections/{connection_id}`<br>- `WEB/connections` | None | Soft delete integration connections |

## Dashboards Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View dashboards | - `GET/email-counts`<br>- `GET/email-monthly-stats`<br>- `GET/task-agent-stats`<br>- `GET/count-by-mailbox`<br>- `GET/task-counts`<br>- `GET/task-monthly-stats`<br>- `GET/task-volume-stats`<br>- `WEB/` | None | View dashboard data and stats |

## Data Templates Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View data templates | - `GET/data-templates`<br>- `GET/data-templates/search`<br>- `GET/data-templates/{data_template_identifier}`<br>- `GET/version-histories`<br>- `GET/version-histories/{version_history_identifier}`<br>- `WEB/settings/data-template` | None | View data templates |
| Create and update data templates | - `GET/data-templates`<br>- `GET/data-templates/search`<br>- `GET/data-templates/{data_template_identifier}`<br>- `POST/data-templates`<br>- `PATCH/data-templates/{data_template_uuid}`<br>- `POST/data-templates/build-schema`<br>- `GET/version-histories`<br>- `GET/version-histories/{version_history_identifier}`<br>- `WEB/settings/data-template` | None | Create and update data templates |
| Delete data templates | - `GET/data-templates`<br>- `GET/data-templates/search`<br>- `GET/data-templates/{data_template_identifier}`<br>- `DELETE/data-templates/{data_template_identifier}`<br>- `WEB/settings/data-template` | None | Delete data templates |

## Event Inbox Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View event inbox | - `GET/event-inboxes`<br>- `GET/event-inboxes/{event_inbox_id}`<br>- `WEB/event-inbox` | `external_event_id`, `dedupe_key` | View event inbox items |
| Create and update event inbox | - `GET/event-inboxes`<br>- `GET/event-inboxes/{event_inbox_id}`<br>- `POST/event-inboxes`<br>- `PATCH/event-inboxes/{event_inbox_id}`<br>- `WEB/event-inbox` | None | Create and update event inbox items |
| Delete event inbox | - `GET/event-inboxes`<br>- `GET/event-inboxes/{event_inbox_id}`<br>- `DELETE/event-inboxes/{event_inbox_id}`<br>- `WEB/event-inbox` | None | Delete event inbox items |

## Integration Catalog Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View integration catalog | - `GET/providers`<br>- `GET/auth-schema-catalog`<br>- `GET/trigger-catalog`<br>- `WEB/integration-catalog` | `keyword` | View integration provider, auth schema, and trigger catalogs |

## Integrations Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View integrations | - `GET/integrations`<br>- `GET/integrations/search`<br>- `GET/integrations/tags`<br>- `GET/integrations/{integration_identifier}`<br>- `GET/integrations/{integration_identifier}/bindings`<br>- `WEB/integrations` | None | View integrations |
| View integration credentials | - `GET/integrations`<br>- `GET/integrations/search`<br>- `GET/integrations/tags`<br>- `GET/integrations/{integration_identifier}`<br>- `GET/integrations/{integration_identifier}/bindings`<br>- `GET/integrations/{integration_identifier}/credentials`<br>- `WEB/integrations` | None | View integration credentials |

## Issues Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View issues | - `GET/issues`<br>- `GET/issues/search`<br>- `GET/issues/filters`<br>- `GET/issues/filters/search`<br>- `GET/issues/{issue_uuid}`<br>- `GET/issues/{issue_uuid}/comments`<br>- `GET/issues/{issue_uuid}/agent-tasks`<br>- `GET/agent-tasks/{agent_task_uuid}/issues`<br>- `GET/emails/{email_uuid}/issues`<br>- `GET/comments/{comment_uuid}`<br>- `WEB/issues` | None | View issues and comments |
| Create and update issues | - `GET/issues`<br>- `GET/issues/search`<br>- `GET/issues/filters`<br>- `GET/issues/filters/search`<br>- `GET/issues/{issue_uuid}`<br>- `GET/issues/{issue_uuid}/comments`<br>- `GET/issues/{issue_uuid}/agent-tasks`<br>- `GET/agent-tasks/{agent_task_uuid}/issues`<br>- `GET/emails/{email_uuid}/issues`<br>- `GET/comments/{comment_uuid}`<br>- `POST/issues`<br>- `PATCH/issues/{issue_uuid}`<br>- `PATCH/issues/{issue_uuid}/{action}`<br>- `PUT/issues/{issue_uuid}/progress`<br>- `POST/comments`<br>- `PATCH/comments/{comment_uuid}`<br>- `WEB/issues` | None | Create and update issues and comments |
| Delete issues | - `GET/issues`<br>- `GET/issues/search`<br>- `GET/issues/filters`<br>- `GET/issues/filters/search`<br>- `GET/issues/{issue_uuid}`<br>- `GET/issues/{issue_uuid}/comments`<br>- `GET/issues/{issue_uuid}/agent-tasks`<br>- `GET/agent-tasks/{agent_task_uuid}/issues`<br>- `GET/emails/{email_uuid}/issues`<br>- `GET/comments/{comment_uuid}`<br>- `DELETE/issues/{issue_uuid}`<br>- `DELETE/comments/{comment_uuid}`<br>- `WEB/issues` | None | Delete issues and comments |

## Intents Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View intents | - `GET/intents`<br>- `GET/intents-search`<br>- `GET/intents/{intent_identifier}`<br>- `WEB/settings/intent-class` | None | View intents |
| Create and update intents | - `GET/intents`<br>- `GET/intents-search`<br>- `GET/intents/{intent_identifier}`<br>- `POST/intents`<br>- `POST/intents/{intent_uuid}`<br>- `WEB/settings/intent-class` | None | Create and update intents |
| Delete intents | - `GET/intents`<br>- `GET/intents-search`<br>- `GET/intents/{intent_identifier}`<br>- `DELETE/intents/{intent_identifier}`<br>- `WEB/settings/intent-class` | None | Delete intents |

## Mailbox Pollings Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View mailbox pollings | - `GET/pollings`<br>- `GET/pollings/search`<br>- `GET/pollings/{polling_identifier}`<br>- `WEB/settings/mailbox-polling` | None | View list of polled mailboxes |
| Create and update pollings | - `GET/pollings`<br>- `GET/pollings/search`<br>- `GET/pollings/{polling_identifier}`<br>- `POST/pollings`<br>- `PATCH/pollings/{polling_identifier}`<br>- `POST/pollings/{polling_identifier}/start`<br>- `POST/pollings/{polling_identifier}/stop`<br>- `GET/storage-mounts`<br>- `WEB/settings/mailbox-polling` | None | Create and update mailbox pollings |
| Delete mailbox pollings | - `GET/pollings`<br>- `GET/pollings/search`<br>- `GET/pollings/{polling_identifier}`<br>- `DELETE/pollings/{polling_identifier}`<br>- `WEB/settings/mailbox-polling` | None | Delete mailbox pollings |

## Organizations Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View organization | - `GET/organizations/current`<br>- `GET/configurations`<br>- `WEB/settings/account` | None | View organization details |
| Update organization | - `GET/organizations/current`<br>- `GET/configurations`<br>- `PATCH/organizations/current`<br>- `POST/configurations`<br>- `GET/storage-mounts`<br>- `GET/agent-llms`<br>- `WEB/settings/account` | None | Update organization details |

## Task Inbox Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View task inbox | - `GET/emails`<br>- `GET/emails/search`<br>- `POST/emails/export`<br>- `POST/agent-tasks/export`<br>- `GET/emails/{email_uuid}`<br>- `GET/emails/filters`<br>- `GET/agents/preview`<br>- `GET/emails/{email_uuid}/agent-tasks`<br>- `GET/emails/{email_uuid}/task-events`<br>- `GET/emails/{email_uuid}/attachments`<br>- `GET/attachments/{attachment_identifier}`<br>- `GET/attachments/{attachment_identifier}/view`<br>- `GET/attachments/{attachment_identifier}/view-images`<br>- `GET/attachments/{attachment_identifier}/download`<br>- `GET/data-templates/{data_template_identifier}`<br>- `GET/task-outputs/{agent_task_uuid}`<br>- `GET/task-outputs/{agent_task_uuid}/usage`<br>- `GET/agent-outputs/{agent_task_uuid}/{agent_uuid}`<br>- `GET/agent-outputs/{agent_output_uuid}`<br>- `GET/task-progress/{email_uuid}`<br>- `GET/task-progress-search/{email_uuid}`<br>- `GET/agent-tasks/{agent_task_uuid}`<br>- `GET/agent-tasks/{agent_task_uuid}/stream`<br>- `POST/agent-tasks/{agent_task_uuid}/continue`<br>- `POST/agent-tasks/{agent_task_uuid}/resume`<br>- `GET/entities/{entity_id}/activity-logs`<br>- `PATCH/emails/{email_uuid}/tags`<br>- `POST/agent-tasks/{agent_task_uuid}/tags`<br>- `GET/tags`<br>- `GET/tags/search`<br>- `GET/tags/{tag_identifier}`<br>- `POST/tags`<br>- `PATCH/tags/{tag_uuid}`<br>- `DELETE/tags/{tag_identifier}`<br>- `GET/agent-tasks/{agent_task_uuid}/issues`<br>- `GET/emails/{email_uuid}/issues`<br>- `GET/issues/{issue_uuid}`<br>- `GET/issues/{issue_uuid}/comments`<br>- `GET/issues/{issue_uuid}/agent-tasks`<br>- `GET/comments/{comment_uuid}`<br>- `POST/issues`<br>- `PATCH/issues/{issue_uuid}`<br>- `PATCH/issues/{issue_uuid}/{action}`<br>- `PUT/issues/{issue_uuid}/progress`<br>- `POST/comments`<br>- `PATCH/comments/{comment_uuid}`<br>- `WEB/inbox` | `mailbox_email` | View task inbox on this platform |
| Retry email tasks | _(includes all view endpoints)_<br>- `POST/agent-tasks/{agent_task_uuid}/retry`<br>- `POST/emails/{agent_task_uuid}/retry/{agent_id}`<br>- `POST/emails/{email_uuid}/reprocess`<br>- `POST/attachments/{attachment_uuid}/reprocess` | None | Retry email tasks |
| Archive email tasks | _(includes all view endpoints)_<br>- `POST/emails/archive` | None | Archive email tasks |
| Update agent tasks | _(includes all view endpoints)_<br>- `POST/agent-tasks/status` | None | Update agent tasks and its related data |
| Delete email tasks | _(includes all view endpoints)_<br>- `DELETE/emails/bulk`<br>- `DELETE/issues/{issue_uuid}`<br>- `DELETE/comments/{comment_uuid}`<br>- `WEB/inbox` | None | Delete email tasks and its related data |

## Task Sources Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View task sources | - `GET/task-sources`<br>- `GET/task-sources/{task_source_id}`<br>- `WEB/task-sources` | `name`, `provider_key`, `trigger_key` | View task sources |
| Create and update task sources | - `GET/task-sources`<br>- `GET/task-sources/{task_source_id}`<br>- `POST/task-sources`<br>- `PATCH/task-sources/{task_source_id}`<br>- `WEB/task-sources` | None | Create and update task sources |
| Delete task sources | - `GET/task-sources`<br>- `GET/task-sources/{task_source_id}`<br>- `DELETE/task-sources/{task_source_id}`<br>- `WEB/task-sources` | None | Delete task sources |

## Tool Bindings Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View tool bindings | - `GET/tool-bindings`<br>- `GET/tool-bindings/{tool_binding_id}`<br>- `WEB/tool-bindings` | `provider_key`, `tool_key` | View tool bindings |
| Create and update tool bindings | - `GET/tool-bindings`<br>- `GET/tool-bindings/{tool_binding_id}`<br>- `POST/tool-bindings`<br>- `PATCH/tool-bindings/{tool_binding_id}`<br>- `WEB/tool-bindings` | None | Create and update tool bindings |
| Delete tool bindings | - `GET/tool-bindings`<br>- `GET/tool-bindings/{tool_binding_id}`<br>- `DELETE/tool-bindings/{tool_binding_id}`<br>- `WEB/tool-bindings` | None | Delete tool bindings |

## User Management Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| View user management | - `GET/users`<br>- `GET/users/search`<br>- `GET/users/{user_identifier}`<br>- `GET/user-roles`<br>- `GET/user-roles/search`<br>- `GET/permissions`<br>- `GET/user-groups`<br>- `GET/user-groups/search`<br>- `GET/user-groups/{user_group_identifier}`<br>- `WEB/settings/manage-user` | None | View users, user roles, and user groups |
| Create and update user management | - `GET/users`<br>- `GET/users/search`<br>- `GET/users/{user_identifier}`<br>- `POST/users`<br>- `PATCH/users/{user_uuid}`<br>- `POST/users/{user_uuid}/{action}`<br>- `GET/user-roles`<br>- `GET/user-roles/search`<br>- `GET/permissions`<br>- `POST/user-roles`<br>- `PATCH/user-roles/{user_role_uuid}`<br>- `GET/user-groups`<br>- `GET/user-groups/search`<br>- `GET/user-groups/{user_group_identifier}`<br>- `POST/user-groups`<br>- `PATCH/user-groups/{user_group_uuid}`<br>- `GET/user-roles/{user_role_uuid}/data-access-permissions`<br>- `GET/permissions/data-access`<br>- `GET/app-access`<br>- `WEB/settings/manage-user` | None | Create and update users, user roles, and user groups |
| Delete user management | - `GET/users`<br>- `GET/users/search`<br>- `GET/users/{user_identifier}`<br>- `DELETE/users/{user_uuid}`<br>- `GET/user-roles`<br>- `GET/user-roles/search`<br>- `DELETE/user-roles/{user_role_uuid}`<br>- `GET/user-groups`<br>- `GET/user-groups/search`<br>- `GET/user-groups/{user_group_identifier}`<br>- `DELETE/user-groups/{user_group_uuid}`<br>- `WEB/settings/manage-user` | None | Delete users, user roles, and user groups |

## User Profile Permissions

| Permission Name | Endpoints | Data Filters | Description |
|----------------|-----------|--------------|-------------|
| Manage profile | - `GET/profile/office365`<br>- `GET/profile`<br>- `PATCH/profile`<br>- `PUT/profile/password`<br>- `WEB/profile` | None | View and edit user profile |
