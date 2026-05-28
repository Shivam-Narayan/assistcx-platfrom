# Unified Base Tool System - Final Plan

## Goal

1. **Unify base tools** (integration + system tools) with a single `handler` config
2. Keep **API tools unchanged** (`generate_api_tool` stays intact)
3. Use signature introspection to auto-detect params and `tool_runtime`
4. Minimal config - module/function or module/class/method

---

## Scope

| Tool Type | Status | Method |
|-----------|--------|--------|
| **API Tools** (REST, OData, SOAP) | **Keep Intact** | `generate_api_tool()` |
| **Base Tools** (system + integration) | **Refactor** | `generate_base_tool()` |

---

## Current vs Proposed Flow (Base Tools Only)

### Current

```
agent_tools_data.py → tool_function_map → generate_base_tool() → _create_runtime_wrapper()
```

### Proposed

```
agent_tools_data.py (with handler config) → generate_base_tool() → _build_tool_wrapper()
```

---

## ToolsFactory - Complete Method Reference

### Methods to Keep Intact (No Changes)

```python
class ToolsFactory:

    SUPPORTED_API_TYPES = {"REST", "ODATA", "SOAP"}

    def __init__(self, tool_runtime: Optional[Dict[str, Any]] = None):
        """Initialize ToolsFactory with optional runtime configuration."""
        # Keep as-is

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate the tool configuration for required fields."""
        # Keep as-is

    def _is_api_tool(self, config: Dict[str, Any]) -> bool:
        """Check if the tool configuration is for an API tool."""
        # Keep as-is

    def generate_api_tool(self, tool_config: Dict[str, Any]) -> StructuredTool:
        """Generate a StructuredTool for API tools using the unified APITool class."""
        # Keep as-is (API tools unchanged)

    def generate(self, tool_config: Dict[str, Any]) -> StructuredTool:
        """Generate either an API tool or a base tool based on the tool configuration."""
        # Keep as-is (routing logic unchanged)

    def generate_multiple(self, tool_configs: List[Dict[str, Any]]) -> List[StructuredTool]:
        """Generate multiple tools from a list of configurations."""
        # Keep as-is

    @staticmethod
    def get_available_api_types() -> List[str]:
        """Get list of all available API types."""
        # Keep as-is

    def get_runtime_info(self) -> Dict[str, Any]:
        """Get runtime information for debugging."""
        # Keep as-is

    @staticmethod
    def get_tool_schemas(tool: StructuredTool) -> Dict[str, Any]:
        """Get tool schema information."""
        # Keep as-is
```

### Methods to Remove

```python
def _create_runtime_wrapper(self, original_function, action_name: str):
    """REMOVE: Replaced by _build_tool_wrapper"""

@staticmethod
def get_available_base_actions() -> List[str]:
    """REMOVE: No longer needed without tool_function_map"""
```

### Methods to Rewrite

