import json
import re
from typing import List, Dict, Any, Union, Optional, Set, Type
from pydantic import BaseModel, ConfigDict, Field, create_model


class DocumentMetadata(BaseModel):
    """Model for document-level metadata for extraction purposes."""

    document_id: Optional[str] = Field(
        default=None,
        description="Unique document identifier (invoice number, form ID, reference number)",
    )
    document_index: Optional[int] = Field(
        default=None,
        description="Position of this document in the input (1 for first document)",
    )
    start_page_idx: Optional[int] = Field(
        default=None,
        description="Page number where document starts (e.g., 1 for first page)",
    )
    end_page_idx: Optional[int] = Field(
        default=None,
        description="Page number where document ends (e.g., 3 for third page)",
    )
    boundary_text: Optional[str] = Field(
        default=None,
        description="5-10 words from document header/title that mark the beginning",
    )
    document_summary: Optional[str] = Field(
        default=None,
        description="3-5 sentence summary of the document and its key information",
    )


class FieldMetadata(BaseModel):
    """Model for field-level metadata."""

    original_text: Optional[str] = Field(
        default=None,
        description="The exact text from the document that was used to extract this field value. Only include relevant snippets, not large sections of text.",
    )
    confidence_score: Optional[int] = Field(
        default=None,
        description="Confidence score (0-100) indicating the reliability of the extraction",
    )


# Shared config for all generated models: lenient on extra keys, accept aliases.
_MODEL_CONFIG = ConfigDict(extra="ignore", populate_by_name=True)


