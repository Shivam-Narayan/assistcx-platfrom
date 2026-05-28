​# Changelog

## [v3.52.10] Latest

✨ Discover What's New in v3.52 ✨

A release series delivering RBAC/permissions hardening, agent tools expansion, email filtering improvements, assistant module routing, and incremental patch fixes.

### 🚀 New Features

- 📁 **Assistant Module Routing**
  - Added new routes for data files and collections in the assistant module.
  - Added configurations inside the Assistant module in the user_role file.

### 🛠️ Enhancements

- 🤖 **Agent Tools Integrations**
  - Added API tools in agent tools integrations.
  - Renamed get agent tools route URL for consistency.
  - Minor fix for agent-tools permission in agents module.
  - Minor changes for embedding model.
  - Removed full access from integration defaults.

- 📧 **Email & Mailbox Filtering**
  - Refactored email filtering logic to conditionally include archived tasks based on status filter.
  - Removed delete email access from default roles.
  - Added mailbox-filters route and enhanced agent data resolution in permissions.

- 🔒 **RBAC & Permissions**
  - Enhanced agent preview retrieval with inherited data filters and access verification.
  - Enhanced error handling in inherited data filters resolution (HTTP 401 on access denial).
  - Enhanced permissions handling with inherited data filters and refactored RBAC utility functions.
  - Added `/class-groups` and `/users` routes to platform modules configuration.
  - Added `/version-histories` route to platform modules configuration.
  - Added `/integrations-llms` route to agent LLMs module and updated access routes.
  - Minor changes in access level configurations.

### 🐛 Bug Fixes

- 🔧 **Export**
  - Fixed bug in export agent task timestamp.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.52.0] 🔒 Assistant Refactor, Permissions Hardening & HITL

✨ Discover What's New in v3.52.0 ✨

A significant release with permissions hardening, assistant service refactoring, and HITL improvements in the live agent.

### 🛠️ Enhancements

- 🔒 **Permissions**
  - Enhanced permissions handling by denying access for empty `data_permission` keys.
  - Added core route check for data filters.

- 🤖 **Assistant Services**
  - Refactored file handling: replaced `file_ids` with `attachments` in query processing.
  - Enhanced query screening guidelines for `DirectResponse` in prompts.

- 🔄 **HITL (Human-in-the-Loop)**
  - HITL improvement in Live agent.
  - Minor improvement in live agent.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.51.0] 🔧 Filter Params Hotfix

A focused hotfix release resolving query parameter filter issues introduced by the RBAC revamp.

### 🐛 Bug Fixes

- 🔧 **Filter Params**
  - Resolved filter issue for routes affected by the RBAC revamp.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.50.5] 📄 OCR & Task Agent Graph Improvements

✨ Discover What's New in v3.50 ✨

A series of releases improving the DocumentParser with RapidOCR, refactoring the task agent graph for cleaner execution, and scoping data filters to agents and knowledge only.

### 🛠️ Enhancements

- 📄 **Document Parser (OCR)**
  - Updated OCR model paths in DocumentParser for RapidOCR integration.
  - Removed modelscope dependency and related model download code for a lighter footprint.

- 🤖 **Task Agent Graph**
  - Used setup agent graph in `execute_task`.
  - Graph setup refactoring and reuse.
  - Simplified task output tool and process.
  - Improved interrupt payload logic.
  - Improved LLM review flow.
  - Minor refactoring for cleaner execution.

- 🔄 **HITL**
  - Removed feedback in HITL (Reject now handles the feature).

- 🤖 **Agent Assignment**
  - Added `get_agents_by_assignment` repository function.

- 🔒 **Data Filters**
  - Removed data filters from all modules except agents and knowledge for cleaner scoping.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.50.1] 🤖 Agent Assignment, Exa Integration & Research Timestamps

✨ Discover What's New in v3.50.1 ✨

Introducing email-to-agent assignment by description, Exa search integration, execution timing in research mode, and attachment validation.

### 🚀 New Features

- 🔍 **Exa Integration**
  - Added Exa search integration for enhanced web research capabilities.

- ⏱️ **Research Mode Timestamps**
  - Added execution timing (`start_time` / `end_time`) to assistant streaming response in research mode.

### 🛠️ Enhancements

- 📧 **Email Agent Assignment**
  - Emails are now assigned agents based on agent description rather than intent class.

- 📎 **Attachment Validation**
  - Added validation for attachment file type in the reprocess endpoint.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.50.0] 🔒 RBAC Revamp & Human Review Enhancements

✨ Discover What's New in v3.50.0 ✨

A landmark release merging the comprehensive RBAC revamp, removing the deprecated RAG agent, and enhancing the human review workflow.

### 🚀 New Features

- 🔒 **RBAC Revamp**
  - Merged comprehensive RBAC revamp with permission simplification and standardization.

### 🛠️ Enhancements

- 🔄 **Human Review**
  - Added question generation for human reviewer in the review workflow.
  - Human review history serialization.
  - Refactored tool generation to include human review flag.

### 🗑️ Deprecations

- 🤖 **RAG Agent**
  - Removed deprecated RAG agent from the codebase.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.49.0] 🔌 Agent Tools Data, Data Extractor & Integration Improvements

✨ Discover What's New in v3.49 ✨

A focused release improving agent tools data for integrations, removing legacy data extractor code, refining the model generator, and adding mailbox polling fixes.

### 🚀 New Features

- 🛠️ **Agent Tools Data**
  - Improvements in agent tools data for integrations.
  - Added 3 new fields in the migration for agent tools.

### 🛠️ Enhancements

- 📡 **Mailbox Polling**
  - Minor change in backend worker for periodic polling order.

- 🔬 **Data Extractor**
  - Removed legacy data extractor implementation to streamline the codebase.
  - Updated description for Extract Structured Data tool for improved clarity.
  - Minor changes in data extractor.

- 🤖 **Model Generator**
  - Improved model generator with better structure.

- 🔄 **Human Review**
  - Refactored human review logic and updated rejection prompt for clarity.

- 🔌 **Integrations API**
  - Renamed `GET/provider` to `GET/providers` for API consistency.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.48.16] 🔧 Dependencies & Pause State

### 🛠️ Enhancements

- 📦 **Dependencies**
  - Updated langchain and langgraph versions in requirements.txt.

- ⏸️ **Task State**
  - Included paused status in task state handling.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.48.10] ⏸️ Task Pause/Resume, Connection Health Check & Activity Log

✨ Discover What's New in v3.48.10 ✨

A series of patch releases adding task pause/resume support, connection health checks, and activity log fallback improvements.

### 🚀 New Features

- ⏸️ **Task Pause & Resume**
  - Added permissions for resume task.
  - Updated exit condition in `TaskAgentGraph` to handle paused tasks for human review.
  - Refactored pending review extraction in `TaskExecutor` and `TaskAgentGraph`.

- 🔌 **Connection Health Check**
  - Implemented connection health check endpoint and response schema.
  - Added triggers and tools to provider endpoints.
  - Permission added to the new test endpoint.

### 🛠️ Enhancements

- 📊 **Activity Log**
  - Added fallback user name (`External system`) in activity log when task is retried via API key.

- 🔌 **Provider API**
  - Combined provider API endpoints for cleaner access.
  - Fixed minor connection repository issues.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.48.7] 🔌 Connections, Credits API & Human Review Fixes

✨ Discover What's New in v3.48.7 ✨

A release series adding a credits & token usage API, enriching connection data with creator names, and fixing human review edge cases.

### 🚀 New Features

- 💳 **Credits & Token Usage API**
  - Added API for credits and token usage for agent task output (latest or by output ID).

- 🔌 **Connection Enhancements**
  - Added `user_name` field to `ConnectionDetail` schema.
  - Batch-fetch creator names for connections and assign to `user_name` field.
  - Added user name attachment to connection creation and updates.

### 🛠️ Enhancements

- 🔒 **Permissions**
  - Permissions added for all new v4 endpoints.
  - Added `provider_key` to auth schemas for integration mapping.
  - Permissions added for integration modules.

### 🐛 Bug Fixes

- 🔄 **Human Review**
  - Fixed metadata handling for human review checks to prevent errors with missing metadata.
  - Enhanced error handling in human review functions and improved code formatting.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.48.3] 🛠️ Integration Catalog, Execution Plan & DB Patches

### 🛠️ Enhancements

- 📋 **Integration Catalog**
  - Renamed integration catalog endpoint to `/provider`.
  - Added `provider_key` to auth schemas for integration mapping.
  - Fixed rename of integration catalog endpoint.

- 🤖 **Execution Plan**
  - Execution plan improvements and prompt refinements.

- 🗄️ **Database**
  - DB patch to fill in empty `created_at` and `updated_at` fields.
  - Added token usage key to task output.

### 🐛 Bug Fixes

- 🔧 **Attachment**
  - Safety check for null value in attachment.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.48.2] 🔌 Integration V4, RBAC Simplification & HITL Refactoring

✨ Discover What's New in v3.48.2 ✨

A significant update introducing the Integration V4 model, RBAC simplification, HITL improvements, and a new async database pool manager.

### 🚀 New Features

- 🔌 **Integration V4**
  - New Integration V4 model with updated auth schemas, triggers, S3, and Outlook support.
  - New connection APIs, catalog APIs, tool binding APIs, task source APIs, and event inbox APIs.
  - New OpenAI validator.

