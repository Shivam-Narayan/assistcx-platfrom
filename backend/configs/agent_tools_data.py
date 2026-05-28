AGENT_TOOLS_TYPE = [
    {
        "name": "Base tool",
        "key": "BASE_TOOL",
        "description": "Base tools for the agent",
    },
    {
        "name": "Email tool",
        "key": "EMAIL_TOOL",
        "description": "Base tools for the agent",
    },
    {
        "name": "API tool",
        "key": "API_TOOL",
        "description": "Base tools for the agent",
    },
    {
        "name": "Data tool",
        "key": "DATA_TOOL",
        "description": "Base tools for the agent",
    },
]

AGENT_TOOLS_AUTH = {
    "Basic": [
        {
            "name": "Username",
            "key": "username",
            "description": "The username for Basic Authentication",
            "input_type": "text",
            "required": True,
        },
        {
            "name": "Password",
            "key": "password",
            "description": "The password for Basic Authentication",
            "input_type": "password",
            "required": True,
        },
    ],
    "Bearer": [
        {
            "name": "Token",
            "key": "token",
            "description": "The Bearer token for authentication",
            "input_type": "text",
            "required": True,
        }
    ],
    "OAuth2": [
        {
            "name": "Client ID",
            "key": "client_id",
            "description": "The client ID for OAuth2",
            "input_type": "text",
            "required": True,
        },
        {
            "name": "Client Secret",
            "key": "client_secret",
            "description": "The client secret for OAuth2",
            "input_type": "text",
            "required": True,
        },
        {
            "name": "Token URL",
            "key": "token_url",
            "description": "The token endpoint URL for OAuth2",
            "input_type": "url",
            "required": True,
        },
        {
            "name": "Scope",
            "key": "scope",
            "description": "The scope of access being requested",
            "input_type": "text",
            "required": False,
        },
    ],
    "APIKey": [
        {
            "name": "API Key Name",
            "key": "api_key_name",
            "description": "The name of the API key (e.g., 'X-API-Key')",
            "input_type": "text",
            "required": True,
        },
        {
            "name": "API Key",
            "key": "api_key",
            "description": "The API key value",
            "input_type": "password",
            "required": True,
        },
        {
            "name": "API Key Location",
            "key": "api_key_location",
            "description": "Where to put the API key",
            "input_type": "select",
            "options": ["header", "query", "cookie"],
            "default": "header",
            "required": True,
        },
    ],
    # Add more auth types as needed
}

AGENT_TOOLS_INTEGRATIONS = [
    {
        "key": "outlook",
        "name": "Outlook",
    },
    {
        "key": "aws_s3",
        "name": "AWS S3",
    },
    {
        "key": "file_system",
        "name": "File System",
    },
    {
        "key": "ai_tools",
        "name": "AI Tools",
    },
    {
        "key": "exa",
        "name": "Exa",
    },
    {
        "key": "miscellaneous",
        "name": "Miscellaneous",
    },
    {
        "key": "api_tools",
        "name": "API Tools",
    },
]

