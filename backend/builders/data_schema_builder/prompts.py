DATA_SCHEMA_BUILDER_PROMPT = """
You are an expert data architect with deep expertise in document processing, data extraction, and schema design. Your task is to generate a comprehensive data schema for a data template based on the template's name and description.

## Data Schema Name
{{ name }}

## Data Schema Description
{{ description }}

{% if previous_schema != "None" %}
## Previous Data Schema
{{ previous_schema }}
{% endif %}

{% if user_instructions != "None" %}
## Additional User Instructions
{{ user_instructions }}
{% endif %}

## Your Task
{% if previous_schema != "None" %}
**IMPORTANT: This is an iterative refinement request.**

You have been provided with a previous data schema and additional user instructions. Your task is to:
1. Use the previous schema as your foundation and starting point
2. Carefully analyze the user's additional instructions to understand what needs to change
3. Preserve fields that work well and don't require changes
4. Only add, remove, or modify the specific fields that the user's instructions indicate
5. Maintain consistency in naming conventions and description quality across all fields
6. Ensure the refined schema still aligns with the data template's purpose

The user is asking you to refine and improve the existing schema based on their feedback, not create a completely new schema from scratch.

{% else %}
Using the data template name and description, create a complete data schema from scratch that captures all relevant fields for this type of document or data source.
{% endif %}

Generate a list of data schema fields. Each field must include the following properties:

1. **name** (string, required): A unique, descriptive, snake_case identifier for the field.
   - Use lowercase letters, numbers, and underscores only
   - Must be concise yet self-explanatory (e.g., `invoice_number`, `ship_to_city`, `line_items`)

2. **data_type** (string, required): The expected data type. Must be one of:
   - `string` — Free text, identifiers, names, addresses, dates
   - `integer` — Whole numeric values such as quantities, counts, IDs
   - `decimal` — Fractional numeric values such as amounts, prices, weights
   - `list` — Simple repeating values (e.g., list of tags, list of names)
   - `object` — A single nested structure with named sub-fields. When using `object`, you MUST also populate `field_schema`
   - `list[object]` — Repeating/tabular data where each item is a structured object (e.g., line items, list of charges). When using `list[object]`, you MUST also populate `field_schema`

3. **description** (string, required): A detailed, actionable description that guides an AI extraction system. The description should:
   - Explain what the field represents and where it is typically found in the document
   - Include format specifications where applicable (e.g., "Return output strictly in MM/DD/YYYY format")
   - Note common alternate labels or variations (e.g., "The field name can also appear as: 'B/L NUMBER' or 'B/L NO.'")
   - Include OCR correction hints when relevant (e.g., "It will always be a numerical value so make sure to correct any OCR error")
   - Provide disambiguation guidance when fields might be confused (e.g., "If you see two order numbers, the first one is customer order number")
   - Be specific enough that an extraction model can reliably identify and extract the correct value

4. **keywords** (list of strings, optional): Alternate labels, synonyms, or abbreviations commonly used for this field in documents. Useful for improving extraction accuracy.

5. **field_schema** (list of objects, required when data_type is `object` or `list[object]`): Defines the sub-fields of the structure. Each object in field_schema must have:
   - `name` (string): snake_case field name for the sub-field
   - `data_type` (string): The expected data type for the sub-field. Must be one of: `string`, `integer`, `float`, `boolean`
   - `description` (string): Description of the sub-field following the same guidelines above

   Example for a `list[object]` field:
   ```json
   {
     "name": "line_items",
     "data_type": "list[object]",
     "description": "List of items mentioned in the invoice",
     "keywords": ["items", "charges", "details"],
     "field_schema": [
       {"name": "item_description", "data_type": "string", "description": "Complete description of line item as mentioned in the document"},
       {"name": "quantity", "data_type": "integer", "description": "Quantity mentioned for the line item"},
       {"name": "unit_price", "data_type": "float", "description": "Unit price of the line item"},
       {"name": "amount", "data_type": "float", "description": "Total amount for the line item"}
     ]
   }
   ```

   Example for an `object` field:
   ```json
   {
     "name": "vendor_address",
     "data_type": "object",
     "description": "Complete address of the vendor found in the document",
     "keywords": ["supplier address", "remit to"],
     "field_schema": [
       {"name": "street", "data_type": "string", "description": "Street address of the vendor"},
       {"name": "city", "data_type": "string", "description": "City name in the vendor address"},
       {"name": "state", "data_type": "string", "description": "State or province in the vendor address"},
       {"name": "postal_code", "data_type": "string", "description": "Postal or ZIP code in the vendor address"}
     ]
   }
   ```

## Schema Design Guidelines

- **Completeness**: Include all fields that are commonly found in the described document type. Think about header fields, detail fields, totals, metadata, and any attachments.
- **Specificity**: Descriptions must be precise enough for an AI to extract the correct value without human intervention. Avoid vague descriptions like "relevant data" or "important information."
- **Consistency**: Use consistent naming conventions (snake_case), consistent description tone, and consistent format specifications across all fields.
- **Ordering**: Order fields logically — start with document identifiers (document_type, document_number), then header/party information, then detail/line-level data, then totals/summaries, and finally metadata fields (attachment_file, email_file).
- **Nested structures**: Use `data_type: list[object]` with `field_schema` for repeating/tabular data, and `data_type: object` with `field_schema` for single nested structures. Do not flatten structured data into separate top-level fields.
- **Format hints**: Always specify the expected output format for dates, currencies, and other formatted values.
- **Edge cases**: Where applicable, include guidance on handling ambiguous, missing, or poorly scanned data in the description.

Generate a structured, professional, and actionable data schema that can reliably guide AI-powered data extraction for the described template.
"""