- 🔄 **HITL Refactoring**
  - HITL API route for resuming tasks.
  - New task output tool.

- 🗄️ **Async DB Pool Manager**
  - New async database pool manager for improved connection handling.

### 🛠️ Enhancements

- 🔒 **RBAC**
  - RBAC simplification and revamp for cleaner permission management.

- 📄 **Data Extractor**
  - Data extraction enhancements with combined extraction tools.
  - Email body added to email data extraction.
  - Email file URL introduced.

- 📧 **Notifications**
  - Added email and task failure notification templates.

### 🐛 Bug Fixes

- 🔧 **Minor Fixes**
  - Various minor bug fixes across the platform.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.48.1] 📚 Knowledge Base Tools, RBAC & Document Parser

### 🚀 New Features

- 📚 **Knowledge Base Default Tools**
  - Set default tools for knowledge base in agents.
  - Added default tool configuration for agents with knowledge collection handling.
  - New task output tool registered to agent config.

### 🛠️ Enhancements

- 🔒 **RBAC**
  - Enhancement to RBAC permissions system.

- 📄 **Document Parser**
  - Removed unused parser files for DOCX, Markdown, PPTX, and XLSX.
  - Improved document file handling.

- 🔍 **Knowledge Search**
  - Preprocessed filters in knowledge search.
  - Converted list to string in Milvus metadata.
  - Used text type for list fields in metadata.

- 🛠️ **Toolkits**
  - Refactored summarization and web search toolkits for improved structure and error handling.
  - Removed deprecated toolkits.

### 🐛 Bug Fixes

- 🔧 **Minor Fixes**
  - Minor bug fixes across knowledge base and agent configuration.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.48.0]

✨ Discover What's New in v3.48 ✨

A focused release delivering assistant streaming improvements and better observability for the Milvus vector store.

### 🛠️ Enhancements

- 📡 **Assistant Streaming**
  - Send agent state before the final answer for real-time progress visibility.
  - Minor improvements in assistant stream handling.

- 📊 **Milvus Observability**
  - Added log limits for milvus-standalone to prevent log flooding.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.47.2] 🔧 External Task Hotfix & API Refinements

✨ Discover What's New in v3.47 ✨

A focused release with external task reliability improvements, simplified embedding info, and API endpoint cleanups.

### 🛠️ Enhancements

- 🔌 **External Task API**
  - Refactored external task function for cleaner execution.
  - Simplified external task body and schema.
  - Simplified embedding info response.
  - Minor error handling improvements.

- 🛠️ **API Cleanup**
  - Renamed agent tools endpoint for better consistency.
  - Improved error messages across the platform.

### 🐛 Bug Fixes

- 🔧 **External Task Fixes**
  - Fixed minor error handling edge cases in external task processing.
  - Fixed minor schema issue in external task response.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.46.16] 🧠 MinIO Migration, Knowledge Tools & Research Agent

✨ Discover What's New in v3.46 ✨

A major release introducing MinIO storage migration, knowledge collection support in tools, consolidated assistant APIs, significant research agent streaming improvements, and a range of schema and API enhancements.

### 🚀 New Features

- 📦 **MinIO Storage Migration**
  - Migrated knowledge collections from local file system to MinIO storage.
  - Removed S3 bucket dependency from knowledge collections.
  - Minor file path adjustments for the new storage backend.

- 🔍 **Knowledge Tools Collection Support**
  - Added collection support directly in knowledge search tools.
  - Refactored knowledge extraction with collection-aware processing.

- 🔗 **API Consolidation**
  - Consolidated all assistant-related routes into a single assistant router.
  - Removed unused and deprecated routes.
  - Added assistant thread and vector store routes.

- 🛠️ **Agent Tools API**
  - New endpoint to get agent tools by agent UUID.
  - Code optimization for agent tools retrieval.

- 🤖 **Live Agent Improvements**
  - Improved live agent with HITL support.
  - Agent name now shown in live agent context.

### 🛠️ Enhancements

- 🔬 **Research Agent**
  - Refactored research agent for better streaming performance.
  - Research system prompt refactoring and improvements.
  - Dead code removal and simplification.
  - Improved previous messages in context window.
  - Research agent tools refactoring.

- 🧠 **RAG Agent Refactoring**
  - Renamed assistant agent to RAG agent throughout the codebase.
  - Renamed assistant service files for clarity.
  - Cleanup and minor optimizations in RAG agent.

- 📋 **Schema & Data**
  - Added metadata field to AgentLLMDetail.
  - Added extra fields for embedding models.
  - Updated skills field in AgentBase schema to accept list of dictionaries.
  - Added metadata field to integration data.
  - Minor variable and field name changes.

- 🔌 **External Task API**
  - Minor improvements for external task APIs.
  - Added agent check for external tasks.

- 🏷️ **Tag Management**
  - Deleted tag ID references everywhere when the actual tag is deleted (cascade fix).

- 📊 **App Access**
  - Removed web_application app access.
  - Additional app access changes.

### 🐛 Bug Fixes

- 🔧 **Schema Fixes**
  - Fixed minor schema bugs in external task and agent endpoints.
  - Fixed intermediate message format in streaming.
  - Fixed state enrichment logic in AssistantQueryService.

- 🛠️ **General Fixes**
  - Minor bug fixes in prompts and routing.
  - Minor changes in document file handling.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.45.80] 🏗️ Class-Based Tools, Live Agent & Issue Management

✨ Discover What's New in v3.45 (continued) ✨

An extensive mid-cycle release with a major tool architecture overhaul, live agent bootstrapping, issue management improvements, task API key authentication, and significant service refactoring.

### 🚀 New Features

- 🧰 **Class-Based Tools Architecture**
  - Refactored all major tools to class-based structure: Web Browser, Web Search, Knowledge Search, Content Summarizer, Content Classification, Attachment Parser, Key Information Extractor, and Data Extractor.
  - Updated agent tools data for class-based tools.
  - Context-based tool refactoring with write-early architecture.

- 🤖 **Live Agent**
  - Bootstrapped all-new live agent module.
  - Integrated HITL (Human-in-the-Loop) into live agent.
  - HITL improvements and readiness enhancements.

- 📋 **Issue Management Improvements**
  - Issue subscribed column with user_id association.
  - Issue notification templates and notification methods for issue events.
  - Filters added for get issues by email ID.
  - Refactored issue retrieval functions with model validation.
  - Timezone handling for issue event timestamps.
  - Refactored status change handling for cleaner formatting.

- 🔑 **Task API Key Authentication**
  - Implemented API key-based authentication for task API.
  - User ID association for API keys.
  - Permission controls and route updates for task API keys.

- 📐 **Data Template Builder**
  - Added data template builder (renamed to data schema builder).
  - Minor improvements for nested field handling.
  - Moved to dedicated builders folder.

- 🧠 **Skills Column for Agents**
  - Added skills column to agent table.
  - Minor schema improvements.

### 🛠️ Enhancements

- 🔐 **Permission Module**
  - New permission module for user, user_role, and user_group management.
  - Removed deprecated permission configs.

- 🔬 **Assistant Service Refactoring**
  - Refactored assistant query service.
  - Renamed assistant service files.
  - Separate helper class for cleaner structure.
  - Removed assistant query simulation.

- ⚡ **Executor & Performance**
  - Executor optimization and cleanup.
  - Removed unused executor code.
  - Minor DB session optimizations.

- 🤖 **Agent LLM**
  - Added metadata to agent LLMs.
  - Extended LLM info in responses.
  - Updated model examples.
  - Reduced embedding dimensions for OpenAI.

- 📄 **Data Files**
  - New endpoints to get chunks and content for data files.
  - Brought prompt improvements from trigger branch.

- 📧 **Notification Updates**
  - Removed date from edit, comment, and status change notifications.
  - Minor changes in notification methods.

### 🐛 Bug Fixes

- 🔧 **Tool Fixes**
  - Fixed minor bugs in tool factory and task dispatcher.
  - Fixed minor bug in issue management routes.

- 🛠️ **Issue Model Fixes**
  - Fixed issue model validation and retrieval.
  - Deprecated unused schemas.
  - Performance improvement in issue retrieval.

- 📊 **Research Route Fixes**
  - Added file_ids in the research stream.
  - Some optimizations at function level.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.45.63]

✨ Discover What's New in v3.45 ✨

A major release bringing powerful new capabilities including a completely revamped research agent, enhanced tool system, custom embeddings support, and significant performance optimizations across the platform.

### 🚀 New Features

- 🔬 **Research Agent System**
  - All-new research agent with streaming query execution and background processing.
  - Added graph state enrichment to chat messages endpoint.
  - Implemented result clustering, sorting, and improved citation handling.
  - New research stream API with observable functions.

- 🛠️ **Tool System Revamp**
  - Revamped all Outlook, File System, and AWS S3 tools with improved schemas.
  - Added extraction and summarization tools with handler configurations.
  - Implemented classify_email_content and classify_text_content tools.
  - Added new parser tool and vision parser module with document mode support.
  - Enhanced tool output format and descriptions.

- 🧠 **Custom Embeddings Support**
  - Added embedding model APIs with seed data.
  - Updated embedding model identifiers to include provider prefix for OpenAI models.
  - Removed dense model dependency from Milvus Store and Search init.

