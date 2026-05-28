DOCUMENT_CONTEXT_PROMPT = """You are a document analysis expert. Extract comprehensive document context from the provided content for optimal retrieval matching. This context will enable users to find this document through diverse search queries.

**EXTRACTION STRATEGY:**
Scan for: document purpose, key topics, important entities, dates, numbers, processes, relationships, and domain-specific terms. Prioritize concrete details over general descriptions.

**OUTPUT REQUIREMENTS:**
Return valid JSON following DocumentContext schema. Extract factual information directly from content - capture specific details that make this document unique and searchable.

**EXAMPLE:**
{
    "title": "Employee Benefits Policy Manual 2024",
    "type": "policy",
    "overview": "Comprehensive employee benefits policy for XYZ Corporation covering healthcare, retirement, and leave policies. Outlines eligibility requirements and enrollment procedures for full-time employees. Details medical, dental, vision insurance coverage. Effective January 1, 2024 benefit year with mandatory employee acknowledgment. Contains premium costs, deductible amounts, and enrollment deadlines.",
    "keywords": ["employee benefits", "healthcare policy", "XYZ Corporation", "enrollment procedures", "medical insurance", "retirement plan", "premium costs", "deductibles", "eligibility requirements"],
    "entities": ["XYZ Corporation", "January 1, 2024", "HR Department", "Employee Benefits Policy Manual"],
    "filename": "Employee Benefits Policy Manual 2024.pdf"
}

**DOCUMENT:**
**Filename:** {{ filename }}
**Content Snippet:**
{{ content }}
"""

# Smart field extraction prompt
SMART_FIELD_PROMPT = """
You are an expert at extracting the value of a specific field from given document content.

Field to extract: {{ field_name }}
Field description: {{ field_description }}
Field keywords: {{ field_keywords }}
Field type: {{ field_type }}

Document content:
{{ content }}

Extract the requested field value from the document content above. Follow these guidelines:

1. **Focus**: Look specifically for information related to field name, keywords and description
2. **Accuracy**: Extract only information that is explicitly stated or clearly implied in the document
3. **Format**: Return the direct value of the field without any additional content or explanation
4. **Brevity**: Provide concise, relevant information without unnecessary elaboration

If the requested information is not found in the document, respond with null as the field value. Return dates in YYYY-MM-DD format (e.g., '2025-12-31').

Respond the output in JSON format with the keys "field_name", "field_value".

Example:
{
    "field_name": "field_name",
    "field_value": "field_value"
}
"""

# Knowledge topic extraction prompt
KNOWLEDGE_TOPIC_PROMPT = """
You are an expert at extracting the specific knowledge on the given topic from the given document content.

Topic name: {{ topic_name }}
Topic description: {{ topic_description }}
Topic keywords: {{ topic_keywords }}

Document content:
{{ content }}

Extract comprehensive knowledge about the topic from the document content. Follow these guidelines:

1. **Comprehensive**: Include all relevant information about the topic found in the document
2. **Structured**: Organize the information clearly and logically in a structured format.
3. **Accurate**: Base your response strictly on the document content provided
4. **Concise**: Extract concise and factual information while remaining focused on the topic

Keep the extracted knowledge around 300 words in length. If no relevant information about the topic is found, respond with null.

Extracted knowledge:
"""
