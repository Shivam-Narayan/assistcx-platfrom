from functools import wraps
from langchain_core.tools import StructuredTool
from typing import Dict, Any, Optional, List, Callable
import importlib
import inspect
import json
import logging

# Import your existing components
# from toolkits import tool_function_map
from db_pool import DatabasePoolManager
from toolkits.api_tool_class import APITool


db_pool = DatabasePoolManager()


class ToolsFactory:
    """
    Hybrid tool factory that handles both API tools (no runtime) and base tools (with runtime).
    Uses the unified APITool class for all API types (REST, OData, SOAP).
    Uses function wrapping instead of partial binding for better LangChain compatibility.
    """

    # Supported API types (now all handled by the unified APITool class)
    SUPPORTED_API_TYPES = {"REST", "ODATA", "SOAP"}

    def __init__(self, tool_runtime: Optional[Dict[str, Any]] = None):
        """
        Initialize ToolsFactory with optional runtime configuration.

        Args:
            tool_runtime: Runtime configuration for base tools (not used for API tools)
        """
        self.logger = logging.getLogger(__name__)
        self.tool_runtime = tool_runtime or {}

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate the tool configuration for required fields.

        Args:
            config: Tool configuration dictionary to validate

        Raises:
            ValueError: If required fields are missing or configuration is invalid
        """
        required_fields = ["name", "action", "description"]
        missing_fields = [field for field in required_fields if not config.get(field)]

        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        # Validate API-specific requirements
        if config.get("api_type") in self.SUPPORTED_API_TYPES:
            if not config.get("endpoint"):
                raise ValueError("Endpoint is required for API tools")

    def _is_api_tool(self, config: Dict[str, Any]) -> bool:
        """Check if the tool configuration is for an API tool"""
        return config.get("api_type") in self.SUPPORTED_API_TYPES

    # def _create_runtime_wrapper(self, original_function, action_name: str):
    #     """
    #     Create a proper function wrapper instead of using functools.partial.
    #     This ensures LangChain can properly inspect the function for schema generation.

    #     Args:
    #         original_function: The original function from tool_function_map
    #         action_name: Name of the action for metadata

    #     Returns:
    #         A proper function wrapper with runtime pre-injected
    #     """
    #     # Get the original function signature
    #     original_sig = inspect.signature(original_function)

    #     # Create new parameters excluding 'tool_runtime'
    #     new_params = [
    #         param
    #         for name, param in original_sig.parameters.items()
    #         if name != "tool_runtime"
    #     ]

    #     # Create the wrapper function
    #     @wraps(original_function)
    #     def runtime_wrapper(*args, **kwargs):
    #         # Inject runtime as first argument
    #         return original_function(self.tool_runtime, *args, **kwargs)

    #     # Set proper function metadata
    #     runtime_wrapper.__name__ = action_name
    #     runtime_wrapper.__doc__ = getattr(
    #         original_function, "__doc__", f"Tool function: {action_name}"
    #     )

    #     # Create new signature without tool_runtime parameter
    #     new_signature = original_sig.replace(parameters=new_params)
    #     runtime_wrapper.__signature__ = new_signature

    #     return runtime_wrapper

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
                        # Check if class constructor accepts 'db' parameter
                        init_sig = inspect.signature(target_class.__init__)
                        init_params = list(init_sig.parameters.keys())[1:]  # Skip 'self'
                        
                        if "db" in init_params:
                            # Default: use db session if constructor expects it
                            with db_pool.get_session(org_schema) as db:
                                instance = target_class(db=db)
                                result = getattr(instance, callable_ref.__name__)(**kwargs)
                        else:
                            # No-arg constructor
                            instance = target_class()
                            result = getattr(instance, callable_ref.__name__)(**kwargs)
                else:
                    # Standalone function: call directly
                    result = callable_ref(**kwargs)

                # Format response (if not already formatted)
                if isinstance(result, str):
                    return result  # Already formatted JSON
                elif result:
                    return json.dumps(
                        {
                            "status_code": 200,
                            "message": f"{action_name} completed successfully",
                            "data": str(result),
                        }
                    )
                else:
                    return json.dumps(
                        {"status_code": 500, "message": f"{action_name} failed"}
                    )

            except Exception as e:
                self.logger.error(f"Tool {action_name} failed: {str(e)}")
                return json.dumps(
                    {"status_code": 500, "message": f"Operation failed: {str(e)}"}
                )

        tool_wrapper.__name__ = action_name
        return tool_wrapper

    def generate_api_tool(self, tool_config: Dict[str, Any]) -> StructuredTool:
        """
        Generate a StructuredTool for API tools using the unified APITool class.
        API tools do NOT use tool_runtime.

        Args:
            tool_config: The tool configuration dictionary

        Returns:
            A configured StructuredTool instance
        """
        try:
            self._validate_config(tool_config)

            # Use the unified APITool class for all API types
            tool_generator = APITool(tool_config)
            api_function = tool_generator.create_api_function()

            # Create args schema with parameter types
            args_schema = tool_generator.create_args_schema(api_function)

            # Build StructuredTool with or without args_schema
            if args_schema:
                api_tool = StructuredTool.from_function(
                    func=api_function,
                    name=tool_config.get("action", ""),
                    description=tool_config.get("description", ""),
                    return_direct=tool_config.get("return_direct", False),
                    args_schema=args_schema,
                )
            else:
                api_tool = StructuredTool.from_function(
                    func=api_function,
                    name=tool_config.get("action", ""),
                    description=tool_config.get("description", ""),
                    return_direct=tool_config.get("return_direct", False),
                )

            return api_tool

        except Exception as e:
            error_msg = f"Error generating {tool_config.get('api_type', 'Unknown')} API tool: {str(e)}"
            self.logger.error(error_msg)
            raise type(e)(error_msg) from e

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

            handler_config = tool_config["tool_config"].get("handler")

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

            # Create a clean signature without tool_runtime for LangChain
            # tool_params already excludes tool_runtime, so annotations will too
            new_sig = sig.replace(parameters=tool_params)
            wrapped_function.__signature__ = new_sig
            
            # Extract annotations from tool_params (already excludes tool_runtime)
            annotations = {param.name: param.annotation for param in tool_params 
                          if param.annotation != inspect.Parameter.empty}
            if sig.return_annotation != inspect.Signature.empty:
                annotations['return'] = sig.return_annotation
            wrapped_function.__annotations__ = annotations

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

    def generate(
        self,
        tool_config: Dict[str, Any],
        review_required: bool = False,
    ) -> StructuredTool:
        """
        Generate either an API tool or a base tool based on the tool configuration.

        Args:
            tool_config: The tool configuration dictionary
            review_required: Whether this tool requires human review before execution

        Returns:
            A configured StructuredTool instance
        """
        if self._is_api_tool(tool_config):
            tool = self.generate_api_tool(tool_config)
        else:
            tool = self.generate_base_tool(tool_config)

        if review_required:
            if tool.metadata is None:
                tool.metadata = {}
            tool.metadata["review_required"] = True

        return tool

    def generate_multiple(
        self, tool_configs: List[Dict[str, Any]]
    ) -> List[StructuredTool]:
        """
        Generate multiple tools from a list of configurations.

        Args:
            tool_configs: List of tool configuration dictionaries

        Returns:
            List of configured StructuredTool instances
        """
        tools = []
        tool_names = []
        api_tool_count = 0
        base_tool_count = 0

        for config in tool_configs:
            try:
                tool = self.generate(config)
                tools.append(tool)
                tool_names.append(config.get("action", "unknown"))

                # Track tool type
                if self._is_api_tool(config):
                    api_tool_count += 1
                else:
                    base_tool_count += 1
            except Exception as e:
                self.logger.error(
                    f"Failed to generate tool {config.get('name', 'unknown')}: {e}"
                )
                raise

        # Log consolidated tools configured with counts
        self.logger.info(
            f"tools_configured: count={len(tools)}, "
            f"api_tools={api_tool_count}, base_tools={base_tool_count}, "
            f"tools={tool_names}"
        )
        return tools

    # @staticmethod
    # def get_available_base_actions() -> List[str]:
    #     """Get list of all available base tool actions"""
    #     return list(tool_function_map.keys())

    @staticmethod
    def get_available_api_types() -> List[str]:
        """Get list of all available API types"""
        return list(ToolsFactory.SUPPORTED_API_TYPES)

    # def get_runtime_info(self) -> Dict[str, Any]:
    #     """Get runtime information for debugging"""
    #     return {
    #         "has_runtime": bool(self.tool_runtime),
    #         "runtime_keys": list(self.tool_runtime.keys()) if self.tool_runtime else [],
    #         "available_base_actions": len(tool_function_map),
    #         "available_api_types": len(self.SUPPORTED_API_TYPES),
    #     }

    @staticmethod
    def get_tool_schemas(tool: StructuredTool) -> Dict[str, Any]:
        """
        Get tool schema information.

        Args:
            tool: StructuredTool instance

        Returns:
            Dict containing tool schema
        """
        return {
            "tool_name": tool.name,
            "description": tool.description,
            "tool_call_schema": tool.tool_call_schema.model_json_schema(),
            "args": tool.args,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)  # Reduce log noise

    # Initialize factory with sample runtime
    sample_runtime = {
        "aws_access_key": "sample_key",
        "runtime_secret": "runtime_secret",
    }
    tools_factory = ToolsFactory(tool_runtime=sample_runtime)

    # Base tool configuration
    base_config = {
        "name": "Upload to S3",
        "action": "upload_data_to_s3",
        "description": "Upload data to S3 bucket",
    }

    # REST API tool configuration
    rest_config = {
        "name": "Get Invoice",
        "action": "get_invoice",
        "description": "Get invoice details via REST API",
        "api_type": "REST",
        "method": "GET",
        "endpoint": "https://api.example.com/invoices/{invoice_id}",
        "headers": {"Authorization": "Bearer {token}"},
        "query_params": {"company": "{company_code}"},
    }

    # OData API tool configuration
    odata_config = {
        "name": "Get Products",
        "action": "get_products",
        "description": "Get filtered products via OData",
        "api_type": "ODATA",
        "endpoint": "https://services.odata.org/V4/Northwind/Products",
        "query_params": {"$filter": "UnitPrice gt {min_price}", "$top": "{limit}"},
    }

    # SOAP API tool configuration
    soap_config = {
        "name": "Get Weather",
        "action": "get_weather",
        "description": "Get weather via SOAP API",
        "api_type": "SOAP",
        "endpoint": "https://soap.example.com/weather",
        "headers": {"SOAPAction": "GetWeather"},
        "body_template": """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetWeather>
      <zipCode>{zip_code}</zipCode>
    </GetWeather>
  </soap:Body>
</soap:Envelope>""",
    }

    print("=== ToolsFactory Test ===")

    configs = [
        ("Base Tool", base_config),
        ("REST Tool", rest_config),
        ("OData Tool", odata_config),
        ("SOAP Tool", soap_config),
    ]

    for tool_type, config in configs:
        try:
            tool = tools_factory.generate(config)
            print(f"✓ {tool_type}: {tool.name}")

            # Show tool schema with actual parameters
            try:
                schema_info = tools_factory.get_tool_schemas(tool)
                properties = schema_info.get("input_schema", {}).get("properties", {})
                if properties:
                    params = list(properties.keys())
                    print(f"  Parameters: {params}")
                else:
                    print(f"  Parameters: No parameters required")
            except Exception:
                print(f"  Parameters: Unable to extract")

        except Exception as e:
            print(f"✗ {tool_type}: {str(e)}")

    # Test batch generation
    try:
        batch_tools = tools_factory.generate_multiple(
            [rest_config, odata_config, soap_config]
        )
        print(f"✓ Batch: Generated {len(batch_tools)} API tools")
    except Exception as e:
        print(f"✗ Batch: {str(e)}")

    print("✓ All tests completed")
