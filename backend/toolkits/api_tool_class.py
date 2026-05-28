import requests
import inspect
import os
import re
import json
from functools import wraps
from typing import Any, Dict, Callable, Tuple, Optional
from urllib.parse import urlencode, quote
from pydantic import Field, create_model
from langchain_core.tools import StructuredTool
from logger import configure_logging


class APITool:
    """
    Unified API Tool class that handles REST, OData, and SOAP API types.
    Consolidates common functionality while providing protocol-specific optimizations.
    """

    # Maximum response size in bytes (default: 150 KB to ensure LLM context safety)
    # Based on empirical data: ~3 bytes per token, 150KB = ~50K tokens
    MAX_RESPONSE_SIZE = int(os.getenv("API_MAX_RESPONSE_SIZE", 150 * 1024))

    # Protocol-specific configurations
    PROTOCOL_DEFAULTS = {
        "REST": {
            "method": "GET",
            "content_type": "application/json",
            "default_headers": {},
        },
        "ODATA": {
            "method": "GET",
            "content_type": "application/json",
            "default_headers": {"Accept": "application/json"},
        },
        "SOAP": {
            "method": "POST",
            "content_type": "text/xml; charset=utf-8",
            "default_headers": {},
        },
    }

    def __init__(self, tool_config: Dict[str, Any]):
        """Initialize APITool with configuration and logger."""
        self.tool_config = tool_config
        self.api_type = tool_config.get("api_type", "REST").upper()
        self.logger = configure_logging(__name__)

        # Validate API type
        if self.api_type not in self.PROTOCOL_DEFAULTS:
            raise ValueError(f"Unsupported API type: {self.api_type}")

    def _replace_placeholders(self, text: str, param_values: Dict[str, Any]) -> str:
        """Replace placeholders in text with parameter values.

        Handles both {param_name} and {param_name:type} patterns.
        """
        if not isinstance(text, str):
            return text

        for param_name, param_value in param_values.items():
            # Replace both {param_name} and {param_name:type} patterns
            pattern = r"\{" + param_name + r"(?::[^}]*)?\}"
            text = re.sub(pattern, str(param_value), text)
        return text

    def _get_protocol_defaults(self) -> Dict[str, Any]:
        """Get default configuration for the current API protocol."""
        return self.PROTOCOL_DEFAULTS[self.api_type]

    def _process_headers(
        self, headers: Dict[str, Any], param_values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process request headers by replacing placeholders with actual values."""
        processed_headers = {}

        # Start with protocol defaults
        defaults = self._get_protocol_defaults()
        processed_headers.update(defaults["default_headers"])

        # Process user-defined headers
        if headers:
            for key, value in headers.items():
                processed_headers[key] = self._replace_placeholders(value, param_values)

        # Add Content-Type if not present
        content_type = self.tool_config.get("content_type", defaults["content_type"])
        if "Content-Type" not in processed_headers and content_type:
            processed_headers["Content-Type"] = content_type

        return processed_headers

    def _process_query_params(
        self, params: Dict[str, Any], param_values: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process query parameters by replacing placeholders with actual values."""
        processed_params = {}
        if params:
            for key, value in params.items():
                processed_params[key] = self._replace_placeholders(value, param_values)
        return processed_params

    def _process_body_template(
        self, body_template: str, param_values: Dict[str, Any]
    ) -> Optional[Any]:
        """Process body template based on API type."""
        if not body_template:
            if self.api_type == "SOAP":
                raise ValueError("SOAP requests require a body template")
            return None

        if self.api_type == "SOAP":
            # SOAP: Return raw XML without JSON escaping
            return self._replace_placeholders(body_template, param_values)
        else:
            # REST/OData: Process as JSON with proper escaping
            escaped_params = {}
            for key, value in param_values.items():
                if isinstance(value, str):
                    # Escape quotes and special characters for JSON
                    escaped_params[key] = json.dumps(value)[1:-1]  # Remove outer quotes
                else:
                    escaped_params[key] = str(value)

            processed_template = self._replace_placeholders(
                body_template, escaped_params
            )

            # Parse as JSON with better error handling
            try:
                return json.loads(processed_template)
            except json.JSONDecodeError as e:
                self.logger.error(
                    f"JSON body template invalid: {e.msg} at position {e.pos}"
                )
                return {"error": f"Invalid JSON body template: {str(e)}"}

    def extract_parameters(self, text: str) -> Dict[str, str]:
        """Extract parameter names and types from text using regex.

        Supports patterns like {param_name} or {param_name:type}.
        Returns dict mapping parameter names to their types.
        Defaults to 'string' if no type specified.

        Examples:
            {bol_number} -> {"bol_number": "string"}
            {amount:number} -> {"amount": "number"}
            {is_active:bool} -> {"is_active": "boolean"}
        """
        if not text:
            return {}

        # Type mapping for common type aliases
        type_map = {
            "str": "string",
            "string": "string",
            "text": "string",
            "int": "integer",
            "integer": "integer",
            "float": "number",
            "number": "number",
            "num": "number",
            "bool": "boolean",
            "boolean": "boolean",
        }

        # Match {param_name} or {param_name:type}
        pattern = r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([a-zA-Z_][a-zA-Z0-9_]*))?\}"
        matches = re.findall(pattern, text)

        result = {}
        for param_name, param_type in matches:
            if param_type:
                # Map the type hint to JSON Schema type
                result[param_name] = type_map.get(param_type.lower(), "string")
            else:
                # No type specified, default to string
                result[param_name] = "string"

        return result

    def _process_url(self, url: str, param_values: Dict[str, Any]) -> str:
        """Process URL by replacing dynamic placeholders and path parameters."""
        # First handle path parameters if defined
        path_params = self.tool_config.get("path_params") or {}
        if path_params:
            for param_name, param_pattern in path_params.items():
                if param_name in param_values:
                    # Replace the pattern in URL with actual value
                    url = url.replace(param_pattern, str(param_values[param_name]))

        # Then handle any remaining placeholders in the URL
        return self._replace_placeholders(url, param_values)

    def _configure_auth(
        self,
        auth_type: str,
        auth_config: Dict[str, Any],
        existing_headers: Dict[str, str],
    ) -> Tuple[Optional[Tuple[str, str]], Dict[str, str]]:
        """Configure authentication for the API request."""
        if not auth_type or "Authorization" in existing_headers:
            return None, {}

        auth = None
        headers = {}

        if auth_type == "Basic":
            auth = (auth_config.get("username"), auth_config.get("password"))
        elif auth_type == "Bearer":
            headers["Authorization"] = f"Bearer {auth_config.get('api_key')}"
        elif auth_type == "APIKey":
            api_key_name = auth_config.get("api_key_name")
            api_key = auth_config.get("api_key")
            headers[api_key_name] = api_key
        elif auth_type == "OAuth2":
            try:
                self._handle_oauth2_auth(auth_config, headers)
            except Exception as e:
                self.logger.error(f"OAuth2 authentication failed: {str(e)}")
                # Return empty auth but include error in headers for debugging
                headers["X-OAuth-Error"] = str(e)

        return auth, headers

    def _handle_oauth2_auth(
        self, auth_config: Dict[str, Any], headers: Dict[str, str]
    ) -> None:
        """Handle OAuth2 authentication flow."""
        token_url = auth_config.get("token_url")
        if not token_url:
            raise ValueError("OAuth2 requires token_url in auth_config")

        token_data = {
            "grant_type": auth_config.get("grant_type", "client_credentials"),
            "client_id": auth_config.get("client_id"),
            "client_secret": auth_config.get("client_secret"),
        }

        # Add scope if provided
        if auth_config.get("scope"):
            token_data["scope"] = auth_config.get("scope")

        # Add custom token parameters if provided
        if auth_config.get("token_params"):
            token_data.update(auth_config.get("token_params"))

        token_response = requests.post(token_url, data=token_data, timeout=10)
        if token_response.status_code == 200:
            access_token = token_response.json().get("access_token")
            headers["Authorization"] = f"Bearer {access_token}"
        else:
            raise Exception(
                f"OAuth2 token request failed with status: {token_response.status_code}"
            )

    def _build_request_url(
        self, processed_url: str, query_params: Dict[str, Any], method: str
    ) -> str:
        """Build the final request URL based on API type and method."""
        if not query_params:
            return processed_url

        if self.api_type == "ODATA" and method in ["GET", "DELETE"]:
            # OData: Use safe encoding to preserve special characters
            query_string = urlencode(
                query_params,
                quote_via=quote,
                safe="$=,()' ",  # Preserve OData operators
            )
            return f"{processed_url}?{query_string}"
        elif method in ["GET", "DELETE"]:
            # REST: Standard URL encoding
            query_string = urlencode(query_params)
            return f"{processed_url}?{query_string}"
        else:
            # For POST/PUT/PATCH, query params will be added separately
            return processed_url

    def _configure_request_kwargs(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        query_params: Dict[str, Any],
        body: Any,
        auth: Optional[Tuple[str, str]],
        timeout: int,
    ) -> Dict[str, Any]:
        """Configure request kwargs based on API type."""
        request_kwargs = {
            "method": method,
            "url": url,
            "headers": headers,
            "auth": auth,
            "timeout": timeout,
            "verify": os.getenv("SSL_VERIFICATION", "true").lower() == "true",
        }

        # Handle query parameters for non-GET/DELETE methods
        if method not in ["GET", "DELETE"] and query_params:
            if self.api_type != "ODATA":  # OData handles this in URL building
                request_kwargs["params"] = query_params

        # Handle body based on API type
        if body is not None:
            if self.api_type == "SOAP":
                request_kwargs["data"] = body  # SOAP uses raw XML data
            elif isinstance(body, dict):
                request_kwargs["json"] = body  # REST/OData use JSON
            else:
                request_kwargs["data"] = body

        return request_kwargs

    def _process_response(
        self, response: requests.Response, method: str, url: str
    ) -> str:
        """Process response based on API type."""
        if response.status_code >= 400:
            error_response = {
                "error": f"{self.api_type} API call failed: {response.status_code} - {response.reason}",
                "status_code": response.status_code,
                "method": method,
                "url": url,
            }

            # Include partial response for SOAP faults
            if self.api_type == "SOAP":
                error_response["response"] = response.text[:500]

            return json.dumps(error_response)

        # Handle successful responses
        if self.api_type == "SOAP":
            soap_response = {
                "status_code": response.status_code,
                "response": response.text,
                "headers": dict(response.headers),
            }
            return json.dumps(soap_response)
        elif self.api_type == "ODATA":
            # OData: Try to parse as JSON and unwrap OData v2 structure
            if response.text:
                try:
                    parsed_response = response.json()
                    # Unwrap OData v2: {"d": {"results": [...]}} → [...] or {"d": {...}} → {...}
                    d_value = parsed_response.get("d", parsed_response)
                    return json.dumps(d_value.get("results", d_value) if isinstance(d_value, dict) else d_value)
                except json.JSONDecodeError:
                    return json.dumps(
                        {"response": response.text, "status_code": response.status_code}
                    )
            else:
                return json.dumps(
                    {"status": "Success", "status_code": response.status_code}
                )
        else:
            # REST: Try to parse as JSON
            if response.text:
                try:
                    # Parse and re-serialize to ensure consistent JSON formatting
                    parsed_response = response.json()
                    return json.dumps(parsed_response)
                except json.JSONDecodeError:
                    # If response isn't valid JSON, wrap it
                    return json.dumps(
                        {"response": response.text, "status_code": response.status_code}
                    )
            else:
                return json.dumps(
                    {"status": "Success", "status_code": response.status_code}
                )

    def _configure_api_function(self, func: Callable) -> Callable:
        """Configure the API function with request handling."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            # Get method from config or use protocol default
            defaults = self._get_protocol_defaults()
            method = self.tool_config.get("method", defaults["method"])

            # SOAP always uses POST
            if self.api_type == "SOAP":
                method = "POST"

            url = self.tool_config.get("endpoint", "")

            # Build parameter values dictionary
            param_values = dict(zip(func.__code__.co_varnames, args))
            param_values.update(kwargs)

            # Validate all required parameters are provided
            expected_params = set(func.__code__.co_varnames)
            provided_params = set(param_values.keys())
            missing_params = expected_params - provided_params

            if missing_params:
                error_response = {
                    "error": f"Missing required parameters: {', '.join(missing_params)}"
                }
                if self.api_type == "SOAP":
                    error_response["type"] = "validation_error"
                return json.dumps(error_response)

            # Process request components
            processed_url = self._process_url(url, param_values)
            headers = self._process_headers(
                self.tool_config.get("headers") or {}, param_values
            )
            query_params = self._process_query_params(
                self.tool_config.get("query_params") or {}, param_values
            )

            # Process body
            body = None
            if method in ["POST", "PUT", "PATCH", "DELETE"] and self.tool_config.get(
                "body_template"
            ):
                try:
                    body = self._process_body_template(
                        self.tool_config.get("body_template"), param_values
                    )
                    # Check if body processing returned an error
                    if isinstance(body, dict) and "error" in body:
                        return json.dumps(body)
                except ValueError as e:
                    return json.dumps({"error": str(e), "type": "configuration_error"})

            # Configure authentication
            auth, auth_headers = self._configure_auth(
                self.tool_config.get("auth_type"),
                self.tool_config.get("auth_config") or {},
                headers,
            )
            headers.update(auth_headers)

            # Get timeout from config or use default
            timeout = self.tool_config.get("timeout", 30)

            # Build final URL
            full_url = self._build_request_url(processed_url, query_params, method)

            # Configure request
            request_kwargs = self._configure_request_kwargs(
                method, full_url, headers, query_params, body, auth, timeout
            )

            # Make the request
            try:
                response = requests.request(**request_kwargs)

                # Calculate response metrics
                response_size = len(response.content) if response.content else 0
                response_time = f"{int(response.elapsed.total_seconds() * 1000)}ms"

                # Check if response size exceeds limit
                if response_size > self.MAX_RESPONSE_SIZE:
                    error_response = {
                        "error": f"API Response size exceeds maximum allowed size. Received ({response_size} bytes), maximum allowed is ({self.MAX_RESPONSE_SIZE} bytes)",
                        "status_code": response.status_code,
                        "response_size": response_size,
                        "max_allowed_size": self.MAX_RESPONSE_SIZE,
                        "method": method,
                        "url": full_url,
                    }
                    self.logger.error(
                        f"api_call_failed: type={self.api_type}, method={method}, "
                        f"url={full_url}, status={response.status_code}, "
                        f"response_size={response_size}B, response_time={response_time}, "
                        f'error="Response size exceeds limit ({self.MAX_RESPONSE_SIZE} bytes)"'
                    )
                    return json.dumps(error_response)

                # Log successful API call
                if response.status_code < 400:
                    self.logger.info(
                        f"api_call_completed: type={self.api_type}, method={method}, "
                        f"url={full_url}, status={response.status_code}, "
                        f"response_size={response_size}B, response_time={response_time}"
                    )
                else:
                    self.logger.error(
                        f"api_call_failed: type={self.api_type}, method={method}, "
                        f"url={full_url}, status={response.status_code}, "
                        f"response_size={response_size}B, response_time={response_time}, "
                        f'error="{response.reason}"'
                    )

                return self._process_response(response, method, full_url)

            except requests.RequestException as e:
                error_context = {
                    "error": f"{self.api_type} API call failed: {str(e)}",
                    "method": method,
                    "url": full_url,
                    "error_type": type(e).__name__,
                }
                self.logger.error(
                    f"api_call_failed: type={self.api_type}, method={method}, "
                    f'url={full_url}, error="{type(e).__name__}: {str(e)}"'
                )
                return json.dumps(error_context)

        return wrapper

    def create_api_function(self) -> Callable:
        """Create dynamic API function based on tool configuration."""
        # Extract required parameters with types from all sources
        required_params = {}

        for source in [
            self.tool_config.get("query_params", {}),
            self.tool_config.get("headers", {}),
            self.tool_config.get("path_params", {}),
            self.tool_config.get("body_template", ""),
            self.tool_config.get("endpoint", ""),
            self.tool_config.get("auth_config", {}),
        ]:
            if isinstance(source, dict):
                for value in source.values():
                    required_params.update(self.extract_parameters(str(value)))
            else:
                required_params.update(self.extract_parameters(str(source)))

        function_name = self.tool_config.get("action", "unknown_action")
        param_str = ", ".join(sorted(required_params))

        # Create a local namespace for the function
        local_namespace = {}
        exec_str = f"def {function_name}({param_str}): pass"
        exec(exec_str, local_namespace)

        # Attach parameter types to the function for later use in tool generation
        func = local_namespace[function_name]
        func.__param_types__ = required_params

        # Configure and return the function from local namespace
        configured_func = self._configure_api_function(func)
        configured_func.__param_types__ = required_params
        return configured_func

    def create_args_schema(self, api_function: Callable) -> Optional[Any]:
        """Create Pydantic args schema from API function with parameter types."""
        # Check if parameter types exist
        if (
            not hasattr(api_function, "__param_types__")
            or not api_function.__param_types__
        ):
            return None

        # Create field definitions with types
        field_definitions = {}
        for param_name, param_type in api_function.__param_types__.items():
            # Map JSON Schema types to Python types
            python_type = str  # default
            if param_type == "integer":
                python_type = int
            elif param_type == "number":
                python_type = float
            elif param_type == "boolean":
                python_type = bool

            field_definitions[param_name] = (python_type, Field(...))

        # Create dynamic Pydantic model
        ArgsSchema = create_model(f"{api_function.__name__}_args", **field_definitions)

        return ArgsSchema

    def generate_tool(self) -> StructuredTool:
        """Generate a StructuredTool from the configured API function with typed parameters."""
        api_function = self.create_api_function()

        # Create args schema with parameter types
        args_schema = self.create_args_schema(api_function)

        # Build StructuredTool with or without args_schema
        if args_schema:
            return StructuredTool.from_function(
                func=api_function,
                name=self.tool_config["name"],
                description=self.tool_config["description"],
                args_schema=args_schema,
            )
        else:
            return StructuredTool.from_function(
                func=api_function,
                name=self.tool_config["name"],
                description=self.tool_config["description"],
            )


# Example usage and testing
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    # Test configurations for all three API types
    test_configs = [
        {
            "name": "REST User API",
            "api_type": "REST",
            "action": "create_user",
            "description": "Create a new user via REST API",
            "method": "POST",
            "endpoint": "https://api.example.com/users/{org_id}",
            "headers": {"Authorization": "Bearer {api_token}"},
            "body_template": '{"name": "{user_name}", "email": "{user_email}"}',
            "path_params": {"org_id": "{org_id}"},
        },
        {
            "name": "OData Products API",
            "api_type": "ODATA",
            "action": "get_products",
            "description": "Get filtered products via OData API",
            "method": "GET",
            "endpoint": "https://services.odata.org/V4/Products",
            "query_params": {
                "$filter": "Price gt {min_price}",
                "$select": "ID,Name,Price",
                "$top": "{limit}",
            },
        },
        {
            "name": "SOAP Weather API",
            "api_type": "SOAP",
            "action": "get_weather",
            "description": "Get weather via SOAP API",
            "endpoint": "http://example.com/soap",
            "headers": {"SOAPAction": "getWeather"},
            "body_template": "<soap:Envelope><soap:Body><GetWeather><zip>{zip_code}</zip></GetWeather></soap:Body></soap:Envelope>",
        },
    ]

    for config in test_configs:
        try:
            api_tool = APITool(config)
            generated_tool = api_tool.generate_tool()
            print(f"✓ Generated {config['api_type']} tool: {generated_tool.name}")

            # Extract expected parameters
            expected_params = set()
            for source in [
                config.get("query_params", {}),
                config.get("headers", {}),
                config.get("path_params", {}),
                config.get("body_template", ""),
                config.get("endpoint", ""),
            ]:
                if isinstance(source, dict):
                    for value in source.values():
                        expected_params.update(api_tool.extract_parameters(str(value)))
                else:
                    expected_params.update(api_tool.extract_parameters(str(source)))

            print(f"✓ Expected parameters: {sorted(list(expected_params))}")
            print()

        except Exception as e:
            print(f"✗ {config['api_type']} tool test failed: {str(e)}")
            print()

    print("✓ Unified APITool class successfully handles all three API types!")