class DataModelGenerator:
    """
    Generate Pydantic models from schema definitions.

    Supports nested objects via `field_schema`, parallel metadata structures
    (document-level and field-level), and an optional extraction summary on
    the top-level wrapper.
    """

    # Mapping from user-facing type strings to Python annotations.
    TYPE_MAPPING = {
        # Basic types
        "string": str,
        "str": str,
        "text": str,
        "integer": int,
        "int": int,
        "decimal": float,
        "float": float,
        "number": Union[int, float],
        "boolean": bool,
        "bool": bool,
        # Collection types
        "list": List[str],
        "list[string]": List[str],
        "list[str]": List[str],
        "list[text]": List[str],
        "list[integer]": List[int],
        "list[int]": List[int],
        "list[float]": List[float],
        "list[number]": List[Union[int, float]],
        "list[boolean]": List[bool],
        "list[bool]": List[bool],
        # Complex types (used when no field_schema is provided)
        "object": Dict[str, Any],
        "dict": Dict[str, Any],
        "list[object]": List[Dict[str, Any]],
        "list[dict]": List[Dict[str, Any]],
    }

    def sanitize_name(self, name: str, default: str = "field") -> str:
        """Convert a string to a valid Python identifier."""
        if not name:
            return default

        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sanitized = re.sub(r"^\d+", "", sanitized)
        sanitized = re.sub(r"_+", "_", sanitized)
        sanitized = sanitized.strip("_")

        return sanitized or default

    def create_pydantic_model(
        self,
        data_schema: List[Dict[str, Any]],
        model_name: str = "data_model",
        wrap_as_list: bool = True,
        document_metadata: bool = False,
        field_metadata: bool = False,
        extraction_summary: bool = False,
    ) -> Type[BaseModel]:
        """
        Create a Pydantic model from field definitions.

        Args:
            data_schema: List of field definition dictionaries
            model_name: Name for the generated record model
            wrap_as_list: When True (default), wrap the record in a
                `data_records: List[record]` container — used by LLM
                extraction flows that may return multiple records per input.
                When False, return the bare record model — used for agent
                response schemas and other single-object structured-output
                cases.
            document_metadata: Include `meta__document` field on the record
            field_metadata: Include `meta__fields` dict on the record
            extraction_summary: Include `extraction_summary` on the wrapper.
                Ignored when `wrap_as_list=False`.

        Returns:
            Pydantic model class
        """
        sanitized_name = self.sanitize_name(model_name, "data_model")
        record_model = self._build_record_model(
            data_schema=data_schema,
            model_name=sanitized_name,
            currently_building=set(),
            include_metadata=True,
            document_metadata=document_metadata,
            field_metadata=field_metadata,
        )

        if not wrap_as_list:
            return record_model

        return self._build_wrapper_model(
            record_model=record_model,
            wrapper_name=f"{sanitized_name}_list",
            extraction_summary=extraction_summary,
        )

    def _build_record_model(
        self,
        data_schema: List[Dict[str, Any]],
        model_name: str,
        currently_building: Set[str],
        include_metadata: bool,
        document_metadata: bool,
        field_metadata: bool,
    ) -> Type[BaseModel]:
        """
        Build a single record model.

        Recursive calls (for nested object / list[object] fields) always pass
        `include_metadata=False`, so `meta__document` and `meta__fields` only
        appear on the outermost record, never on nested sub-objects.

        `currently_building` is the active recursion stack, used to detect
        self-referential schemas before they cause infinite recursion.
        """
        sanitized_name = self.sanitize_name(model_name, "data_model")

        # Detect self-referential schemas: if we're already building a model
        # with this exact name + schema higher up the call stack, recursing
        # into it again would never terminate.
        build_key = f"{sanitized_name}_{hash(str(data_schema))}"
        if build_key in currently_building:
            raise ValueError(
                f"Self-referential schema detected while building model "
                f"'{sanitized_name}': this nested schema is already being "
                f"built higher in the recursion stack, which would cause "
                f"infinite recursion. Check your data_schema for a field "
                f"whose field_schema transitively contains itself."
            )
        currently_building.add(build_key)

        try:
            fields: Dict[str, Any] = {}

            for field_def in data_schema:
                if "name" not in field_def:
                    continue

                original_name = field_def["name"]
                field_name = self.sanitize_name(original_name, "field")
                field_type = (
                    field_def.get("data_type", field_def.get("type", "string"))
                ).lower()

                # Resolve annotation: nested schema beats type-mapping fallback.
                nested_schema = field_def.get("field_schema")
                if nested_schema and field_type in ("object", "dict"):
                    annotation = self._build_record_model(
                        data_schema=nested_schema,
                        model_name=f"{field_name}_model",
                        currently_building=currently_building,
                        include_metadata=False,
                        document_metadata=False,
                        field_metadata=field_metadata,
                    )
                elif nested_schema and field_type == "list[object]":
                    item_model = self._build_record_model(
                        data_schema=nested_schema,
                        model_name=f"{field_name}_item",
                        currently_building=currently_building,
                        include_metadata=False,
                        document_metadata=False,
                        field_metadata=field_metadata,
                    )
                    annotation = List[item_model]
                else:
                    annotation = self.TYPE_MAPPING.get(field_type, str)

                description = field_def.get("description", "")
                if field_def.get("keywords"):
                    description += f" Keywords: {', '.join(field_def['keywords'])}"

                fields[field_name] = (
                    annotation,
                    Field(description=description, alias=original_name),
                )

            # Only the top-level record carries metadata; nested sub-objects
            # never do (recursive calls force include_metadata=False).
            if include_metadata:
                if document_metadata:
                    fields["meta__document"] = (
                        Optional[DocumentMetadata],
                        Field(
                            default=None,
                            description="Document-level metadata (ID, boundaries, etc.)",
                        ),
                    )
                if field_metadata:
                    fields["meta__fields"] = (
                        Optional[Dict[str, FieldMetadata]],
                        Field(
                            default_factory=dict,
                            description="Field-level metadata including original text and confidence scores",
                        ),
                    )

            return create_model(
                sanitized_name,
                __config__=_MODEL_CONFIG,
                **fields,
            )
        finally:
            currently_building.discard(build_key)

    def _build_wrapper_model(
        self,
        record_model: Type[BaseModel],
        wrapper_name: str,
        extraction_summary: bool,
    ) -> Type[BaseModel]:
        """Wrap a record model in a `data_records` list container."""
        fields: Dict[str, Any] = {
            "data_records": (
                List[record_model],
                Field(description=f"List of {record_model.__name__} records"),
            ),
        }

        if extraction_summary:
            fields["extraction_summary"] = (
                Optional[str],
                Field(
                    default=None,
                    description="Summary of extraction process, including any errors or contextual information",
                ),
            )

        wrapper_config = ConfigDict(
            extra="ignore",
            populate_by_name=True,
            json_schema_extra={"title": wrapper_name, "type": "object"},
        )

        return create_model(
            wrapper_name,
            __config__=wrapper_config,
            **fields,
        )

    @staticmethod
    def describe_model(model: Type[BaseModel]) -> str:
        """
        Return a human-readable JSON schema view of a generated model.

        Useful for debugging the exact shape that will be sent to an LLM via
        `with_structured_output(...)`.
        """
        return json.dumps(model.model_json_schema(), indent=2)