```python
def generate_base_tool(self, tool_config: Dict[str, Any]) -> StructuredTool:
    """
    Generate a StructuredTool for base tools (system + integration).
    Uses handler config with signature introspection.

    Args:
        tool_config: Tool configuration with 'handler' key

    Returns:
        A configured StructuredTool instance
    """
    try:
        self._validate_config(tool_config)

        handler_config = tool_config["handler"]

        # Import module
        module = importlib.import_module(handler_config["module"])

        # Determine if it's a function or class method
        if "class" in handler_config:
            # Class method
            target_class = getattr(module, handler_config["class"])
            method_name = handler_config["method"]
            callable_ref = getattr(target_class, method_name)
            init_args = handler_config.get("init_args", [])
            is_class_method = True
        else:
            # Standalone function
            callable_ref = getattr(module, handler_config["function"])
            target_class = None
            init_args = []
            is_class_method = False

        # Introspect signature
        sig = inspect.signature(callable_ref)
        params = list(sig.parameters.values())

        # Skip 'self' for class methods
        if is_class_method:
            params = [p for p in params if p.name != "self"]

        # Check if handler has tool_runtime param (at ANY position)
        has_tool_runtime = any(p.name == "tool_runtime" for p in params)

        # Get tool params (excluding tool_runtime) for new signature
        tool_params = [p for p in params if p.name != "tool_runtime"]

        # Build tool function wrapper
        wrapped_function = self._build_tool_wrapper(
            callable_ref=callable_ref,
            target_class=target_class,
            init_args=init_args,
            has_tool_runtime=has_tool_runtime,
            is_class_method=is_class_method,
            action_name=tool_config["action"],
        )

        # Set modified signature (without tool_runtime) for LangChain schema generation
        wrapped_function.__signature__ = sig.replace(parameters=tool_params)

        return StructuredTool.from_function(
            func=wrapped_function,
            name=tool_config["action"],
            description=tool_config["description"],
            return_direct=tool_config.get("return_direct", False),
        )

    except Exception as e:
        error_msg = f"Error generating base tool: {str(e)}"
        self.logger.error(error_msg)
        raise type(e)(error_msg) from e
```

### New Methods to Add

```python
def _build_tool_wrapper(
    self,
    callable_ref,
    target_class,
    init_args: list,
    has_tool_runtime: bool,
    is_class_method: bool,
    action_name: str,
) -> Callable:
    """
    Build unified wrapper for both functions and class methods.
    Auto-injects tool_runtime if the handler expects it.

    Args:
        callable_ref: The function or unbound method
        target_class: The class (if class method) or None
        init_args: Constructor args to extract from tool_runtime
        has_tool_runtime: Whether to inject tool_runtime
        is_class_method: Whether this is a class method
        action_name: Name of the action

    Returns:
        Wrapped function ready for StructuredTool
    """
    tool_runtime = self.tool_runtime  # Captured in closure

    def tool_wrapper(**kwargs) -> str:
        try:
            org_schema = tool_runtime.get("organization_schema", "public")

            # Inject tool_runtime as keyword arg if handler expects it
            if has_tool_runtime:
                kwargs["tool_runtime"] = tool_runtime

            if is_class_method:
                # Class method: need to instantiate class first
                if init_args:
                    # Custom constructor args from tool_runtime
                    init_kwargs = {
                        key: tool_runtime[key]
                        for key in init_args
                        if key in tool_runtime
                    }
                    instance = target_class(**init_kwargs)
                    result = getattr(instance, callable_ref.__name__)(**kwargs)
                else:
                    # Default: use db session
                    with db_pool.get_session(org_schema) as db:
                        instance = target_class(db=db)
                        result = getattr(instance, callable_ref.__name__)(**kwargs)
            else:
                # Standalone function: call directly
                result = callable_ref(**kwargs)

            # Format response (if not already formatted)
            if isinstance(result, str):
                return result  # Already formatted JSON
            elif result:
                return json.dumps({
                    "status_code": 200,
                    "message": f"{action_name} completed successfully",
                    "data": str(result)
                })
            else:
                return json.dumps({
                    "status_code": 500,
                    "message": f"{action_name} failed"
                })

        except Exception as e:
            self.logger.error(f"Tool {action_name} failed: {str(e)}")
            return json.dumps({
                "status_code": 500,
                "message": f"Operation failed: {str(e)}"
            })

    tool_wrapper.__name__ = action_name
    return tool_wrapper
```

### Imports to Update

```python
# Replace current imports with:
import importlib
import inspect
import json
import logging
from typing import Dict, Any, Optional, List, Callable
from functools import wraps

from langchain.tools import StructuredTool
from db_pool import DatabasePoolManager
from toolkits.api_tool_class import APITool

db_pool = DatabasePoolManager()

# REMOVE: from toolkits import tool_function_map
```

---

## Handler Config Format

### Data tool (class method, `organization_schema` constructor)