- 📋 **Issues Management System**
  - New endpoints for issue and issue_comment models.
  - Added issue status tracking with auto-reopen logic for resolved issues.
  - Implemented search functionality for get users for issues.
  - Added tag filters for issues routes.

- 🔄 **Task Continuation (HITL)**
  - Added continue agent task API for human-in-the-loop workflows.
  - Implemented resume task execution capability.
  - Task streaming API for real-time progress updates.

- 📦 **Agent LLM Configuration**
  - New agent_llm table with dedicated endpoints and schemas.
  - Database integration for all LLM provider callers.
  - Refactored LLM settings API for active agent LLMs.

- 📁 **Office 360 Parser**
  - Unified OfficeParser for DOCX, PPTX, and XLSX files.
  - Improved document handling and processing.

### 🛠️ Enhancements

- 📊 **Performance Optimizations**
  - Optimized dashboard repo functions and email search.
  - Fixed N+1 queries in task and output repositories.
  - Improved database session management with context managers.
  - Split executor to stay within PyArmor free limit.

- 🔐 **Authentication & Security**
  - Improved error messages and status codes for authentication.
  - Enhanced global exception handler.
  - Added view_organization permission for all user roles.

- 📝 **Schema & Data Improvements**
  - Renamed RAG to Assistant across routes, schemas, and permissions.
  - Renamed chat thread to chat history with updated field names.
  - Added JSONB columns for attachments, agent_output, and agent_task metadata.
  - Improved version history schema with user email in response.

- 🤖 **Agent Builder Improvements**
  - Enhanced agent builder prompt with response_schema.
  - Improved plan and tool selection logic.
  - Added user instructions support in prompts.
  - Rules are now optional for agents.

- 📧 **Email & Task Processing**
  - Implemented email execution time tracking.
  - Added resolved status for emails when all tasks are resolved.
  - Implemented mailbox priority in processing.
  - Enhanced worker retry logic with auto-retry for knowledge worker.

- 🔍 **Knowledge & Search**
  - Added high priority setting for knowledge topics and smart fields.
  - Improved Milvus search with result clustering.
  - Implemented selective re-extraction for Smart Fields and Knowledge Topics.

- 📎 **Attachment Handling**
  - Added attachment streaming API.
  - Implemented document mode for attachment reprocessing.
  - Added page numbers for data extractor.
  - Increased max PDF pages to 100.

### 🐛 Bug Fixes

- 🔧 **Critical Fixes**
  - Fixed infinite loop in save email copy.
  - Fixed database scaling issue.
  - Fixed circular import issues.
  - Fixed task streaming bugs.

- 🛠️ **Worker & Processing Fixes**
  - Fixed email status for failed attachments.
  - Fixed task retry on INCOMPLETE and FAIL status.
  - Fixed vision parser spacing and blank page logic.
  - Fixed rotation handling bugs.

- 📊 **Data & Schema Fixes**
  - Fixed migration script issues for agent LLMs.
  - Fixed UUID validation in extraction fields.
  - Fixed stage_attachments return type mismatch.
  - Fixed user sorting issues.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.44.19] 📊 Dashboard Revamp & Task Events

✨ Discover What's New in v3.44 ✨

This release focuses on dashboard improvements, task event tracking, enhanced logging, and significant optimizations across the platform.

### 🚀 New Features

- 📊 **Dashboard Revamp**
  - New dashboard schema, routes, and repository functions.
  - Enhanced performance with optimized repository functions.
  - Improved time saved calculation logic.

- 📋 **Task Event System**
  - Added task event table with event types and additional data fields.
  - Implemented task event tracking throughout email processing.
  - Enhanced event descriptions for better visibility.

- 📄 **Document Processing**
  - Added page and word count for documents.
  - Implemented native PDF word mapper with bounding box logic.
  - Updated Langchain libraries for improved document handling.

- 🔌 **External Task API**
  - New external task schema, routes, and functions.
  - Enhanced error handling with HTTPException on failure.
  - Added permission controls for task API.

- 📈 **Grafana Integration (POC)**
  - Initial Grafana integration for monitoring and observability.

### 🛠️ Enhancements

- 📝 **Logging Improvements**
  - Major log refactoring across dispatch, task executor, and extraction tools.
  - Improved logging throughout attachment worker and OCR processing.
  - Cleaner logging with removal of unwanted debug logs.

- ⚡ **Performance Optimizations**
  - Optimized SQL for version history queries.
  - Improved agent worker with better status updates.
  - Pre-load OCR model for faster processing.
  - Optimized task events handling.

- 🤖 **Agent Builder Enhancements**
  - Improved agent builder prompt with better function documentation.
  - Added attachment validators and function docstrings.
  - Enhanced intent classification dispatcher function.

- 🔧 **LLM Provider Improvements**
  - Improved LLM provider and config correction.
  - Added LLM validation at mailbox polling.
  - Handle huge response sizes gracefully.

- 📧 **Email Processing**
  - Consider updated event in polling.
  - Improved follow-through logic in worker.
  - Added new polling_start_time in worker.

### 🐛 Bug Fixes

- 🔧 **Critical Fixes**
  - Fixed lost task due to result expiration.
  - Fixed bug in save email copy causing infinite loop.
  - Fixed staging environment issues.

- 🛠️ **General Fixes**
  - Fixed activity log repository bugs.
  - Fixed reprocess email route issues.
  - Safe removal of containers in deployment.
  - Minor fixes for agent ID handling.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.43.3] 🤖 Agent Worker & Version History

✨ Discover What's New in v3.43 ✨

This release introduces a completely revamped agent worker system, comprehensive version history tracking, and significant improvements to email event handling.

### 🚀 New Features

- 🤖 **New Agent Worker System**
  - All-new combined agent worker with multiple task support.
  - Agent queue and worker for improved dispatch.
  - Automate task retry feature implementation.

- 📜 **Version History Tracking**
  - Added version history tracking for Agent routes and Data templates.
  - New schemas, routes, and repository functions for version history.
  - Optimized version history schema and routes.
  - Database patch for version history table.

- 📧 **Email Events System**
  - All-new email events with event column in email table.
  - Renamed finalize_status to finalize_email for clarity.
  - Email events tracking in all workers.

- 🔧 **Agent Builder API**
  - Added agent builder API endpoint.
  - Added name input for agent builder.
  - New agent export schema without intent and data template.

- 📄 **PDF Parser Improvements**
  - Added images in PDF parser.
  - Optional PDF to image conversion.
  - Vision correction in PDF parser.

### 🛠️ Enhancements

- 📊 **Logging Improvements**
  - Improved logging throughout the platform.
  - Simplified rotation handler threading.
  - Clean up of unwanted debug logs.
  - Refactoring and function for execution time tracking.

- ⚡ **Memory Optimizations**
  - Memory optimization in attachment parsing.
  - Model cleanup from memory.
  - Optimized corrector processing.

- 📧 **Email Notification Optimization**
  - Optimized notification feature.
  - Changed max width to 600 for email templates.
  - Improved email cleaning methods.

- 🔧 **Worker Improvements**
  - Minor improvements in worker stability.
  - Updated attachment worker pipeline.
  - Moved external task processing from attachment.

- 🔍 **Field Mapping & Extraction**
  - Improved field meta and mapping.
  - Corrector improvement and text sanitization.
  - Handle empty data in extraction tool.

### 🐛 Bug Fixes

- 🔧 **Worker Fixes**
  - Fixed unstable self.retry() for agent worker.
  - Minor fix for attachment issues.
  - Bug fix in version history repository.

- 🛠️ **General Fixes**
  - Fixed repeated password ask bug in start script.
  - Fixed merge conflicts in attachment worker.
  - None type exception handling in data template and agent routes.
  - Fixed minor email event issues.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.42.0] 🔗 App Unification & Agent Builder

✨ Discover What's New in v3.42 ✨

This release brings significant architectural changes with app unification, a completely new agent builder, and enhanced RAG collection management.

### 🚀 New Features

- 🔗 **Web App Unification**
  - Unified RAG and web app backend.
  - Added web_application check in middleware.
  - Updated scripts with environment protection.

- 🤖 **All-New Agent Builder**
  - Completely rebuilt agent builder with improved code optimization.
  - Better handling of agent configurations.

- 📁 **RAG Collection Routes**
  - Added RAG collection and file routes.
  - Added assistant permission for RAG operations.
  - Email reprocess API endpoint.

### 🛠️ Enhancements

- 📧 **Email Processing**
  - Improved email sanitization.
  - Added 50 character limit for attachment names.
  - Handle irrelevant input gracefully.

- 📝 **Logging Improvements**
  - Improved logging in process mailbox.
  - Logging fixes in OCR processing.
  - Improved logging in PDF parser.
  - Optimizing and reorganizing of RAG routes and services.

- 🔧 **Task & Permissions**
  - Minor changes in task permissions.
  - Updated agent LLM models.
  - Bug fix in LLM provider key.

### 🐛 Bug Fixes

- 🔧 **Attachment Fixes**
  - Fixed attachment duplication bug in reprocess email.
  - None type validation for item meta fields.

- 🛠️ **General Fixes**
  - Handle empty data in extraction tool.
  - Include summary during extraction.
  - Minor improvements for SharePoint.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.41.1]

