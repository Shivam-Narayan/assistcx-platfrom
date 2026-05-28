# Custom libraries
from logger import configure_logging

# Default libraries
from typing import Dict, Optional
import json
import os

# Installed libraries
from dotenv import load_dotenv
from exa_py import Exa

load_dotenv()

logger = configure_logging(__name__)

MIN_QUERY_LENGTH = 2

MAX_QUERY_LENGTH = 100

# exa-py 2.x search results include `text` by default; Result has no `snippet` attribute.
SEARCH_SNIPPET_MAX_CHARS = 800


class WebSearch:
    """
    Handles web search using Exa API.
    """

    def __init__(self):
        """
        Initializes WebSearch with EXA API key validation.
        """
        api_key = os.getenv("EXA_API_KEY")
        if not api_key:
            logger.error("EXA_API_KEY environment variable not found")
            raise Exception("EXA_API_KEY environment variable is required.")
        self.exa = Exa(api_key)

    def search_web(
        self,
        tool_runtime: Dict,
        query: str,
        result_count: Optional[int] = 10,
    ) -> str:
        """
        Searches the web using Exa API and returns results as JSON string.

        Args:
            tool_runtime (Dict): Tool runtime context containing task_id, etc
            query (str): Search query text
            result_count (Optional[int]): Number of results to return (default: 10)

        Returns:
            str: JSON string of search results
        """
        task_id = tool_runtime.get("task_id", "unknown")

        try:
            # Validate query
            if not query or not isinstance(query, str):
                return json.dumps(
                    {"error": "query is required."},
                    ensure_ascii=False,
                )

            query = query.strip()
            if len(query) < MIN_QUERY_LENGTH:
                return json.dumps(
                    {
                        "error": f"query must be at least {MIN_QUERY_LENGTH} characters long."
                    },
                    ensure_ascii=False,
                )

            if len(query) > MAX_QUERY_LENGTH:
                query = query[:MAX_QUERY_LENGTH]

            logger.info(
                f"[task_id={task_id}] search_web_started: "
                f"tool=search_web, query={query}, result_count={result_count}"
            )

            # exa-py 2.x: `use_autoprompt` was removed — passing it raises ValueError from validate_search_options.
            response = self.exa.search(
                query,
                num_results=result_count,
                type="neural",
            )

            if not getattr(response, "results", None):
                return json.dumps(
                    {"error": "No web search results found."},
                    ensure_ascii=False,
                )

            # Process and format results using list comprehension
            results = [
                {
                    "url": getattr(r, "url", "") or "",
                    "title": getattr(r, "title", "No title") or "No title",
                    "snippet": (getattr(r, "text", None) or "")[
                        :SEARCH_SNIPPET_MAX_CHARS
                    ],
                    "score": getattr(r, "score", None),
                    "published_date": getattr(r, "published_date", None),
                }
                for r in response.results
            ]

            logger.info(
                f"[task_id={task_id}] search_web_completed: "
                f"tool=search_web, status=SUCCESS, records_found={len(results)}"
            )

            result = json.dumps(results, ensure_ascii=False)
            return result

        except Exception as e:
            logger.error(
                f"[task_id={task_id}] search_web_completed: "
                f'tool=search_web, status=FAILED, error="{str(e)}"'
            )
            return json.dumps(
                {"error": f"Error in searching the web: {str(e)}"},
                ensure_ascii=False,
            )


# Example usage
if __name__ == "__main__":
    # Initialize the WebSearch
    web_search = WebSearch()

    # Test 1: Search Web
    print("\n --- Testing search_web ---")
    results = web_search.search_web(query="AI Trends 2026")
    print(results)