Matches `configs/agent_tools_data.py` shape (`tool_config.handler`):

```python
{
    "name": "Extract Data from Email",
    "action": "extract_data_from_email",
    "description": "Extract structured data from email...",
    "tool_config": {
        "name": "Data Extraction",
        "handler": {
            "module": "toolkits.data_extractor",
            "class": "DataExtractor",
            "method": "extract_data_from_email",
            "init_args": ["organization_schema"],
        },
    },
}
```

### Integration Tool (Class Method, DB Constructor)

```python
{
    "name": "Flag Email in Outlook",
    "action": "outlook_flag_email",
    "description": "Flags an email message...",
    "handler": {
        "module": "integrations.office_365.outlook",
        "class": "Outlook",
        "method": "flag_email",
    },
}
```

### Integration Tool (Class Method, Custom Constructor)

```python
{
    "name": "Upload Structured Data to S3",
    "action": "aws_s3_upload_structured_data",
    "description": "Uploads structured data to S3...",
    "handler": {
        "module": "integrations.aws.aws_s3",
        "class": "AWSS3",
        "method": "tool_upload_structured_data",
        "init_args": ["organization_schema", "data_store"],
    },
}
```

---

## How Args Schema Works

LangChain's `StructuredTool.from_function()` auto-generates the args schema from the function's `__signature__`. We set the modified signature (without `tool_runtime`) on the wrapper:

```python
# Set signature without tool_runtime for LangChain
wrapped_function.__signature__ = sig.replace(parameters=tool_params)

# LangChain uses this signature to build args schema
StructuredTool.from_function(func=wrapped_function, ...)
```

**No separate `_build_args_schema_from_signature` needed!**

---

## Signature Introspection

```python
# System function with tool_runtime
def extract_data_from_email(tool_runtime: dict, data_template: str, email_data_id: str, attachment_id: str = None):
    ...

# Introspection:
# 1. has_tool_runtime = True
# 2. tool_params = [data_template, email_data_id, attachment_id]  # tool_runtime excluded
# 3. LangChain sees signature: (data_template: str, email_data_id: str, attachment_id: str = None)

# Class method with tool_runtime at any position
def send_reply(self, from_email: str, tool_runtime: dict, message_id: str) -> bool:
    ...

# Introspection:
# 1. has_tool_runtime = True (at ANY position)
# 2. tool_params = [from_email, message_id]  # self and tool_runtime excluded
```

---

## Files Summary

| File | Action | Description |
|------|--------|-------------|
| `backend/agents/shared_utils/tools_factory.py` | **Rewrite** | Replace `generate_base_tool`, add `_build_tool_wrapper`, remove `_create_runtime_wrapper`, update imports |
| `backend/configs/agent_tools_data.py` | **Modify** | Add `handler` config to all tools |
| `backend/integrations/**/*.py` | **Modify** | Add `tool_*` methods for complex tools |
| `backend/toolkits/` | **Done** | Legacy `__init__.py` / `tool_function_map` removed; submodules imported by path from config |

---

## Migration

### Phase 1: Update ToolsFactory
1. Update imports (add `importlib`, `json`, `db_pool`; remove `tool_function_map`)
2. Rewrite `generate_base_tool` with handler logic
3. Add `_build_tool_wrapper` method
4. Remove `_create_runtime_wrapper` and `get_available_base_actions`

### Phase 2: Add handler config to all tools
- Update `agent_tools_data.py` with `handler` for each tool

### Phase 3: Migrate integration tools to integration classes
1. Add `tool_*` methods to integration classes
2. Remove dead `toolkits/*_tools.py`-style stubs (completed for mail, S3, filesystem, crawl, search, etc.)

### Phase 4: Cleanup
- `tool_function_map` and `toolkits/__init__.py` removed; tools are config-driven only
- Remaining toolkit code lives in named modules (`data_extractor.py`, `web_search.py`, `integrations/...`, etc.)