✨ Discover What's New in v3.41.1 ✨

We're excited to bring you the latest update that enhances our platform's capabilities and user experience. Let's dive into the key improvements!

### 🚀 New Features

- 🔍 **Enhanced Data File Status Tracking**
  - Introduced new EXTRACTING status for data files, providing better visibility into processing workflows.
  - Improved tracking of file processing states for better user experience.

### 🛠️ Enhancements

- 🔐 **SharePoint Permissions Optimization**
  - Optimized SharePoint permissions for enhanced security and performance.
  - Improved access control and user management capabilities.

- 📊 **Assistant Collection & File Filtering**
  - Added advanced filters for Assistant Collection and File routes for better data organization.
  - Enhanced search and filtering capabilities across collections.

- 📧 **Email Processing Improvements**
  - Added lowercase normalization for all email IDs to ensure consistency.
  - Improved email handling and processing workflows.

### 🐛 Bug Fixes

- 🔧 **Structured Response Error Handling**
  - Fixed critical issues in structured response error handling for improved reliability.
  - Enhanced error recovery and system stability.

- 🛠️ **General System Fixes**
  - Minor bug fixes and system stability improvements.
  - Deprecated unused root routes for cleaner API architecture.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.40.0] 🔧 Platform Stability & Security Enhancements

### 🛠️ Enhancements

- 🔒 **Security Module Optimization**
  - Reduced PyArmor module dependencies for improved performance and security.
  - Enhanced platform security architecture and protection mechanisms.

### 🐛 Bug Fixes

- 🛠️ **System Stability Improvements**
  - General platform optimizations and stability enhancements.
  - Improved system reliability and performance across all modules.

## [v3.39.0] 📧 Email Polling & System Reliability

### 🚀 New Features

- 📬 **Enhanced Email Polling System**
  - Preserve delta link if empty during polling for improved email synchronization.
  - Skip duplicate emails from polling to prevent data redundancy.

### 🐛 Bug Fixes

- 🔧 **Polling System Fixes**
  - Fixed critical infinite polling bug that could cause system resource issues.
  - Improved polling reliability and error handling mechanisms.

## [v3.38.0] 🛠️ Method Optimizations & System Improvements

### 🛠️ Enhancements

- ⚡ **System Method Improvements**
  - Minor changes in method implementations for better performance.
  - Optimized system processing and workflow efficiency.

## [v3.37.0] 🔗 SharePoint Collection Management

### 🚀 New Features

- 📁 **SharePoint Collection Integration**
  - Modified collection connect/disconnect site route for better SharePoint integration.
  - Enhanced SharePoint site management and connection handling.

### 🐛 Bug Fixes

- 🛠️ **General System Fixes**
  - Minor bug fixes and system optimizations.
  - Added delete tags endpoint to permissions for better access control.

## [v3.36.0] 🚀 Performance Optimization & Agent Enhancements

### 🚀 New Features

- 📊 **PDF Batch Processing**
  - Implemented PDF batch processing for improved document handling efficiency.
  - Enhanced document processing workflows and performance.

- 🤖 **Agent System Improvements**
  - Added checks for create and update agent operations for better validation.
  - Enhanced agent output handling and processing.

### 🛠️ Enhancements

- ⚡ **Performance Optimizations**
  - Further optimization of system performance and resource utilization.
  - Celery fair scheduling and priority for knowledge worker tasks.
  - Optimized implementation across various system components.

- 🗃️ **Database Improvements**
  - Minor improvements in database patch operations.
  - Enhanced database connectivity and operation handling.

### 🐛 Bug Fixes

- 🔧 **System Stability Fixes**
  - Fixed logging bugs and system stability issues.
  - Minor bug fixes across various system components.

## [v3.35.0] 🧠 Knowledge Management & LLM Provider Enhancements

### 🚀 New Features

- 🏷️ **Data Template Keywords**
  - Added keywords support in data templates for better organization and searchability.
  - Enhanced metadata handling and template functionality.

### 🛠️ Enhancements

- 🤖 **LLM Provider Improvements**
  - Improved LLM provider functionality and performance.
  - Enhanced AI integration and processing capabilities.

- 🔐 **Permission System Updates**
  - Improved permission endpoints for better access control.
  - Enhanced data access permissions and security measures.

- 📎 **Attachment Processing**
  - Sanitized attachment names for improved security and compatibility.
  - Enhanced file handling and processing workflows.

### 🐛 Bug Fixes

- 🛠️ **General Fixes**
  - Minor syntax fixes and code optimizations.
  - Improved system stability and error handling.

## [v3.34.0] 🔗 Integration & Database Improvements

### 🛠️ Enhancements

- 🗃️ **Database Optimization**
  - Updated database patch script for improved migration handling.
  - Enhanced database schema management and updates.

- 🌐 **URL Processing**
  - Minor changes in URL handling and processing.
  - Improved system integration and connectivity.

### 🐛 Bug Fixes

- 🛠️ **System Stability**
  - General system improvements and optimizations.
  - Enhanced platform reliability and performance.

## [v3.33.0] 🛠️ System Optimizations

### 🐛 Bug Fixes

- 🔧 **Start Script Fix**
  - Fixed minor bug in start script for improved system initialization.
  - Enhanced startup reliability and error handling.

## [v3.32.0] ⚡ Performance & System Updates

### 🛠️ Enhancements

- 🔧 **System Optimizations**
  - General system performance improvements and optimizations.
  - Enhanced platform stability and processing efficiency.

## [v3.31.0] 👥 User Management & SharePoint Integration

### 🚀 New Features

- 👥 **User Groups Implementation**
  - Implemented comprehensive user groups functionality for better access management.
  - Added user group access logic and permission controls.

- 📁 **SharePoint Folder Integration**
  - Added functions for SharePoint folder import and management.
  - Enhanced SharePoint site ID import functionality.

### 🛠️ Enhancements

- 📊 **Assistant System Improvements**
  - Improved Assistant email template with complete answers and formatted Markdown support.
  - Enhanced Assistant template padding and formatting for better readability.
  - Added task summary in default response schema for better context.

- 🤖 **Model & Planning Enhancements**
  - Improved model generator and keyword support functionality.
  - Added function format plan feature and removed legacy planning logic.
  - Enhanced task planning and execution workflows.

- 📧 **Chat & Communication**
  - Added AssistCX logo to email communications for better branding.
  - Minor improvements in continue_chat_url functionality.
  - Fixed chat title issue for better user experience.

### 🐛 Bug Fixes

- 🔧 **System Reliability**
  - Fixed pause task functionality and removed unused "is ready" status.
  - Fixed subject name showing as "Untitled Task" issue.
  - General bug fixes and system optimizations.
  - Added maximum length validation for collection names.

## [v3.30.0] 🔍 Enhanced Assistant Agent & Web Search

### 🚀 New Features

- 🌐 **Web Search Tool**
  - Added comprehensive web search tool for enhanced information retrieval.
  - Integrated web search capabilities into agent workflows.

- 🤖 **Assistant Agent v2**
  - Initialized Assistant Agent v2 with researcher capabilities.
  - Enhanced agent processing with improved LLM integration.

### 🛠️ Enhancements

- 🔍 **Knowledge Processing Improvements**
  - Optimized Assistant service and knowledge search functionality.
  - Enhanced Milvus search capabilities and performance.
  - Simplified knowledge_search implementation for better efficiency.

- 🌐 **Web Content Processing**
  - New web content cleaning utility for better data extraction.
  - Improved crawling tools with enhanced content processing.
  - Added cleaning functions to crawling tool for better data quality.

- 📊 **Thread Management**
  - Enhanced Assistant task and chat threads with thread_type support.
  - New thread utilities for common functions and better organization.
  - Improved source cleanup and formatting in result analysis.

### 🐛 Bug Fixes

- 🔧 **System Optimizations**
  - Fixed minor bugs in knowledge processor functionality.
  - Cleaned backend worker implementation for better performance.
  - General system stability improvements and optimizations.

## [v3.29.0] 📊 Task Management & Notification Enhancements

### 🚀 New Features

- 📊 **Assistant Data File Knowledge Route**
  - Added data file knowledge route for Assistant functionality.
  - Enhanced knowledge management and data file integration.

### 🛠️ Enhancements

- 📧 **Notification System Improvements**
  - Added more design elements to notification templates.
  - Performance enhancement in notification utilities for better efficiency.
  - Enhanced notification processing and delivery mechanisms.

- 🔐 **Permission Management**
  - Added permissions for office365-profile route access.
  - Enhanced access control and security measures.

### 🐛 Bug Fixes

- 🔧 **System Optimizations**
  - Cleaned up test modules and removed unwanted files.
  - Removed repeated library dependencies for cleaner codebase.

## [v3.28.0] 📧 Advanced Task Notifications & Processing

### 🚀 New Features

- 📧 **Task Failure Notifications**
  - Added separate failure notifications for individual tasks.
  - Enhanced notification system with detailed task status updates.
  - Added task ID to notification templates for better tracking.

- 👤 **Office365 User Profile**
  - Added office365_user_profile route for enhanced user management.
  - Integrated Office365 user data and profile handling.

### 🛠️ Enhancements

- 🌐 **Web Browsing Capabilities**
  - Added Exa API web browser tool for enhanced content extraction.
  - Improved web content processing and data gathering capabilities.