# ============================================
# OUTLOOK TOOLS
# ============================================
OUTLOOK_TOOLS = [
    {
        "name": "Draft Email Reply in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_draft_email_reply",
        "description": "Creates a draft reply to an email message in Microsoft Office 365 Outlook. Requires the source mailbox email address, message ID of the email to reply to, and the reply message content. The draft will be saved in the Drafts folder for review before sending.",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "draft_email_reply",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Flag Email in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_flag_email",
        "description": "Flags an email message in Microsoft Office 365 Outlook. Requires the mailbox email address and message ID of the email to flag. This adds a flag marker to help track important emails that need attention or follow-up action.",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "flag_email",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Send Email Reply in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_send_email_reply",
        "description": "Creates and sends a reply to an email message in Microsoft Office 365 Outlook. Requires the source mailbox email address, message ID of the email to reply to, and the reply message content. The reply will be sent to all original recipients (Reply All).",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "send_email_reply",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Forward Email in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_forward_email",
        "description": "Forwards an email message to one or more recipients in Microsoft Office 365 Outlook. Requires the source mailbox email address, message ID of the email to forward, and recipient email address(es) as list of email addresses. Optional: cc_recipients (list of CC email addresses), bcc_recipients (list of BCC email addresses).",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "forward_email",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Move Email in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_move_email",
        "description": "Moves an email message between folders in Microsoft Office 365 Outlook. Requires the mailbox email address, message ID, source folder path (e.g. 'Inbox'), and target folder path.",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "move_email",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Send Bulk Email in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_send_bulk_email",
        "description": "Sends an email message with attachments in Microsoft Office 365 Outlook. Requires the source mailbox email address, recipient email address(es), subject, body content, and optional attachments. Optional: cc_recipients (list of CC email addresses), bcc_recipients (list of BCC email addresses).",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "send_bulk_email",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Send New Email in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_send_new_email",
        "description": "Sends an email message list of emails. Requires the source mailbox email address, recipient email address(es), subject, body content, and optional attachments. Optional: cc_recipients (list of CC email addresses), bcc_recipients (list of BCC email addresses).",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "send_new_email",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Archive Email in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_archive_email",
        "description": "Archives an email message in Microsoft Office 365 Outlook. Requires the mailbox email address and message ID of the email to archive.",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "archive_email",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Delete Email in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_delete_email",
        "description": "Deletes an email message in Microsoft Office 365 Outlook. Requires the mailbox email address and message ID of the email to delete.",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "delete_email",
                "init_args": ["db"],
            },
        },
    },
    {
        "name": "Get User Profile in Outlook",
        "api_type": "MAIL_TOOL",
        "action": "outlook_get_user_profile",
        "description": "Retrieves the user profile information for a specified mailbox within the organization in Microsoft Office 365 Outlook. Requires the mailbox email address to fetch the profile details.",
        "is_default": True,
        "integration_key": "outlook",
        "is_enabled": False,
        "tool_config": {
            "name": "Outlook",
            "handler": {
                "module": "integrations.office_365.outlook",
                "class": "Outlook",
                "method": "tool_get_user_profile",
                "init_args": ["db"],
            },
        },
    },
]

# ============================================
# AWS S3 TOOLS
# ============================================
AWS_S3_TOOLS = [
    {
        "name": "Upload Structured Data to AWS S3",
        "api_type": "DATA_TOOL",
        "action": "aws_s3_upload_structured_data",
        "description": "Uploads structured data as JSON files to an AWS S3 bucket under the specified folder path. The data will be stored in the designated S3 bucket using the provided folder structure.",
        "is_default": True,
        "integration_key": "aws_s3",
        "is_enabled": False,
        "tool_config": {
            "name": "AWS S3",
            "handler": {
                "module": "integrations.aws.aws_s3",
                "class": "AWSS3",
                "method": "tool_upload_structured_data",
                "init_args": ["organization_schema", "data_store"],
            },
        },
    },
    {
        "name": "Upload Text Data to AWS S3",
        "api_type": "DATA_TOOL",
        "action": "aws_s3_upload_text_data",
        "description": "Uploads plain text data as text files to an AWS S3 bucket under the specified folder path. The data will be stored in the designated S3 bucket using the provided folder structure.",
        "is_default": True,
        "integration_key": "aws_s3",
        "is_enabled": False,
        "tool_config": {
            "name": "AWS S3",
            "handler": {
                "module": "integrations.aws.aws_s3",
                "class": "AWSS3",
                "method": "tool_upload_text_data",
                "init_args": ["organization_schema", "data_store"],
            },
        },
    },
    {
        "name": "Upload File to AWS S3",
        "api_type": "DATA_TOOL",
        "action": "aws_s3_upload_file",
        "description": "Uploads a file to an AWS S3 bucket under the specified folder path. The data will be stored in the designated S3 bucket using the provided folder structure.",
        "is_default": True,
        "integration_key": "aws_s3",
        "is_enabled": False,
        "tool_config": {
            "name": "AWS S3",
            "handler": {
                "module": "integrations.aws.aws_s3",
                "class": "AWSS3",
                "method": "tool_upload_file",
                "init_args": ["organization_schema", "data_store"],
            },
        },
    },
    {
        "name": "Download File from AWS S3",
        "api_type": "DATA_TOOL",
        "action": "aws_s3_download_file",
        "description": "Downloads a file from an AWS S3 bucket. Requires the remote path indicating the file location in the bucket and a local path where the file should be saved. The remote path should include any folder structure, e.g. 'folder/subfolder/file.txt'. The local path is optional.",
        "is_default": True,
        "integration_key": "aws_s3",
        "is_enabled": False,
        "tool_config": {
            "name": "AWS S3",
            "handler": {
                "module": "integrations.aws.aws_s3",
                "class": "AWSS3",
                "method": "download_file",
                "init_args": ["organization_schema", "data_store"],
            },
        },
    },
]

