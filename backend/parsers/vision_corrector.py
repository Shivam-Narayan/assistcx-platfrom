import os
import re
import base64
import asyncio
import gc
import time
from typing import List, Optional, Tuple
from typing_extensions import deprecated
from pathlib import Path

# Custom imports
from logger import configure_logging
from agents.shared_utils.llm_provider import LLMProvider
from .data_class import Page, ParserOutput
from .prompts import VISION_CORRECTION_PROMPT, VISION_PARSER_PROMPT
from sqlalchemy.orm import Session

logger = configure_logging(__name__)


@deprecated("Use VisionParser instead.")
class VisionCorrector:
    """Class for correcting OCR output using vision models"""

    # Model Constants
    DEFAULT_TIMEOUT = 120  # llm call timeout in seconds
    DEFAULT_CONCURRENCY = 10  # Number of concurrent pages to process
    DEFAULT_WORD_LIMIT = 1200  # Word limit per page for correction
    DEFAULT_PAGE_LIMIT = 1000  # Maximum number of pages to process (set high to effectively disable limit)
    MAX_LLM_RETRY = 1  # Maximum number of retries for LLM calls
    BLANK_PAGE_THRESHOLD = 99.8  # Threshold for blank page detection

    def __init__(
        self,
        organization_schema: str,
        db: Session,
        include_details: bool = False,
        parse_mode: bool = False,
    ):
        """
        Initialize the vision corrector

        Args:
            organization_schema: Organization schema
            db: Database session (required)
            include_details: Whether to include correction details
            parse_mode: Whether to use parser mode (True) or correction mode (False)
        """
        self.agent_llm = LLMProvider(organization_schema, db)
        self.llm = self.agent_llm.get_llm()
        self.include_details = include_details
        self.parse_mode = parse_mode

    def _sanitize_page_text(self, ocr_text: str) -> str:
        """Replace barcode artifacts with spaces to preserve layout."""
        # Handle None or empty text - convert to empty string
        if not ocr_text:
            ocr_text = ""

        # Find all words and check for suspicious patterns
        words = re.findall(r"\S+", ocr_text)
        result = ocr_text

        for word in words:
            ll_count = word.lower().count("ll")
            ii_count = word.lower().count("ii")
            ili_count = word.lower().count("ili")

            # Check for barcode-like patterns
            if (
                ll_count >= 3
                or ii_count >= 3
                or ili_count >= 2
                or (
                    len(word) > 10
                    and (
                        word.count("|") > len(word) * 0.5
                        or word.count(":") > len(word) * 0.5
                    )
                )
            ):
                # Replace word with spaces of same length to preserve layout
                result = result.replace(word, " " * len(word))

        return result

    async def correct_pages(
        self,
        pages: List[Page],
        output_dir: Optional[str] = None,
        file_name: Optional[str] = None,
    ) -> ParserOutput:
        """
        Correct OCR output using vision model by comparing with original images.

        Args:
            pages: List of Page objects containing OCR text and image paths
            output_dir: Optional directory to save corrected output
            file_name: Name of the file being processed
        """
        try:
            start_time = time.time()
            total_pages = len(pages)
            pages_to_process = min(total_pages, self.DEFAULT_PAGE_LIMIT)

            logger.info(
                f"Starting vision correction: file={file_name or 'unknown'}, pages={pages_to_process}/{total_pages}, concurrent_tasks={self.DEFAULT_CONCURRENCY}, word_limit={self.DEFAULT_WORD_LIMIT}"
            )

            semaphore = asyncio.Semaphore(self.DEFAULT_CONCURRENCY)
            results: List[Optional[Tuple[Page, dict]]] = [None] * total_pages
            task_indices: List[int] = []
            tasks: List[asyncio.Future] = []
            skipped_count = 0

            async def run_with_retry(page: Page) -> Tuple[Page, dict]:
                for attempt in range(self.MAX_LLM_RETRY + 1):
                    try:
                        async with semaphore:
                            return await self._process_page(page)
                    except Exception as exc:
                        if attempt == self.MAX_LLM_RETRY:
                            logger.error(
                                f"Page {page.page_number} failed after {self.MAX_LLM_RETRY + 1} attempts: {exc}"
                            )
                            page.corrected_content = page.original_content
                            page.correction_details = (
                                f"Failed after {self.MAX_LLM_RETRY + 1} attempts: {exc}"
                            )
                            return page, {"input_tokens": 0, "output_tokens": 0}

                        wait_time = 2**attempt
                        logger.warning(
                            f"Page {page.page_number} attempt {attempt + 1} failed: {exc}, retrying in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)

            for idx, page in enumerate(pages):
                if idx >= self.DEFAULT_PAGE_LIMIT:
                    page.corrected_content = page.original_content
                    page.correction_details = (
                        f"Skipped: Beyond page limit ({self.DEFAULT_PAGE_LIMIT})"
                    )
                    results[idx] = (page, {"input_tokens": 0, "output_tokens": 0})
                    skipped_count += 1
                    continue

                content_words = len((page.original_content or "").split())
                if content_words > self.DEFAULT_WORD_LIMIT:
                    logger.info(
                        f"Skipping page {page.page_number} - word count {content_words} exceeds limit {self.DEFAULT_WORD_LIMIT}"
                    )
                    page.corrected_content = page.original_content
                    page.correction_details = (
                        f"Skipped: Exceeds word limit ({self.DEFAULT_WORD_LIMIT})"
                    )
                    results[idx] = (page, {"input_tokens": 0, "output_tokens": 0})
                    skipped_count += 1
                    continue

                task_indices.append(idx)
                tasks.append(run_with_retry(page))

            if tasks:
                gathered = await asyncio.gather(*tasks)
                for idx, page_result in zip(task_indices, gathered):
                    results[idx] = page_result

                gc.collect()

            corrected_pages: List[Tuple[Page, dict]] = [
                entry for entry in results if entry is not None
            ]

            input_tokens = sum(
                page_tokens["input_tokens"] for _, page_tokens in corrected_pages
            )
            output_tokens = sum(
                page_tokens["output_tokens"] for _, page_tokens in corrected_pages
            )

            if output_dir:
                await self._save_corrections(output_dir, corrected_pages)

            elapsed_time = time.time() - start_time
            pages_corrected = len(tasks)

            logger.info(
                f"Completed vision correction: file={file_name or 'unknown'}, time={elapsed_time:.2f}s, pages_corrected={pages_corrected}, pages_skipped={skipped_count}, tokens={{input:{input_tokens}, output:{output_tokens}}}"
            )

            return ParserOutput(
                completion_time=elapsed_time,
                file_name=file_name or "unknown",
                pages=[page for page, _ in corrected_pages],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(
                f"Vision correction failed: file={file_name or 'unknown'}, time={elapsed_time:.2f}s, error={str(e)}"
            )
            raise

    def is_image_blank(self, image_path: str) -> bool:
        """Check if an image file is blank by analyzing white pixel percentage."""
        try:
            from PIL import Image, ImageFilter
            import numpy as np

            img = Image.open(image_path).convert("L")
            img = img.filter(ImageFilter.MedianFilter(size=3))
            gray_array = np.array(img)

            total_pixels = gray_array.size
            white_pixels = np.sum(gray_array > 250)
            white_percentage = (white_pixels / total_pixels) * 100

            return white_percentage >= self.BLANK_PAGE_THRESHOLD

        except Exception as e:
            logger.error(f"Error checking if image is blank: {e}")
            return False

    async def _process_page(self, page: Page) -> Tuple[Page, dict]:
        """Run vision correction for a single page."""
        start_time = time.time()

        # Skip blank pages by checking the actual image
        if page.image_path and os.path.exists(page.image_path):
            if self.is_image_blank(page.image_path):
                logger.info(f"Skipping blank page {page.page_number}")
                page.corrected_content = page.original_content or ""
                page.correction_details = "Skipped: Blank page"
                return page, {"input_tokens": 0, "output_tokens": 0}

        def read_image_as_base64() -> str:
            with open(page.image_path, "rb") as f:
                # Stream directly to base64 encoder without storing raw bytes
                return base64.b64encode(f.read()).decode()

        # Get base64 directly - no intermediate raw bytes variable
        base64_image = await asyncio.to_thread(read_image_as_base64)

        # Select prompt based on mode
        system_message = (
            VISION_PARSER_PROMPT if self.parse_mode else VISION_CORRECTION_PROMPT
        )

        # Build user message content based on mode
        user_content = []

        if not self.parse_mode:
            # Correction mode: include sanitized OCR text
            original_content = self._sanitize_page_text(page.original_content)
            user_content.append(
                {
                    "type": "text",
                    "text": f"Original OCR Text output: \n```\n{original_content}\n```\n",
                }
            )

        # Always include the image
        user_content.append(
            {
                "type": "image",
                "source_type": "base64",
                "data": base64_image,
                "mime_type": "image/jpeg",
            }
        )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_content},
        ]

        try:
            response = await asyncio.wait_for(
                self.llm.ainvoke(messages), timeout=self.DEFAULT_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"LLM call timed out after {self.DEFAULT_TIMEOUT}s for Page {page.page_number}"
            )
            raise

        corrected_output, correction_details = self.parse_response(response.content)

        page.corrected_content = (
            corrected_output if corrected_output else page.original_content
        )
        page.correction_details = correction_details

        tokens = {
            "input_tokens": response.usage_metadata.get("input_tokens", 0),
            "output_tokens": response.usage_metadata.get("output_tokens", 0),
        }

        elapsed_time = time.time() - start_time
        logger.info(
            f"Processed page {page.page_number}: input_tokens={tokens['input_tokens']}, output_tokens={tokens['output_tokens']}, processing_time={elapsed_time:.2f}s"
        )
        return page, tokens

    def parse_response(self, response: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse the LLM response to extract corrected output and correction details.

        Args:
            response: Raw response from the LLM

        Returns:
            Tuple of (corrected_output, correction_details)
            - corrected_output: The text between triple backticks
            - correction_details: Raw correction details text
        """
        try:
            # Handle None or empty response
            if not response:
                logger.warning("Received None or empty response from LLM")
                return None, None

            # Extract corrected output (text between triple backticks)
            output_pattern = r"```.*?\n(.*?)\n```"  # r"```\n?(.*?)\n?```"

            output_match = re.search(output_pattern, response, re.DOTALL)
            corrected_output = output_match.group(1).strip() if output_match else None

            # Extract correction details as raw text
            details_pattern = r"<correction_details>\n(.*?)\n</correction_details>"
            details_match = re.search(details_pattern, response, re.DOTALL)
            correction_details = (
                details_match.group(1).strip() if details_match else None
            )

            return corrected_output, correction_details

        except Exception as e:
            logger.error(f"Error parsing correction response: {str(e)}")
            return None, None

    async def _save_corrections(
        self, output_dir: str, pages: List[tuple[Page, dict]]
    ) -> None:
        """Save corrected pages to output directory"""
        os.makedirs(output_dir, exist_ok=True)

        async def write_file(file_path, content):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: open(file_path, "w", encoding="utf-8").write(content)
            )

        for page, tokens in pages:
            # Save corrected content
            corrected_path = Path(output_dir) / f"page{page.page_number}_corrected.txt"
            await write_file(corrected_path, page.corrected_content)

            # Save diff information
            diff_path = Path(output_dir) / f"page{page.page_number}_diff.txt"
            diff_content = (
                f"Original Length: {len(page.original_content)}\n"
                f"Corrected Length: {len(page.corrected_content)}\n"
                f"Input Tokens: {tokens['input_tokens']}\n"
                f"Output Tokens: {tokens['output_tokens']}\n"
            )
            await write_file(diff_path, diff_content)