- 📊 **Task Threading & Processing**
  - New tasks now spawn new threads for better parallel processing.
  - Updated schemas to include parent ID for better task hierarchy.
  - Enhanced task management and execution workflows.

- 📄 **Document Processing**
  - Parallel processing of knowledge for improved performance.
  - Enhanced knowledge extraction and processing capabilities.
  - Improved data handling and processing efficiency.

- 🔍 **Search & Data Management**
  - Only published collections are now included in search results.
  - Added minimum length validation for knowledge_topic and smart_field names.
  - Enhanced data validation and quality control measures.

### 🐛 Bug Fixes

- 🔧 **System Reliability**
  - Updated permissions and fixed database session issues.
  - Minor improvements in notification functions and error handling.
  - Enhanced system stability and reliability across modules.

## [v3.27.0] 🔍 Knowledge Management & Data Processing

### 🚀 New Features

- 🗃️ **Data File Knowledge Route**
  - Added comprehensive data file knowledge route for enhanced data management.
  - Improved knowledge extraction and file processing capabilities.

### 🛠️ Enhancements

- 🔍 **Knowledge Source Formatting**
  - Hierarchical knowledge source formatting for better organization.
  - Enhanced source formatting and presentation in knowledge systems.

- 📊 **Filter Processing**
  - Improved filter processing capabilities for better data handling.
  - Enhanced search and filtering mechanisms across the platform.

### 🐛 Bug Fixes

- 🔧 **System Improvements**
  - Minor improvements and optimizations across various components.
  - Enhanced system stability and performance.

## [v3.26.0] 📧 Email Notifications & System Enhancements

### 🚀 New Features

- 📧 **Email Task Notifications**
  - Initial implementation of comprehensive email task notifications.
  - Enhanced communication system for task updates and status changes.

### 🛠️ Enhancements

- 🔄 **Reindexing Capabilities**
  - Added route to reindex files for better search and data management.
  - Added permissions for reindex API to ensure proper access control.

- 🌐 **Web Browser Implementation**
  - Exa API web browser tool for enhanced content gathering from URLs.
  - Improved web content processing and data extraction capabilities.

- 📄 **Document Processing**
  - Improved structure of attachment parser for better document handling.
  - Enhanced attachment processing and data extraction workflows.

### 🐛 Bug Fixes

- 🔧 **Email Notifications**
  - Fixed bugs in email failure notification system.
  - Enhanced notification reliability and delivery mechanisms.

- 🛠️ **General Improvements**
  - Black formatter updates for better code consistency.
  - Minor improvements across various system components.

## [v3.25.0] 🚀 Platform Optimizations & Agent Removal

### 🛠️ Enhancements

- 🤖 **Agent Management**
  - Removed pre-built agent creation for more flexible custom agent workflows.
  - Enhanced agent customization and management capabilities.

### 🐛 Bug Fixes

- 🔧 **System Optimizations**
  - General platform optimizations and performance improvements.
  - Enhanced system stability and reliability.

## [v3.24.0] 🌐 Web Application Access & Context Enhancement

### 🚀 New Features

- 🌐 **Web Application Access**
  - Implemented comprehensive web application access functionality.
  - Added app access data and Assistant access permissions for enhanced security.

### 🛠️ Enhancements

- 📊 **Context & Knowledge Processing**
  - Add context in knowledge extraction for improved accuracy.
  - Enhanced context prompts and knowledge processing workflows.
  - Improved search result sorting order and result limiting.

- 🔍 **Metadata & Search Improvements**
  - Include null values in metadata processing for comprehensive data handling.
  - Enhanced metadata processing and search capabilities.

### 🐛 Bug Fixes

- 🔧 **Data Processing**
  - Replaced field in content when re-processing for better data consistency.
  - Fixed minor bugs in utils schema and user management.
  - Enhanced data validation and processing reliability.

## [v3.23.0] 🏷️ Tagging System & Metadata Management

### 🚀 New Features

- 🏷️ **Comprehensive Tagging System**
  - Added complete tagging system with tags table, schemas, and routes.
  - Implemented tags in email and agent_tasks responses for better organization.
  - Added permissions for delete routes for intents, data templates, agent tools, and mailbox pollings.

- 📊 **Smart Fields & Knowledge Topics**
  - Added smart fields and knowledge topics functionality.
  - New APIs for hybrid search and metadata field management.
  - Enhanced knowledge extraction and topic management capabilities.

### 🛠️ Enhancements

- 🔍 **Search & Query Improvements**
  - Implemented global search functionality across the platform.
  - Enhanced search capabilities with list filter support.
  - Improved planning prompts and search result processing.

- 📄 **Document Processing**
  - Added document-query route for enhanced document interaction.
  - Enhanced metadata handling and document processing workflows.
  - Improved data validation and field management.

- 🌐 **Web Integration**
  - Fully functional worker with web_search_enabled capabilities.
  - Added web search column for Assistant tasks and enhanced web integration.
  - Improved web search functionality and API inheritance.

### 🐛 Bug Fixes

- 🔧 **System Stability**
  - Fixed minor bugs in knowledge topics and smart field routes.
  - Enhanced data collection and document processing reliability.
  - Improved system validation and error handling mechanisms.

## [v3.22.0] 🧠 Advanced Knowledge Extraction & User Management

### 🚀 New Features

- 👥 **Enhanced User Role Management**
  - Added new APIs for comprehensive user role management.
  - Implemented user role checks for create and update user operations.
  - Added permissions for tags and enhanced access control.

- 🧠 **Advanced Knowledge Processing**
  - Added advanced_knowledge_extraction option for enhanced data processing.
  - Implemented structured extraction for smart fields with improved accuracy.
  - Enhanced knowledge search and planning capabilities with better AI integration.

### 🛠️ Enhancements

- 🔍 **Search & Discovery**
  - Improved hybrid search functionality with enhanced result accuracy.
  - Enhanced Milvus search capabilities and planning prompt optimization.
  - Consistent output in Milvus query processing for better reliability.

- 📊 **Data Management**
  - Bootstrapped knowledge extraction process with automated workflows.
  - Improved document insertion and data processing efficiency.
  - Enhanced metadata handling with record type inclusion.

- 🔧 **System Architecture**
  - Renamed alias to keywords for collections for better semantic clarity.
  - Updated schemas and migration scripts for enhanced data structure.
  - Added TODO items and documentation for future development.

### 🐛 Bug Fixes

- 🛠️ **Database & Processing**
  - Fixed minor bugs in Tags system and knowledge extractor.
  - Enhanced data collection and file processing reliability.
  - Improved system stability and error handling across modules.

## [v3.21.0] 🛡️ Security & Profile Management

### 🚀 New Features

- 🔐 **Enhanced Security Features**
  - Implemented comprehensive permissions for Assistant access control.
  - Added triage node implementation for query safety and content filtering.
  - Alerts system for harmful query detection and prevention.

- 👤 **Profile Management System**
  - Added profile routes for Assistant functionality.
  - Enhanced user profile management and access control.
  - Implemented app access functionality for better user experience.

### 🛠️ Enhancements

- 🤖 **Agent & Task Processing**
  - Enhanced agent tools filters and improved agent authentication.
  - Added support for reasoning-only tasks with specialized prompts.
  - Implemented timestamp schedule support and helper functions.

- 📄 **Document Processing**
  - Implemented native PDF parser for improved document handling.
  - Enhanced document processing workflows and parsing accuracy.

- 💬 **Communication System**
  - Added pagination for chat messages for better performance.
  - Enhanced chat thread management and message handling.

### 🐛 Bug Fixes

- 🔧 **System Reliability**
  - Fixed issues in email repository and search functionality.
  - Enhanced agent task status handling and validation.
  - Improved system stability and error handling mechanisms.

## [v3.20.0] 🛠️ Agent Tools & System Optimizations

### 🚀 New Features

- 🔧 **Agent Tools Management**
  - Added comprehensive agent tools filter functionality in routes, schemas, and repository.
  - Enhanced agent tool organization and management capabilities.

### 🛠️ Enhancements

- 🤖 **LLM Provider Enhancements**
  - Added max tokens configuration for LLM provider settings.
  - Enhanced AI processing capabilities and resource management.

- 📊 **Debug & Monitoring**
  - Added extra debug logs for better system monitoring and troubleshooting.
  - Enhanced logging capabilities across various system components.

### 🐛 Bug Fixes

- 🔧 **Authentication & Processing**
  - Fixed bug in agent authentication routes for improved security.
  - Enhanced authentication reliability and error handling.
  - Minor improvements in system processing and optimization.

## [v3.19.0] 🔧 Tool Management & System Improvements

### 🚀 New Features

- 🛠️ **Enhanced Tool Management**
  - Comprehensive improvements to agent and system tool handling.
  - Enhanced tool integration and management capabilities.

### 🛠️ Enhancements

- ⚡ **Performance Optimizations**
  - General system performance improvements and optimizations.
  - Enhanced processing efficiency and resource utilization.

### 🐛 Bug Fixes

- 🔧 **System Stability**
  - Various bug fixes and stability improvements across the platform.
  - Enhanced error handling and system reliability.

## [v3.18.0] 📧 Outlook Integration & File System Tools

### 🚀 New Features