# ============================================
# FILE SYSTEM TOOLS
# ============================================
FILE_SYSTEM_TOOLS = [
    {
        "name": "Create Structured File in Filesystem",
        "api_type": "DATA_TOOL",
        "action": "filesystem_create_structured_file",
        "description": "Creates a structured file in JSON or CSV format from structured data (a dictionary or a list of dictionaries) in a local or network filesystem. Requires the data, a file name, and an optional format (json or csv). Defaults to json if no format is provided. The file will be stored at the designated mount path using the specified folder structure.",
        "is_default": True,
        "integration_key": "file_system",
        "is_enabled": False,
        "tool_config": {
            "name": "File System",
            "handler": {
                "module": "integrations.file_system.file_system",
                "class": "FileSystem",
                "method": "tool_create_structured_file",
                "init_args": ["data_store"],
            },
        },
    },
    {
        "name": "Create Text File in Filesystem",
        "api_type": "DATA_TOOL",
        "action": "filesystem_create_text_file",
        "description": "Creates a plain text file from a string in a local or network-mounted filesystem. Requires the text content and a file name. The file will be stored at the designated mount path using the specified folder structure.",
        "is_default": True,
        "integration_key": "file_system",
        "is_enabled": False,
        "tool_config": {
            "name": "File System",
            "handler": {
                "module": "integrations.file_system.file_system",
                "class": "FileSystem",
                "method": "tool_create_text_file",
                "init_args": ["data_store"],
            },
        },
    },
    {
        "name": "Read File from Filesystem",
        "api_type": "DATA_TOOL",
        "action": "filesystem_read_file",
        "description": "Reads a file from a local or network filesystem. Requires the file path in the filesystem and a local path where the file should be saved.",
        "is_default": True,
        "integration_key": "file_system",
        "is_enabled": False,
        "tool_config": {
            "name": "File System",
            "handler": {
                "module": "integrations.file_system.file_system",
                "class": "FileSystem",
                "method": "read_file",
                "init_args": ["data_store"],
            },
        },
    },
    {
        "name": "Copy File in Filesystem",
        "api_type": "DATA_TOOL",
        "action": "filesystem_copy_file",
        "description": "Copies a file from one location to another within the filesystem. Requires source file path and destination file path. Creates destination directories if they don't exist.",
        "is_default": True,
        "integration_key": "file_system",
        "is_enabled": False,
        "tool_config": {
            "name": "File System",
            "handler": {
                "module": "integrations.file_system.file_system",
                "class": "FileSystem",
                "method": "copy_file",
                "init_args": ["data_store"],
            },
        },
    },
    {
        "name": "Delete File from Filesystem",
        "api_type": "DATA_TOOL",
        "action": "filesystem_delete_file",
        "description": "Deletes a file from the filesystem. Requires the file path to delete. Use with caution as this action is irreversible.",
        "is_default": True,
        "integration_key": "file_system",
        "is_enabled": False,
        "tool_config": {
            "name": "File System",
            "handler": {
                "module": "integrations.file_system.file_system",
                "class": "FileSystem",
                "method": "tool_delete_file",
                "init_args": ["data_store"],
            },
        },
    },
    {
        "name": "Search File in Filesystem",
        "api_type": "DATA_TOOL",
        "action": "filesystem_search_file",
        "description": "Searches for files in the filesystem by keyword. Requires a search keyword and optional search path. Returns a list of matching file paths based on filename patterns.",
        "is_default": True,
        "integration_key": "file_system",
        "is_enabled": False,
        "tool_config": {
            "name": "File System",
            "handler": {
                "module": "integrations.file_system.file_system",
                "class": "FileSystem",
                "method": "search_file",
                "init_args": ["data_store"],
            },
        },
    },
    {
        "name": "Move File in Filesystem",
        "api_type": "DATA_TOOL",
        "action": "filesystem_move_file",
        "description": "Moves or renames a file within the filesystem. Requires source file path and destination file path. Creates destination directories if they don't exist.",
        "is_default": True,
        "integration_key": "file_system",
        "is_enabled": False,
        "tool_config": {
            "name": "File System",
            "handler": {
                "module": "integrations.file_system.file_system",
                "class": "FileSystem",
                "method": "move_file",
                "init_args": ["data_store"],
            },
        },
    },
    {
        "name": "List Directory in Filesystem",
        "api_type": "DATA_TOOL",
        "action": "filesystem_list_directory",
        "description": "Lists all files and directories in a specified directory path. Requires directory path parameter. Returns a list of all contents in the specified directory.",
        "is_default": True,
        "integration_key": "file_system",
        "is_enabled": False,
        "tool_config": {
            "name": "File System",
            "handler": {
                "module": "integrations.file_system.file_system",
                "class": "FileSystem",
                "method": "list_directory",
                "init_args": ["data_store"],
            },
        },
    },
]