# Example usage to demonstrate the model generator
if __name__ == "__main__":
    invoice_schema = [
        {
            "name": "invoice_number",
            "description": "Invoice number mentioned in the document",
            "type": "string",
            "keywords": ["invoice #", "inv no", "number", "reference"],
        },
        {
            "name": "invoice_date",
            "description": "Date of the invoice in YYYY-MM-DD format",
            "type": "string",
            "keywords": ["date", "issued on", "invoice date"],
        },
        {
            "name": "total_amount",
            "description": "Total amount of the invoice",
            "type": "float",
            "keywords": ["total", "amount due", "grand total", "balance"],
        },
        {
            "name": "billing_address",
            "description": "Billing address details",
            "type": "object",
            "field_schema": [
                {"name": "street", "description": "Street address", "type": "string"},
                {"name": "city", "description": "City name", "type": "string"},
                {"name": "state", "description": "State or province", "type": "string"},
                {
                    "name": "zip_code",
                    "description": "Postal or ZIP code",
                    "type": "string",
                },
            ],
        },
        {
            "name": "line_items",
            "description": "List of items in the invoice",
            "type": "list[object]",
            "field_schema": [
                {
                    "name": "item_description",
                    "description": "Description of the item",
                    "type": "string",
                },
                {
                    "name": "quantity",
                    "description": "Quantity of the item",
                    "type": "float",
                },
                {
                    "name": "unit_price",
                    "description": "Price per unit",
                    "type": "float",
                },
            ],
        },
    ]

    generator = DataModelGenerator()
    invoice_model = generator.create_pydantic_model(
        invoice_schema, "Invoice", document_metadata=True, field_metadata=True
    )

    print("=== Generated Model JSON Schema ===")
    print(generator.describe_model(invoice_model))

    # Sample data with metadata using the simplified flat structure
    invoice_data = {
        "data_records": [
            {
                "invoice_number": "INV-001",
                "invoice_date": "2023-05-15",
                "total_amount": 1250.50,
                "billing_address": {
                    "street": "123 Main St",
                    "city": "Anytown",
                    "state": "CA",
                    "zip_code": "12345",
                },
                "line_items": [
                    {
                        "item_description": "Laptop",
                        "quantity": 1,
                        "unit_price": 1000.00,
                    },
                    {"item_description": "Mouse", "quantity": 1, "unit_price": 25.50},
                ],
                "meta__document": {
                    "document_id": "invoice1",
                    "document_index": 1,
                    "start_page_idx": 0,
                    "end_page_idx": 1,
                    "boundary_text": "INVOICE #INV-001",
                    "document_summary": "Invoice from TechSupplier Inc. for computer equipment",
                },
                "meta__fields": {
                    "invoice_number": {
                        "original_text": "Invoice No: INV-001",
                        "confidence_score": 95,
                    },
                    "billing_address.city": {
                        "original_text": "City: Anytown",
                        "confidence_score": 95,
                    },
                    "line_items[0].item_description": {
                        "original_text": "Item: Laptop Computer",
                        "confidence_score": 98,
                    },
                },
            }
        ]
    }

    validated = invoice_model.model_validate(invoice_data)
    invoice = validated.data_records[0]

    print("\n=== Validation round-trip ===")
    assert invoice.invoice_number == "INV-001"
    assert invoice.billing_address.city == "Anytown"
    assert invoice.line_items[0].unit_price == 1000.00
    assert invoice.meta__document.document_id == "invoice1"
    assert invoice.meta__fields["billing_address.city"].confidence_score == 95
    print("All assertions passed.")
    print(f"Invoice: {invoice.invoice_number}, Date: {invoice.invoice_date}")
    print(f"Total: ${invoice.total_amount}")
    print(f"Billing city: {invoice.billing_address.city}")
    print(f"First item: {invoice.line_items[0].item_description}")