- 📧 **Enhanced Outlook Integration**
  - Comprehensive Outlook tools including email management, archiving, and deletion.
  - Added Outlook user profile tool for better user management.
  - Implemented draft email and reply email tools with attachment support.

- 📁 **File System Tools**
  - Added comprehensive file system tools: write, read, copy, move, delete, list, and search.
  - Enhanced file management capabilities with improved upload and download functionality.

- ☁️ **AWS S3 Integration**
  - Added AWS S3 upload file tool with comprehensive cloud storage management.
  - Enhanced cloud integration and file storage capabilities.

### 🛠️ Enhancements

- 📄 **Document Processing**
  - Added OCR page limit functionality for improved document processing.
  - Enhanced attachment processing and file handling workflows.
  - Improved document parsing and text extraction capabilities.

- 🤖 **Agent & Task Management**
  - Added RESOLVED status in agent task update routes.
  - Enhanced agent processing with improved LLM integration.
  - Added file metadata support for searching data files.

- 📧 **Email Processing**
  - Modified email date filtering for received_at timestamp.
  - Enhanced email search and filtering capabilities.
  - Improved email management and processing workflows.

### 🐛 Bug Fixes

- 🔧 **System Reliability**
  - Fixed PDF parser data removal bug for improved document processing.
  - Enhanced system stability and error handling mechanisms.
  - Minor bug fixes in document processing and attachment handling.

## [v3.17.0] ⚡ OCR & System Optimizations

### 🚀 New Features

- 📄 **Enhanced OCR Processing**
  - Added OCR page limit to mailbox polling for better resource management.
  - Enhanced optical character recognition capabilities and performance.

### 🛠️ Enhancements

- 🔧 **Tool Management**
  - Renaming and optimization of agent tools for better organization.
  - Enhanced tool configuration and management capabilities.

- 📊 **Search & Processing**
  - Additional search scope options for improved data discovery.
  - Enhanced search capabilities across various data types.

### 🐛 Bug Fixes

- 🔧 **System Stability**
  - Minor changes and optimizations in various system components.
  - Enhanced system reliability and performance.

## [v3.16.2] Platform Foundation & Core Features

We're excited to bring you the latest update that enhances our platform's capabilities and user experience. Let's dive into the key improvements!

### 🚀 New Features

- 👥 **Multiple User Sessions**
  - Introduced support for multiple concurrent sessions per user, enhancing multi-tasking capabilities.
  - Improved session management and resource allocation for better user experience.

### 🛠️ Enhancements

- 🔄 **Celery Worker Improvements**
  - Enhanced worker cleanup and performance optimizations for better task processing.
  - Improved async pool management and connection handling.

### 🐛 Bug Fixes

- 🤖 **Assistant Agent Fixes**
  - Resolved issues in Assistant agent functionality for improved accuracy and reliability.
  - Fixed various bugs in agent processing and response generation.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.15.0] 🚀 Advanced Storage & Knowledge Management

### 🚀 New Features

- 📁 **Multi-Storage Mount Support**
  - Introduced support for multiple storage mount points, enabling flexible data organization.
  - Enhanced file system management with improved storage configuration options.

- 🧠 **Private Data Collections**
  - Added private data collection functionality with enhanced permission controls.
  - Implemented user-specific data isolation for improved security and privacy.

### 🛠️ Enhancements

- 🔍 **Knowledge Search Improvements**
  - Enhanced LLM-assisted document retrieval for more accurate search results.
  - Improved Milvus search capabilities with better indexing and performance.

- 📊 **Task Management System**
  - Enhanced task-email status linking for better workflow tracking.
  - Improved agent task monitoring and progress reporting.

### 🐛 Bug Fixes

- 🔧 **Data Extraction Fixes**
  - Resolved issues in data extractor model generation and processing.
  - Fixed bugs in extraction tool metadata handling and cleanup.

## [v3.14.0] 🌟 Graph-Based Processing & Assistant Enhancements

### 🚀 New Features

- 🕸️ **Graph-Based Agent Processing**
  - Introduced graph-based worker architecture for improved task processing.
  - Enhanced agent workflow management with better state handling.

- 🧠 **Advanced Assistant Capabilities**
  - Implemented comprehensive Assistant simulation and testing APIs.
  - Added sophisticated knowledge retrieval with improved context understanding.

### 🛠️ Enhancements

- 📄 **Document Processing Improvements**
  - Enhanced OCR capabilities with RapidOCR integration for better text recognition.
  - Improved document parsing with better layout and structure detection.

- 🔒 **Enhanced Security & Permissions**
  - Strengthened permission system for collections and data files.
  - Improved access control mechanisms across the platform.

### 🐛 Bug Fixes

- 🔧 **Pipeline Stability**
  - Resolved issues in document processing pipeline for more reliable extraction.
  - Fixed various bugs in agent task execution and monitoring.

## [v3.13.0] 🛠️ Infrastructure & Performance Optimization

### 🚀 New Features

- 📊 **Enhanced Monitoring & Analytics**
  - Introduced comprehensive activity logging and notification system.
  - Added detailed task tracking and performance metrics.

### 🛠️ Enhancements

- 🚀 **Performance Optimizations**
  - Improved memory efficiency in embeddings and document processing.
  - Enhanced batch processing capabilities for better throughput.

- 🔄 **System Reliability**
  - Strengthened error handling and recovery mechanisms.
  - Improved database migration and schema management.

### 🐛 Bug Fixes

- 🔧 **System Stability**
  - Resolved issues in thread management and concurrent processing.
  - Fixed various bugs in data collection and file handling.

## [v3.12.0] 📊 Data Management & Integration Enhancements

### 🚀 New Features

- 🗂️ **Advanced Data File Management**
  - Enhanced data file status tracking and processing workflows.
  - Improved file organization and metadata handling.

### 🛠️ Enhancements

- 🔗 **Integration Improvements**
  - Strengthened SharePoint integration with better error handling.
  - Enhanced data synchronization and processing capabilities.

- 📈 **Analytics & Reporting**
  - Improved dashboard functionality with better data visualization.
  - Enhanced export capabilities for agent tasks and data analysis.

### 🐛 Bug Fixes

- 🔧 **Processing Reliability**
  - Fixed issues in data extraction and validation processes.
  - Resolved bugs in agent task execution and status reporting.

## [v3.11.0] 🔍 Search & Discovery Enhancements

### 🚀 New Features

- 🔍 **Advanced Search Capabilities**
  - Enhanced search functionality with improved result accuracy.
  - Added hybrid search options for better content discovery.

### 🛠️ Enhancements

- 📚 **Knowledge Base Improvements**
  - Optimized knowledge collection management and organization.
  - Enhanced document indexing and retrieval performance.

- 🎯 **User Experience**
  - Improved interface responsiveness and navigation.
  - Enhanced user workflow efficiency and task management.

### 🐛 Bug Fixes

- 🔧 **System Reliability**
  - Resolved issues in search indexing and result ranking.
  - Fixed various bugs in collection management and data processing.

## [v3.10.0] 🚀 AI & Automation Enhancements

### 🚀 New Features

- 🤖 **Enhanced AI Capabilities**
  - Improved agent processing with better LLM integration.
  - Enhanced automated task execution and workflow management.

### 🛠️ Enhancements

- ⚡ **Performance Optimizations**
  - Optimized database queries and improved system response times.
  - Enhanced memory management and resource utilization.

- 🔄 **Process Automation**
  - Streamlined task routing and execution workflows.
  - Improved background processing and queue management.

### 🐛 Bug Fixes

- 🔧 **System Stability**
  - Resolved issues in agent task processing and execution.
  - Fixed various bugs in data validation and error handling.

## [v3.9.0] 🌟 Platform Modernization & Integration Expansion

### 🚀 New Features

- 🔗 **Expanded Integration Support**
  - Enhanced platform integration capabilities with improved API handling.
  - Strengthened third-party service connections and data synchronization.

### 🛠️ Enhancements

- 🏗️ **Architecture Improvements**
  - Modernized platform architecture for better scalability.
  - Enhanced system reliability and performance optimization.

- 📊 **Data Processing Enhancements**
  - Improved data extraction and processing workflows.
  - Enhanced validation and error handling mechanisms.

### 🐛 Bug Fixes

- 🔧 **System Reliability**
  - Resolved critical issues in platform stability and performance.
  - Fixed various bugs in data processing and system integration.

## [v3.8.3] 🚀 Email & Polling System Enhancements

We're excited to bring you the latest update that enhances our platform's capabilities and user experience. Let's dive into the key improvements!

### 🚀 New Features

- ✉️ **Enhanced Email Functionalities**
- Introduced functionality to archive emails, enhancing email organization and management.
- Introduced functionality to delete archived emails, streamlining email cleanup and maintenance.

### 🛠️ Enhancements

- ⚙️ **Polling & Redbeat Task Enhancements**
  - Optimized Redbeat task names for improved handling in multi-organization setups.
  - Added functionality to update Redbeat tasks when updating polling configurations.
  - Improved polling request verification to return more detailed error messages.
  - Functional improvements in polling startup to ensure smoother execution.

- 🔒 **Security & Validation Improvements**
  - Mailbox polling email is now restricted in notification recipients to prevent polling conflicts.
  - Added an exception block for token encryption and decryption, improving error handling.

