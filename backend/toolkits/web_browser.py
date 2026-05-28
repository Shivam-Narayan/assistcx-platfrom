# Custom libraries
from logger import configure_logging
from utils.content_cleaning import clean_web_content

# Default libraries
from typing import Dict, Tuple, Optional
from urllib.parse import urlparse
import json
import os
import time

# Installed libraries
from exa_py import Exa
from dotenv import load_dotenv


load_dotenv()

logger = configure_logging(__name__)

MOUNT_PATH = "/mnt/data-bucket/crawled_data"

FILENAME_MAX_LENGTH = 100

MAX_CONTENT_LENGTH = 10000

MIN_CONTENT_LENGTH = 50

MAX_TEXT_CHARACTERS = 8000


class WebBrowser:
    """
    Fetches page content via Exa for a single URL; cleans, truncates, and persists JSON.
    """

    def __init__(self):
        """
        Initializes WebBrowser with EXA API key validation.
        """
        api_key = os.getenv("EXA_API_KEY")
        if not api_key:
            logger.error("EXA_API_KEY environment variable not found")
            raise Exception("EXA_API_KEY environment variable is required.")
        self.exa = Exa(api_key)

    def _validate_url(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Validates and normalizes URL with proper format checking.

        Args:
            url (str): URL to validate

        Returns:
            Tuple[Optional[str], Optional[str]]: (Validated and normalized URL, None) if valid, (None, error message) if invalid
        """
        if not url or not isinstance(url, str):
            return None, "URL must be a non-empty string."

        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Validate URL format
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                return None, "Invalid URL format - missing domain."
            if parsed.scheme not in ("http", "https"):
                return None, "URL must use HTTP or HTTPS protocol."
        except Exception:
            return None, "Invalid URL format."

        return url, None

    def _sanitize_filename(self, url: str) -> Optional[str]:
        """
        Converts URL to safe filename with timestamp for uniqueness.

        Args:
            url (str): URL to sanitize

        Returns:
            Optional[str]: Safe filename or None if validation fails
        """
        # Remove protocol from URL
        safe_url = url.replace("https://", "").replace("http://", "")

        # Replace unsafe characters in URL with underscores
        safe_url = safe_url.translate(str.maketrans('/?=&%#:*<>|"\\.', "_" * 14))

        # Clean up and limit length
        safe_url = safe_url.strip("_")

        # Check if filename would be empty after sanitization
        if not safe_url:
            safe_url = "browser_page"

        if len(safe_url) > FILENAME_MAX_LENGTH:
            safe_url = safe_url[:FILENAME_MAX_LENGTH]

        # Add timestamp for uniqueness
        timestamp = int(time.time())
        filename = f"{safe_url}_{timestamp}.json"

        # Validate final path stays in mount directory (security check)
        try:
            # Ensure MOUNT_PATH exists before checking realpath
            os.makedirs(MOUNT_PATH, exist_ok=True)
            final_path = os.path.realpath(os.path.join(MOUNT_PATH, filename))
            mount_path_real = os.path.realpath(MOUNT_PATH)
            if not final_path.startswith(mount_path_real):
                return None
        except (OSError, ValueError) as e:
            logger.error(f"Path validation failed: {str(e)}")
            return None

        return filename

    def _save_to_file(self, content: Dict, url: str) -> Optional[str]:
        """
        Saves content to JSON file.

        Args:
            content (Dict): Content to save
            url (str): URL to save content for

        Returns:
            Optional[str]: File path of saved content or None if failed
        """
        try:
            filename = self._sanitize_filename(url)
            if not filename:
                logger.error(f"Failed to sanitize filename for URL: {url}")
                return None

            file_path = os.path.join(MOUNT_PATH, filename)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=4, ensure_ascii=False)

            logger.info(f"Content saved to {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save content: {str(e)}")
            return None

    @staticmethod
    def _failure_response(url: str, error: str, **extra):
        data = {
            "success": False,
            "url": url,
            "error": error,
            "content": "",
            "title": "",
            "cleaned": False,
            "truncated": False,
            "original_length": 0,
            "final_length": 0,
            "file_path": None,
        }
        data.update(extra)
        return json.dumps(data, ensure_ascii=False)

    def browse_webpage(self, tool_runtime: Dict, url: str) -> str:
        """
        Fetch a webpage via Exa API and return structured content as JSON string.

        Args:
            tool_runtime (Dict): Tool runtime context containing task_id, etc
            url (str): URL to open

        Returns:
            str: JSON string of results with success status and content
        """
        task_id = tool_runtime.get("task_id", "unknown")

        # Validate URL
        validated_url, error = self._validate_url(url)
        if error:
            logger.error(f"[task_id={task_id}] Invalid URL: {error}")
            return json.dumps({"error": error}, ensure_ascii=False)

        try:
            logger.info(
                f"[task_id={task_id}] web_browser_started: "
                f"tool=browse_webpage, url={validated_url}"
            )

            # Make direct API call
            response = self.exa.get_contents(
                [validated_url],
                text={"max_characters": MAX_TEXT_CHARACTERS},
            )

            # Check if we got results
            if not hasattr(response, "results") or not response.results:
                return self._failure_response(
                    validated_url, "No content found for URL"
                )

            # Extract content from first result
            result = response.results[0]
            raw_content = getattr(result, "text", "") or ""
            title = getattr(result, "title", "") or ""

            # Check for minimal content
            if len(raw_content.strip()) < MIN_CONTENT_LENGTH:
                return self._failure_response(
                    validated_url,
                    "Minimal content extracted from URL",
                    content=raw_content,
                    title=title,
                    original_length=len(raw_content),
                    final_length=len(raw_content),
                )

            # Always apply content cleaning
            logger.info(f"[task_id={task_id}] Cleaning content for: {validated_url}")
            final_content = clean_web_content(raw_content)

            # Truncate if too long
            if len(final_content) > MAX_CONTENT_LENGTH:
                final_content = (
                    final_content[:MAX_CONTENT_LENGTH] + "\n\n[Content truncated]"
                )
                truncated = True
            else:
                truncated = False

            # Prepare result data
            result_data = {
                "success": True,
                "url": validated_url,
                "content": final_content,
                "title": title,
                "cleaned": True,
                "truncated": truncated,
                "original_length": len(raw_content),
                "final_length": len(final_content),
            }

            # Always save to file
            file_path = self._save_to_file(result_data, validated_url)
            if file_path:
                result_data["file_path"] = file_path
            else:
                result_data["file_path"] = None
                result_data["save_error"] = "Failed to save file"

            logger.info(
                f"[task_id={task_id}] web_browser_completed: "
                f"tool=browse_webpage, status=SUCCESS, url={validated_url}, "
                f"file_path={file_path or 'N/A'}, final_length={len(final_content)}"
            )

            return json.dumps(result_data, ensure_ascii=False)

        except Exception as e:
            logger.error(
                f"[task_id={task_id}] web_browser_completed: "
                f"tool=browse_webpage, status=FAILED, error={str(e)}"
            )
            return self._failure_response(
                validated_url, f"Web browsing failed: {str(e)}"
            )


# Example usage
if __name__ == "__main__":
    # Initialize the WebCrawler
    web_crawler = WebBrowser()

    # Test 1: Crawl Webpage
    print("\n --- Testing browse_webpage ---")
    results = web_crawler.browse_webpage(url="https://www.aexonic.com")
    print(results)