---

## Benefits

| Before | After |
|--------|-------|
| Manual registration in tool_function_map | Config-driven with handler |
| Integration tools need wrapper in toolkits | Direct reference to integration methods |
| Separate _create_runtime_wrapper logic | Unified _build_tool_wrapper |
| Explicit tool_runtime position (first param) | Auto-detected at ANY position |
| API tools | **Unchanged** |

---

## Tools Config Organization

### Current Problem

All tools in one flat `BASIC_AGENT_TOOLS` list becomes hard to maintain as integrations grow.

### Solution: Centralized with Grouping

Keep everything in `agent_tools_data.py` but organize by integration:

```python
# backend/configs/agent_tools_data.py

# ============================================
# OUTLOOK TOOLS
# ============================================
OUTLOOK_TOOLS = [
    {
        "name": "Flag Email in Outlook",
        "action": "outlook_flag_email",
        "description": "Flags an email message...",
        "is_default": True,
        "integration_key": "outlook",
        "handler": {
            "module": "integrations.office_365.outlook",
            "class": "Outlook",
            "method": "flag_email",
        },
    },
    {
        "name": "Archive Email in Outlook",
        "action": "outlook_archive_email",
        "description": "Archives an email message...",
        "is_default": True,
        "integration_key": "outlook",
        "handler": {
            "module": "integrations.office_365.outlook",
            "class": "Outlook",
            "method": "archive_email",
        },
    },
    # ... more outlook tools
]

# ============================================
# AWS S3 TOOLS
# ============================================
AWS_S3_TOOLS = [
    {
        "name": "Upload Structured Data to S3",
        "action": "aws_s3_upload_structured_data",
        "description": "Uploads structured data to S3...",
        "is_default": True,
        "integration_key": "aws_s3",
        "handler": {
            "module": "integrations.aws.aws_s3",
            "class": "AWSS3",
            "method": "tool_upload_structured_data",
            "init_args": ["organization_schema", "data_store"],
        },
    },
    # ... more s3 tools
]

# ============================================
# EXTRACTION TOOLS (DATA_TOOL + class handler)
# ============================================
EXTRACTION_TOOLS = [
    {
        "name": "Extract Data from Email",
        "action": "extract_data_from_email",
        "description": "Extract structured data from email...",
        "is_default": True,
        "integration_key": "data_extraction",
        "tool_config": {
            "name": "Data Extraction",
            "handler": {
                "module": "toolkits.data_extractor",
                "class": "DataExtractor",
                "method": "extract_data_from_email",
                "init_args": ["organization_schema"],
            },
        },
    },
    # ... more extraction tools
]

# ============================================
# FILE SYSTEM TOOLS
# ============================================
FILE_SYSTEM_TOOLS = [
    # ... filesystem tools
]

# ============================================
# COMBINED FOR DB SEEDING
# ============================================
BASIC_AGENT_TOOLS = (
    OUTLOOK_TOOLS
    + AWS_S3_TOOLS
    + EXTRACTION_TOOLS
    + FILE_SYSTEM_TOOLS
)
```

### Benefits of This Approach

| Aspect | Benefit |
|--------|---------|
| **Maintainability** | Find all tools for an integration in one section |
| **DB Seeding** | Still one `BASIC_AGENT_TOOLS` variable for batch save |
| **No Import Complexity** | Everything in one file, no circular imports |
| **Extensibility** | Add new integration section, append to combined list |
| **Code Review** | Easy to review changes per integration |

### Helper Functions (Optional)

```python
def get_tools_by_integration(integration_key: str) -> list:
    """Get all tools for a specific integration."""
    return [t for t in BASIC_AGENT_TOOLS if t.get("integration_key") == integration_key]

def get_all_integration_keys() -> list:
    """Get list of all unique integration keys."""
    return list(set(t.get("integration_key") for t in BASIC_AGENT_TOOLS if t.get("integration_key")))
```