- 🔄 **System Stability & Configurations**
  - Added set_configurations in Redis on startup, ensuring necessary configurations are set automatically.
  - Functional enhancements in deactivating integrations, ensuring seamless removal.

### 🐛 Bug Fixes

- 🏢 **Integration Fixes**
  - Fixed a database session bug related to integrations, preventing session conflicts.

We continuously work to improve our platform, making it more robust, flexible, and user-friendly. Thank you for your continued support and feedback! 🚀

## [v3.8.1] 🚀 Schema and Performance Optimizations & Integration Enhancements

### 🚀 New Features

- 🔌 **Introducing S3 & Outlook Integrations**
  - S3 bucket and Outlook are now fully integrated, allowing seamless data storage and email handling.
  - Added API routes for creating and updating integrations during platform setup.

- 📄 **Document Parsers for Better File Support**
  - Added support for docx, pptx, and xlsx file parsing to enable better extraction and processing of structured document data.

- 🧠 **LangGraph Integration**
  - Added langgraph to enhance AI-driven workflows and task automation.

### 🛠️ Enhancements

- 🔍 **OCR Enhancements**
  - Added confidence_score to OCR Mapper for improved text recognition accuracy.

- ⚡ **Schema and Pagination Optimizations**
  - Optimized all schemas for better query performance.
  - Removed all deprecated v1 routes and optimized pagination for improved performance.

- 🔧 **API & Platform Setup Improvements**
  - Added functionality to create and update integrations in platform setup routes.
  - Optimized API permissions and centralized task event descriptions for better logging.

- 🏢 **User Role & Access Enhancements**
  - Added user role checks for create and update user operations.
  - Removed ROOT collection from permissions data access for better access control.

- 🌍 **External Task Handling Enhancements**
  - External tasks are now managed through attachment-worker, reducing processing latency.
  - Improved error handling and logging for better debugging.

### 🐛 Bug Fixes

- 🛠 **SharePoint & Collection Fixes**
  - Bulk downloads now support only files, preventing unintended folder downloads.
  - Added detailed error messages for failures in SharePoint downloads and data file uploads.
  - Fixed multiple issues in SharePoint integration, improving reliability.
  - Improved handling of attachment task progress updates.

- 🔑 **Authentication & Token Management**
  - Renamed ACCESS_DURATION to TOKEN_VALIDITY for consistency.
  - TOKEN_VALIDITY can now be set via environment variables.

## [v3.7.0] 🚀 Integration Systems, Document Processing & Collection Management

### 🚀 New Features

- 🔌 **Introducing OpenAI & SharePoint Integrations**
  - Introduced a new integrations feature and added bindings for each integration to LLMs and agent tools.
  - Seamlessly integrate with OpenAI and SharePoint for enhanced AI-powered capabilities and document management.

- 📄 **Document Processing System**
  - Added support for Markdown parsing to improve text processing and formatting.
  - A powerful new parser for handling document content extraction with improved accuracy.
  - Combined Text Data Extractor and Visual Data Extractor for streamlined processing.

### 🛠️ Enhancements

- ⚡ **Performance Optimizations in Collection Management**
  - Optimized performance and implemented optional pagination in collection routes.
  - Improved collection and data file deletion processes.

- 🔄 **Process Optimization**
  - Enhanced SharePoint file processing through attachment handler queue.
  - Added functionality for multiple agents in the agent preview route.
  - Improved task event descriptions for better clarity.

- 🔐 **Permission Controls**
  - Added integration permissions and updated agent and agent LLM permissions.
  - Combined webapp and platform permissions for better user experience.

- 📝 **Documentation & System Updates**
  - Minor text refinements and API endpoint improvements.
  - Added a new FAQ section in the README.

- 🎨 **User Experience Enhancements**
  - Added hover effects on cards and refined icons.
  - Improved extractors, wrapped text for fields and PDF zoom.

### 🐛 Bug Fixes

- 📄 **Data Extractor Bug Fixes**
  - Fixed major issues in Data Extractor initialization.
  - Minor bug fix in OCR parser import.

- 🔧 **Fixed Token Refresh Issue**
  - Resolved issues related to token refresh, thus preventing authentication failures.
  - Implemented automatic request retry after token refresh, improving session stability and user experience.

## [v3.6.1] 🚀 AI Enhancements, Deployment Flexibility & Multi-Organization Improvements

### 🚀 New Features

- 🆕 **Extract Data from Attachment Tool**
  - Introducing a powerful new feature for AI agents that enables seamless data extraction directly from attachments. This tool streamlines information processing and improves overall workflow efficiency.

### 🛠️ Enhancements

- 🌐 **Enhanced Deployment Flexibility**
  - Our nginx configuration now supports custom domain names for both backend and frontend applications. This update allows for more user-friendly and professional webapp URLs, giving you greater control over your application's presentation.
- 🔧 **Multi-Organization API Handling**
  - Major improvements in our multi-organization setup now supports:
    - Efficient handling of concurrent API calls.
    - Optimized backend resource utilization.
    - Improved system scalability and performance.

### 🐛 Bug Fixes

- Resolved critical issues in multi-organization API call management.
- Enhanced system stability and resource allocation.

## [v3.5.7] 🚀 PDF Rotation Fixes & Docker Enhancements

### 🚀 New Features

- 🔄 **Doctr-Based Fix for Page Rotation**
  - Implemented an improved version of doctr for handling more complex PDF rotations in mailbox polling.
  - This update enhances the AI's ability to understand and process rotated PDFs. The feature is now available under the "Fix Page Rotation" option in mailbox polling.

### 🛠️ Enhancements

- 🐋 **Docker Image Building Script**
  - Improved the Docker image building script for Windows, streamlining the process for better compatibility and performance.
- ⚙️ **Increased Max Iteration Steps**
  - Increased the maximum iteration steps from 10 to 30, allowing AI agents to handle more steps within the same task, improving task efficiency and flexibility.

## [v3.4.0] 🚀 Platform Optimization & Backend Updates

### 🚀 New Features

- 🖥️ **Staged Mode for Remote Servers**
  - You can now use the `start.sh` script to start the platform in **staged mode** on remote servers.
  - This will start services in a staged manner, optimizing resource utilization by gradually launching different components.
  - Simply add the `--staged` option to the command to enable this feature.

### 🛠️ Enhancements

- 🛠️ **Backend Updates**
  - Introduced backend change logs for better tracking and transparency.
  - Made minor system stability improvements to ensure smoother performance.
- 📝 **Blank Page Detection Improvement**
  - Improved blank page detection using pixel density methods for more accurate identification and better document extraction.

### 🐛 Bug Fixes

- 📄 **PDF Extractor Fixes**
  - Fixed issues in the PDF extractor to better handle corrupted PDF files, ensuring more reliable document processing.

## [v3.3.0] ⚙️ API Enhancements & Document Handling Improvements

### 🚀 New Features

- 🔄 **Retry Mechanism**
  - Introduced a retry mechanism to handle occasional orientation correction failures, improving reliability.

### 🛠️ Enhancements

- 🔧 **API Tool Configuration**
  - Major improvements to the API tool configuration for better flexibility and performance.
- 📑 **Page Rotation & Padding Enhancements**
  - Added padding after image rotation to remove excess whitespace, improving document presentation.
  - Implemented auto-cropping based on the non-white pixel bounding box for a cleaner output.
  - Applied adjustable margins to ensure content is consistently centered with even padding.

### 🐛 Bug Fixes

- 🔄 **Page Orientation Correction**
  - Fixed issues with page orientation correction, ensuring more accurate page alignment and consistency.

## [v3.2.5] ⚙️ Stability, Access Control & User Experience Enhancements

### 🚀 New Features

- 🗂️ **Enhanced Mailbox Pollings**
  - Introduced a "Preserve Page Layout" option to maintain layout consistency during processing.
- 🔐 **Knowledge Collection Permissions**
  - Implemented user permissions for knowledge collections to improve access control and data security.

### 🛠️ Enhancements

- 📄 **Document Formatting & Text Display**
  - Adjusted the maximum word count for better document text formatting.
  - Enhanced text display in the attachment viewer for improved readability.
- 🎨 **User Experience Enhancements**
  - Made minor text formatting changes for better clarity and presentation.
  - Optimized code for improved system performance and maintainability.

### 🐛 Bug Fixes

- 🔄 **Page Rotation & Alignment**
  - Resolved issues with page rotation to ensure proper alignment and improved processing accuracy.
- 📍 **Stepper Navigation**
  - Fixed a sticky positioning issue in stepper navigation for a smoother user experience.
- 🔧 **Redis Connection Stability**
  - Fixed Redis connection pool settings:
    - Increased connection pool size and maximum Redis connections.
    - Enabled retries with maximum retry attempts for broker connection.
    - Configured connection timeout, heartbeat interval, and retry options for improved stability.

## [v3.2.0] 📄 Advanced Document Processing & Access Control

### 🚀 New Features

- 🔍 **Dynamic PDF Zoom**
  - Introduced dynamic zoom functionality in PDF images to provide an improved viewing and navigation experience.
- 🔐 **Enhanced Permissions for Collections**
  - Added new permissions to collections, allowing for better access control and management.
- 🔄 **Automatic Page Rotation Correction**
  - Added a "Fix Page Rotation" option in mailbox pollings to automatically adjust page orientation for accurate processing.

### 🛠️ Enhancements

