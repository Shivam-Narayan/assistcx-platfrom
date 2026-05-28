bol_data_agent = {
    "name": "BoL Assistant",
    "intent_class": "post_bol",
    "description": "Agent to extract and upload new bill of lading data to the system.",
    "style": "professional",
    "goal": "Post Bill of Lading",
    "instructions": "Your objective is to get the bill of lading data and upload it to S3 bucket.\nUse the rules inside <rules> delimeter and data provided in <environment> delimeter while making decisions regarding tool selection or action input or next steps.",
    "rules": [
        "Use email and environment data to find the right data for action_input in each step.",
        "Use tools_config to find additional parameters for action_input and try pass all parameters you can find.",
        "Use the bill of lading data present in the environment to upload and send full data for upload.",
        "Use bill of lading number value as file name while sending data for S3 upload.",
        "Always return the bill of lading data uploaded to S3 in the final answer.",
    ],
    "tools": [
        {
            "name": "Extract Email Data",
            "action": "extract_data_from_email",
        },
        {
            "name": "Upload Data to S3",
            "action": "upload_data_to_s3",
        },
    ],
    "knowledge_base": {},
    "agent_llm": "OPENAI_GPT_4O",
    "data_templates": ["bill_of_lading"],
    "agent_config": {
        "split_task_by_records": True,
        "split_task_by_attachments": True,
    },
    "data_store": {
        "storage_type": "remote",
        "storage_bucket": "assistcx-data",
        "storage_folder": "data",
        "storage_region": "ap-south-1",
    },
    "mailbox_trigger": "",
}

invoice_data_agent = {
    "name": "Invoice Data Agent",
    "intent_class": "post_invoice",
    "description": "Agent to extract and upload new invoice data to the system.",
    "style": "professional",
    "goal": "Post vendor invoice",
    "instructions": "Your objective is to get the vendor invoice data and upload it to S3 bucket. Use the rules inside <rules> delimiter and data provided in <environment> delimiter while making decisions regarding tool selection or action input or the next steps.",
    "rules": [
        "Use email, environment, and tools_config to find the right data for action_input in each step and and try to pass all parameters you can find.",
        "You must use S3 upload tool to upload the vendor invoice data from the environment, if there are multiple invoice data in the environment, upload all invoices by sending one invoice data at a time.",
        "Include the following fields along with invoice data dictionary from the environment to upload to S3:file_url, sender_email, mailbox_email, email_subject, received_date (in YYYY/MM/DD), received_time (in HH:MM:SS).",
        "Use the file name mentioned in the file_url to upload to S3 and make sure to upload all the invoices before giving the final answer.",
        "upload_data input should be the invoice data as present in the environment, do not add any extra parameters to it.",
        "Include the count of invoice data present in the environment and the count of invoice uploaded to S3 along with S3 url in the final answer. Make sure both the counts are matching.",
    ],
    "tools": [
        {
            "name": "Extract Email Data",
            "action": "extract_data_from_email",
        },
        {
            "name": "Upload Data to S3",
            "action": "upload_data_to_s3",
        },
    ],
    "knowledge_base": {},
    "agent_llm": "OPENAI_GPT_4O",
    "data_templates": ["vendor_invoice"],
    "agent_config": {
        "split_task_by_records": True,
        "split_task_by_attachments": True,
    },
    "data_store": {
        "storage_type": "remote",
        "storage_bucket": "assistcx-data",
        "storage_folder": "data",
        "storage_region": "ap-south-1",
    },
    "mailbox_trigger": "",
}

invoice_query_agent = {
    "name": "Invoice Query Agent",
    "intent_class": "invoice_query",
    "description": "Agent to create response to invoice queries and draft email.",
    "style": "professional",
    "goal": "Reply to invoice queries",
    "instructions": "Your objective is to create a polite and professional reply to the following email insider <email> delimiter. Make sure that the email contains proper structure, greetings and all the required information asked in the original email. Use the rules inside <rules> delimiter and data provided in <environment> delimiter while making decisions regarding tool selection or next steps.",
    "rules": [
        "Use email, environment, and tools_config to find the right data for action_input in each step and and try to pass all available parameters.",
        "If the query is about invoice info or payment status use Get Invoice tool and if the payment is pending then it will be cleared in the next payout cycle.",
        "If the query is related to multiple invoices then make sure to get all invoice details before drafting the reply, and include the details in the reply.",
        "Craft a professional and reader-friendly reply, and include useful details such as invoice number, invoice date, amount, due date; avoid lists or bullet points for a natural and engaging read.",
        "Include the complete input and output data of invoice tool displaying all the data fields in a separate information block right after the email draft body.",
        "After creating the reply draft move the original email from 'inbox' to 'Invoice query' folder",
        "Include all key task details in the final answer which is helpful for the user.",
    ],
    "tools": [
        {
            "name": "Get Invoice Details",
            "action": "get_invoice_details",
        },
        {
            "name": "Draft Email Reply",
            "action": "office365_draft_email_reply",
        },
    ],
    "knowledge_base": {},
    "agent_llm": "OPENAI_GPT_4O",
    "data_templates": [],
    "agent_config": {
        "split_task_by_records": True,
        "split_task_by_attachments": True,     
    },
    "data_store": {
        "storage_type": "remote",
        "storage_bucket": "assistcx-data",
        "storage_folder": "data",
        "storage_region": "ap-south-1",
    },
    "mailbox_trigger": "",
}

ap_query_agent = {
    "name": "Invoice Query Agent",
    "intent_class": "invoice_query",
    "description": "Agent to create response to invoice queries and draft email.",
    "style": "professional",
    "goal": "Reply to invoice queries",
    "instructions": "Your objective is to create a polite and professional reply to the following email insider <email> delimeter.\nMake sure that the email contains proper structure, greetings and all the required information asked in the original email.\nUse the rules inside <rules> delimeter and data provided in <environment> delimeter while making decisions regarding tool selection or next steps.",
    "rules": [
        "Use email and environment data to find the right data for action_input in each step.",
        "Use tools_config to find additional parameters for action_input and try pass all parameters you can find.",
        "If the objective is to reply to email, make sure use draft_reply tool to draft email in mailbox email.",
        "If the query is about invoice info or payment status use Get Invoice tool.",
        "If the payment is pending then it will be cleared in the next payout cycle.",
        "If the query is related to multiple invoices then make sure to get all invoice details.",
        "Craft a professional email reply and don't simply mention the data output from the tool",
        "Always return the email draft content in the final final answer.",
    ],
    "tools": [
        {
            "name": "Get Invoice Details",
            "action": "get_invoice_details",
        },
        {
            "name": "Draft Email Reply",
            "action": "office365_draft_email_reply",
        },
    ],
    "knowledge_base": {},
    "agent_llm": "OPENAI_GPT_4O",
    "data_templates": [],
    "agent_config": {
        "split_task_by_records": True,
        "split_task_by_attachments": True,
    },
    "data_store": {
        "storage_type": "remote",
        "storage_bucket": "assistcx-data",
        "storage_folder": "data",
        "storage_region": "ap-south-1",
    },
    "mailbox_trigger": "",
}