# ============================================
# EXTRACTION TOOLS
# ============================================
EXTRACTION_TOOLS = [
    {
        "name": "Extract Structured Data",
        "api_type": "DATA_TOOL",
        "action": "extract_structured_data",
        "description": "Extracts structured data from text and/or attachments using given data template. Use attachment_id for file-based content present in the task input. Use input_text to pass inline text content (email subject + body, message text, notes, etc.) when instructed to do so. At least one of input_text or attachment_id is required.",
        "is_default": True,
        "integration_key": "ai_tools",
        "is_enabled": False,
        "tool_config": {
            "name": "AI Tools",
            "handler": {
                "module": "toolkits.data_extractor",
                "class": "DataExtractor",
                "method": "extract_structured_data",
                "init_args": ["organization_schema"],
            },
        },
    },
    {
        "name": "Extract Key Information",
        "api_type": "DATA_TOOL",
        "action": "extract_key_information",
        "description": "Extracts key information from text and/or attachments. Use attachment_id for file-based content in the task. Use input_text for inline text (email subject + body, message text, notes, etc.). At least one of input_text or attachment_id is required.",
        "is_default": True,
        "integration_key": "ai_tools",
        "is_enabled": False,
        "tool_config": {
            "name": "AI Tools",
            "handler": {
                "module": "toolkits.key_information_extractor",
                "class": "KeyInformationExtractor",
                "method": "extract_key_information",
                "init_args": ["organization_schema"],
            },
        },
    },
    {
        "name": "Vision Parse Attachment",
        "api_type": "DATA_TOOL",
        "action": "vision_parse_attachment",
        "description": ("Parses PDFs and images to extract readable text content."),
        "is_default": True,
        "integration_key": "ai_tools",
        "is_enabled": False,
        "tool_config": {
            "name": "AI Tools",
            "handler": {
                "module": "toolkits.attachment_parser",
                "class": "AttachmentParser",
                "method": "vision_parse_attachment",
                "init_args": ["organization_schema"],
            },
        },
    },
]

# ============================================
# CLASSIFICATION TOOLS
# ============================================
CLASSIFICATION_TOOLS = [
    {
        "name": "Classify Content",
        "api_type": "DATA_TOOL",
        "action": "classify_content",
        "description": "Classifies text and/or attachments into the single best matching class for the given class_group key. Use attachment_id for file-based content in the task. Use input_text for inline text (email subject + body, message text, notes, etc.). At least one of input_text or attachment_id is required.",
        "is_default": True,
        "integration_key": "ai_tools",
        "is_enabled": False,
        "tool_config": {
            "name": "AI Tools",
            "handler": {
                "module": "toolkits.content_classifier",
                "class": "ContentClassifier",
                "method": "classify_content",
                "init_args": ["organization_schema"],
            },
        },
    },
]