- 📑 **OCR Document Processing Enhancements**
  - Enhanced layout and text support for improved recognition and structuring of documents.

## [v3.1.0] 🛠️ Enhanced Functionality, Usability, & Fixes

### 🚀 New Features

- 📄 **Document Handling Enhancements**
  - Implemented orientation from polling configs for dynamic page rotation adjustments.
  - Integrated Doctr-based page orientation for improved document processing.

### 🛠️ Enhancements

- ⚙️ **Data Handling & Flexibility**
  - Updated the nested model function in the data extractor for better handling of complex data structures.
  - Enhanced the field serializer for OCR JSON to improve data formatting and processing.
  - Increased the maximum character length from 25 to 80 for greater data flexibility.
- 🖼️ **User Interface Enhancements**
  - Applied UI improvements to agent components, data schema cards, and instructional elements for a polished appearance.
  - Updated the agent interface with intuitive UI enhancements for a better user experience.
  - Made minor UI adjustments in the file upload interface to enhance usability.
  - Added icons in the step form for better visual representation and navigation.
  - Improved hint texts on hover cards in settings for clearer guidance.
  - Enhanced agent instructions and text for improved clarity and user guidance.
- 📦 **Component Optimization**
  - Optimized agent and data template components for consistent functionality and design.

### 🐛 Bug Fixes

- 🔧 **Data Extraction Fixes**
  - Resolved bugs in the data extractor to address extraction and handling issues.
  - Applied fixes to improve accuracy in data extraction.
- 👤 **Agent & User Data**
  - Fixed issues with user data updates for better reliability.
  - Resolved an agent search issue to deliver more accurate and reliable results.

## [v3.0.0] 🌟 Advanced Data Handling & Enhanced Document Analysis

### 🚀 New Features

- 🖼️ **Formatted Image Data**
  - Added support for formatted image data, improving overall image handling and processing.
- 📋 **Pydantic-Based Data Extraction**
  - Integrated Pydantic for enhanced data validation and parsing during extraction.
- 👁️ **Vision Extraction**
  - Implemented vision extraction from tool runtime to enable more advanced document analysis capabilities.

### 🛠️ Enhancements

- ⚙️ **Improved Model Generation**
  - Enhanced data extractor model generation for greater accuracy in data processing.
- 🔧 **Data Cleanup & Optimization**
  - Made minor updates to data extraction and cleanup processes for improved performance and reliability.
- 🎨 **UI Enhancements**
  - Applied UI patches to resolve visual inconsistencies and improve the overall user experience.

### 🐛 Bug Fixes

- 🆔 **Identifier Bug Fixes**
  - Resolved bugs related to identifiers to ensure smoother data handling.
- 🛠️ **Visual Data Extractor**
  - Fixed data type issues in the visual data extractor, ensuring accurate and reliable data extraction.

## [v2.9.0] 🔍 Enhanced Data Processing & Schema Alignment

### 🛠️ Enhancements

- 📚 **Upgraded LangChain**
  - Enhanced support and functionality for language models by upgrading LangChain.
- 📊 **Visual Data Extractor**
  - Updated the visual extractor to improve data extraction accuracy and efficiency.
- ⚙️ **Data Extractor Enhancements**
  - Improved the data extractor for cleaner and more efficient processing.
  - Enhanced the data extraction tool for better performance and functionality.
- 🔧 **JSON Handling**
  - Added functions to clean escape characters from JSON, ensuring improved data handling and reliability.
- 📝 **Data Template Schema Updates**
  - Updated the data template schema for better alignment with modern data standards and improved usability.

### 🐛 Bug Fixes

- 🛠️ **Schema Data Type Fixes**
  - Resolved data type issues in the data template schema to enhance accuracy and consistency.

## [v2.5.0] ⚙️ Advanced Integrations & Enhanced Usability

### 🛠️ Enhancements

- ⚙️ **Upgraded Pydantic & OpenAI SDK**
  - Upgraded Pydantic and integrated the OpenAI SDK to ensure better compatibility and streamlined functionality.
- 📊 **Visual Data Extractor**
  - Introduced a visual data extractor with block sorting and parsing to improve data handling and organization.
- ✉️ **Email Subject Display**
  - Limited the data displayed in email subjects to prevent information overload and improve clarity.
- 🌟 **Integration Module UI**
  - Updated the integration module interface to enhance usability and streamline workflows.

### 🐛 Bug Fixes

- 🔎 **Inbox Search**
  - Resolved issues with search functionality to ensure more accurate and reliable results.
- 📝 **Text Overflow**
  - Fixed a text overflow issue in the "Extract Data" tab, improving readability and maintaining layout consistency.
- 🔧 **Type Error Resolution**
  - Addressed type error issues to enhance system reliability and accuracy.

## [v2.3.2] 🛠️ Improved Accuracy & User Clarity

### 🛠️ Enhancements

- 📄 **OCR & Data Extraction**
  - Enhanced OCR and data extraction capabilities to deliver greater accuracy and improved processing efficiency.
- 📝 **Document Instructions**
  - Updated the "Document Instruction" section in the data template card for clearer guidance and an enhanced user experience.

### 🐛 Bug Fixes

- ⚠️ **Agent Card Warnings**
  - Resolved a warning issue in the agent card, ensuring better stability and a cleaner, more professional user interface.

## [v2.3.1] ⚡ UI Enhancements & Functionality Improvements

### 🛠️ Enhancements

- 📄 **Optimized Pagination**
  - Enhanced pagination functionality to ensure smooth and reliable navigation.
- 👤 **Agent Details UI**
  - Updated the interface for a more intuitive and user-friendly experience.

### 🐛 Bug Fixes

- 📝 **Description Overflow**
  - Resolved overflow issues to maintain a consistent and clean presentation of content.
- 🔧 **Agent Tools**
  - Fixed minor bugs to improve overall functionality and performance.

## [v2.3.0] 🎨 Visual Upgrades & Stability Enhancements

### 🚀 New Features

- 🖼️ **Enhanced Collection Icons**
  - Introduced new icons for better visual representation and easier navigation.

### 🛠️ Enhancements

- 📁 **Default File Icons**
  - Set default file icons in the collection component to ensure visual consistency.
- 🛠️ **Library Updates**
  - Upgraded the `date-fns` library to resolve peer dependency issues and improve compatibility with other packages.

### 🐛 Bug Fixes

- 📄 **OCR Improvements**
  - Fixed issues with OCR and page orientation to enhance document processing accuracy.
  - Resolved an equality operator bug in OCR geometry to ensure consistent data comparison.
- 📚 **Knowledge Collections**
  - Addressed minor bugs to boost stability and overall performance.

## [v2.2.2] ⚙️ Enhanced LLM Parsing & User Experience

### 🚀 New Features

- Implemented UI enhancements and integrated Knowledge Collection APIs for data files to improve user e functionality.

### 🛠️ Enhancements

- 📊 Enhanced Data Extractor for more accurate parsing of LLM outputs.

### 🐛 Bug Fixes

- 👤 Fixed issues with validation and structure during root user creation.
- 📬 **Inbox Navigation**
  - Resolved navigation-related issues for a smoother user experience.

## [v2.2.1] 📁 Knowledge Collection Management Upgrade

### 🛠️ Enhancements

- 📚 **Enhanced knowledge collection management**
  - Added icons for collections.
  - Improved collection deletion process with automatic cleanup of files.
  - Added better overview of collection contents.
  - Enhanced collection listing and organization.

### 🐛 Bug Fixes

- 🔎 **Persistent Search Preferences**
  - Fixed issues with search settings retention.
  - Consistent search experience across email interactions.

## [v2.1.0] 🚀 New Integrations !

### 🚀 New Features

- 📁 **Introducing Sharepoint Integration**
  - Implemented comprehensive credential validation.
  - Improved security measures for data handling.

### 🛠️ Enhancements

- Enhanced user permission for managing agents.
- Better error handling and user feedback at API level.
- Knowledge Collections now shows collection size and file count.

## [v2.0.0] 🌟 Major Platform Transformation

### 🛠️ Enhancements

- 🔧 **Task Management System Overhaul**
  - Comprehensive task progress monitoring.
  - Real-time status updates.
  - Improved task execution reliability.
- 🛠 **Platform Tools**
  - Simplified platform deployment by introducing `POST/setup_platform` and `POST/update_platform` API endpoints.

## [v1.2.0] 🚀 User Management & Productivity Boost

### 🛠️ Enhancements

- 🔐 **Role-Based Access Control (RBAC)**
  - Granular permission settings.
  - Enhanced security through precise user role definition.
  - Simplified access management for administrators.
- 📁 **Excel Export Capabilities**
  - Search results now exportable to Excel format.
  - Seamless data transfer for further analysis.

## [v1.1.1] 🛡️ Stability Update

### 🛠️ Enhancements

- 🖨️ **Advanced Document Scanning Engine**
  - **Cutting-Edge Text Recognition**
    - Improved optical character recognition (OCR).
    - Enhanced ability to read complex document layouts.
    - Increased accuracy in text extraction.
  - **Performance Enhancements**
    - Significantly faster processing speeds.
    - Optimized scanning algorithms.
    - Reduced resource consumption.
  - **Accuracy Improvements**
    - More precise document analysis.
    - Better handling of varied document types.
    - Increased confidence in text extraction.