# ============================================
# SUMMARIZATION TOOLS
# ============================================
SUMMARIZATION_TOOLS = [
    {
        "name": "Summarize Content",
        "api_type": "DATA_TOOL",
        "action": "summarize_content",
        "description": "Summarizes content from text and/or attachments into a concise summary. Use attachment_id for file-based content in the task. Use input_text for inline text (email subject + body, message text, notes, etc.). At least one of input_text or attachment_id is required.",
        "is_default": True,
        "integration_key": "ai_tools",
        "is_enabled": False,
        "tool_config": {
            "name": "AI Tools",
            "handler": {
                "module": "toolkits.content_summarizer",
                "class": "ContentSummarizer",
                "method": "summarize_content",
                "init_args": ["organization_schema"],
            },
        },
    },
]

# ============================================
# KNOWLEDGE SEARCH TOOLS
# ============================================
KNOWLEDGE_SEARCH_TOOLS = [
    {
        "name": "Search Knowledge Collections",
        "api_type": "DATA_TOOL",
        "action": "search_knowledge_collections",
        "description": "Performs hybrid search on knowledge collections by combining dense and sparse vector techniques to retrieve the most relevant results for a given query.",
        "is_default": True,
        "integration_key": "miscellaneous",
        "is_enabled": False,
        "tool_config": {
            "name": "Miscellaneous",
            "handler": {
                "module": "toolkits.knowledge_search",
                "class": "KnowledgeSearch",
                "method": "search_knowledge_collections",
                "init_args": ["organization_schema"],
            },
        },
    },
]

# ============================================
# WEB SEARCH TOOLS
# ============================================
WEB_SEARCH_TOOLS = [
    {
        "name": "Web Search",
        "api_type": "DATA_TOOL",
        "action": "search_web",
        "description": "Searches the web to find relevant URLs and metadata based on a text query.",
        "is_default": True,
        "integration_key": "exa",
        "is_enabled": False,
        "tool_config": {
            "name": "Exa",
            "handler": {
                "module": "toolkits.web_search",
                "class": "WebSearch",
                "method": "search_web",
            },
        },
    },
]

# ============================================
# WEB BROWSER TOOLS
# ============================================
WEB_BROWSER_TOOLS = [
    {
        "name": "Web Browser",
        "api_type": "DATA_TOOL",
        "action": "browse_webpage",
        "description": "Fetches and extracts content from a given URL. The extracted content is stored as a JSON file in the mounted storage path. Requires a valid URL input.",
        "is_default": True,
        "integration_key": "exa",
        "is_enabled": False,
        "tool_config": {
            "name": "Exa",
            "handler": {
                "module": "toolkits.web_browser",
                "class": "WebBrowser",
                "method": "browse_webpage",
            },
        },
    },
]


# ============================================
# TASK OUTPUT TOOLS
# ============================================
TASK_OUTPUT_TOOLS = [
    {
        "name": "Get Task Output",
        "api_type": "DATA_TOOL",
        "action": "get_task_output",
        "description": "Retrieves the latest output of an agent task by its task ID. Returns the structured output produced by the task. Use this to access results from previously executed tasks.",
        "is_default": True,
        "integration_key": "miscellaneous",
        "is_enabled": False,
        "tool_config": {
            "name": "Miscellaneous",
            "handler": {
                "module": "toolkits.task_output_retriever",
                "class": "TaskOutputRetriever",
                "method": "get_task_output",
                "init_args": ["organization_schema"],
            },
        },
    },
]

# ============================================
# COMBINED BASIC AGENT TOOLS
# ============================================
BASIC_AGENT_TOOLS = (
    OUTLOOK_TOOLS
    + AWS_S3_TOOLS
    + FILE_SYSTEM_TOOLS
    + EXTRACTION_TOOLS
    + CLASSIFICATION_TOOLS
    + SUMMARIZATION_TOOLS
    + KNOWLEDGE_SEARCH_TOOLS
    + TASK_OUTPUT_TOOLS
    + WEB_SEARCH_TOOLS
    + WEB_BROWSER_TOOLS
)


"""
Agent Tool Credits
Each agent tool consumes credits based on its complexity.
L1 Agent Tools - 1 credit (Simple tools like email, S3, API calls)
L2 Agent Tools - 2 credits (Tools that use LLM for execution, eg. data extractor)
L3 Agent Tools - 5 credits (Tools requiring multiple LLM calls, handling large LLM inputs, or retriever tools)
"""
