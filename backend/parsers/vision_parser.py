# Default libraries
import os
import re
import base64
import gc
import time
import asyncio
import shutil
from typing import Optional, List, Tuple
from pathlib import Path

# Installed libraries
import fitz
from jinja2 import Template
from PIL import Image
from pdf2image import convert_from_path

# Custom libraries
from logger import configure_logging
from agents.shared_utils.llm_provider import LLMProvider
from sqlalchemy.orm import Session

# Local modules
from .data_class import Page, ParserOutput
from .prompts import VISION_CORRECTION_PROMPT, VISION_PARSER_PROMPT
from schemas.parsed_document_schema import ParsedDocument


logger = configure_logging(__name__)


class VisionParser:
    """
    A class for parsing text content from images and PDF files using vision-based LLM parsing.

    Unlike OCR-based parsers, this parser uses vision models directly to extract and structure
    text from images without traditional OCR preprocessing.

    Supports two modes:
    - Direct parsing (default): Extract text directly from images
    - Correction mode: Correct OCR text using image comparison
    """

    # Processing Constants
    DEFAULT_TIMEOUT = 120  # LLM call timeout in seconds
    DEFAULT_CONCURRENCY = 10  # Number of concurrent pages to process
    DEFAULT_WORD_LIMIT = 1200  # Word limit per page for correction
    DEFAULT_PAGE_LIMIT = 1000  # Maximum number of pages to process
    MAX_LLM_RETRY = 1  # Maximum number of retries for LLM calls
    BLANK_PAGE_THRESHOLD = 99.8  # Threshold for blank page detection
    DEFAULT_BATCH_SIZE = 10  # Number of pages to process per LLM call

    def __init__(self, organization_schema: str, db: Session, mode: str = "parsing"):
        """
        Initialize the VisionParser with organization schema.

        Args:
            organization_schema: Organization schema for LLM provider configuration
            db: Database session (required)
            mode: Processing mode - "parsing" (extract text) or "correction" (fix OCR)
        """
        self.organization_schema = organization_schema
        self.mode = mode
        self.temp_dir = None

        # Set batch size for processing
        self.batch_size = self.DEFAULT_BATCH_SIZE

        # Create a small white image for blank pages (4x4 white PNG in base64)
        # This prevents text concatenation issues while using minimal tokens
        self.blank_page_image = self._create_blank_image_base64()

        # Initialize LLM provider
        self.agent_llm = LLMProvider(organization_schema, db)
        self.llm = self.agent_llm.get_llm()

    def _create_blank_image_base64(self) -> str:
        """Create a small 2x2 white image and return as base64 string."""
        from PIL import Image
        import io

        # Create 2x2 white image
        img = Image.new("RGB", (2, 2), color="white")

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=30)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode()

    def _setup_temp_directory(self, file_path: str):
        """Create temp directory for vision parsing workflow"""
        if not self.temp_dir:
            base_name = os.path.basename(file_path).replace(" ", "_").replace(".", "_")
            self.temp_dir = f"/data/temp/{base_name}_vision_parsing"
            os.makedirs(self.temp_dir, exist_ok=True)
        return self.temp_dir

    def _cleanup_temp_directory(self):
        """Clean up temp directory created by vision parser"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
            except Exception as e:
                logger.warning(
                    f"Could not clean up temp directory {self.temp_dir}: {e}"
                )

    def _pdf_to_images(self, pdf_path: str, page_limit=None, temp_dir=None):
        """Convert PDF pages to images with optimized memory usage.

        Args:
            pdf_path (str): Path to the PDF file
            page_limit (int, optional): Number of first pages to process
            temp_dir (str, optional): Directory to save images

        Returns:
            List[str]: Paths to the generated image files
        """
        try:
            # Use provided temp_dir or create one
            if not temp_dir:
                temp_dir = self._setup_temp_directory(pdf_path)

            base_name = os.path.splitext(os.path.basename(pdf_path))[0]

            # Configure conversion parameters (same as OCR parser)
            convert_params = {
                "dpi": 150,
                "fmt": "jpeg",
                "use_pdftocairo": True,
                "single_file": False,
                "paths_only": True,
                "output_folder": str(temp_dir),
                "output_file": base_name,
                "thread_count": 1,  # Prevent memory spikes
            }

            # Determine actual page count and set page range
            with fitz.open(pdf_path) as doc:
                total_pages = len(doc)

            if page_limit and page_limit > 0:
                # Process only first N pages (or all pages if document has fewer)
                pages_to_process = min(page_limit, total_pages)
                convert_params["first_page"] = 1
                convert_params["last_page"] = pages_to_process
                logger.info(
                    f"Converting first {pages_to_process} pages from PDF to images (requested: {page_limit}, total: {total_pages})"
                )
            else:
                # Process all pages
                logger.info(f"Converting all {total_pages} pages from PDF to images")

            # Convert PDF to images
            images = convert_from_path(pdf_path, **convert_params)
            # Force GC after bulk image creation to free pdf2image memory
            gc.collect()

            # Process image paths - resize if needed (same logic as OCR parser)
            result_paths = []
            max_width = 1500
            image_format = "jpeg"

            for i, path in enumerate(images, start=1):
                # Check dimensions and resize if needed
                with Image.open(path) as original_img:
                    width, height = original_img.size
                    if width > max_width:
                        # Resize in one operation
                        new_height = int((max_width / width) * height)
                        resized_img = original_img.resize(
                            (max_width, new_height), Image.LANCZOS
                        )
                        resized_img.save(path, format=image_format)
                        resized_img.close()  # Explicitly close the resized image

                result_paths.append(path)

            return result_paths

        except Exception as e:
            logger.error(f"Error converting PDF to images: {str(e)}")
            raise

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

    def is_image_blank(self, image_path: str) -> bool:
        """Check if an image file is blank by analyzing white pixel percentage."""
        try:
            from PIL import ImageFilter
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

    def parse_response(self, response: str) -> Optional[str]:
        """
        Parse the LLM response to extract parsed content.

        Args:
            response: Raw response from the LLM

        Returns:
            Parsed content (text between triple backticks)
        """
        try:
            # Handle None or empty response
            if not response:
                logger.warning("Received None or empty response from LLM")
                return None

            # Extract parsed output (text between triple backticks)
            output_pattern = r"```.*?\n(.*?)\n```"

            output_match = re.search(output_pattern, response, re.DOTALL)
            parsed_output = output_match.group(1).strip() if output_match else None

            return parsed_output

        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}")
            return None

    def _parse_batch_response(
        self, response_content: str, pages: List[Page]
    ) -> List[str]:
        """
        Parse LLM response containing single or multiple pages.

        Args:
            response_content: Raw response from LLM
            pages: List of Page objects processed

        Returns:
            List[str]: List of extracted text for each page
        """
        try:
            # Extract content from ``` blocks (reuse existing method)
            content = self.parse_response(response_content)
            if not content:
                logger.warning("No content extracted from response")
                return [""] * len(pages)

            # Single page - return as-is
            if len(pages) == 1:
                return [content]

            # Multi-page - split by page markers
            page_number_to_idx = {
                page.page_number: idx for idx, page in enumerate(pages)
            }

            # Initialize result list with empty strings
            page_texts = [""] * len(pages)

            # Split by page markers: "--- Page X ---"
            page_pattern = r"---\s*Page\s+(\d+)\s*---"
            parts = re.split(page_pattern, content)

            # Parse alternating pattern: [text_before, page_num, page_content, page_num, page_content, ...]
            for i in range(1, len(parts), 2):
                if i + 1 < len(parts):
                    page_num = int(parts[i])
                    page_content = parts[i + 1].strip()

                    # Map to correct index in our pages list
                    if page_num in page_number_to_idx:
                        idx = page_number_to_idx[page_num]
                        page_texts[idx] = page_content
                    else:
                        logger.warning(
                            f"Page {page_num} in response not found in input pages"
                        )

            # Log pages that weren't found in response
            for idx, text in enumerate(page_texts):
                if not text:
                    page_num = pages[idx].page_number
                    logger.warning(f"No content found in response for page {page_num}")
                    # Keep original content as fallback
                    page_texts[idx] = pages[idx].original_content or ""

            return page_texts

        except Exception as e:
            logger.error(f"Error parsing batch response: {e}")
            return [""] * len(pages)

    async def _build_user_content(self, pages: List[Page]) -> List[dict]:
        """
        Build user content for N pages with page markers and images.

        Args:
            pages: List of Page objects to process

        Returns:
            List of content dictionaries for LLM user message
        """
        user_content = []

        # We'll add instruction as part of first page to avoid whitespace stripping
        instruction_text = ""
        if len(pages) > 1:
            instruction_text = f"Following are the {len(pages)} pages from the document. For each page, start your output with '--- Page X ---' followed by the extracted text.\n\n"

        # Add each page with marker (for multi-page) and image
        for idx, page in enumerate(pages):
            # Handle blank pages - treat like normal pages but replace image with text
            is_blank = False
            if page.image_path and os.path.exists(page.image_path):
                if self.is_image_blank(page.image_path):
                    is_blank = True
                    logger.info(f"Detected blank page {page.page_number}")

            # Handle blank pages - treat exactly like normal pages but with a tiny white image
            if is_blank:
                # Build text content exactly like normal pages
                blank_text = ""

                # Add instruction for first page
                if idx == 0:
                    blank_text = instruction_text

                # Add page marker with leading newlines for spacing
                if len(pages) > 1:
                    if idx > 0:
                        blank_text += f"\n\n--- Page {page.page_number} ---\n"
                    else:
                        blank_text += f"--- Page {page.page_number} ---\n"

                user_content.append({"type": "text", "text": blank_text})

                # Add a small white image - LLM will understand it's blank from the image
                user_content.append(
                    {
                        "type": "image",
                        "source_type": "base64",
                        "data": self.blank_page_image,
                        "mime_type": "image/jpeg",
                    }
                )
                continue

            # Build text content before image (marker + optional OCR)
            text_before_content = ""

            # Add instruction for first page
            if idx == 0:
                text_before_content = instruction_text

            # Add page marker for multi-page batches with leading newlines for spacing
            if len(pages) > 1:
                # Add leading newlines for pages after the first
                if idx > 0:
                    text_before_content += f"\n\n--- Page {page.page_number} ---\n"
                else:
                    text_before_content += f"--- Page {page.page_number} ---\n"

            # Add OCR text for correction mode
            if self.mode == "correction":
                original_content = self._sanitize_page_text(page.original_content)
                text_before_content += (
                    f"Original OCR Text output: \n```\n{original_content}\n```\n"
                )

            # Add text before image
            if text_before_content:
                user_content.append({"type": "text", "text": text_before_content})

            # Add image
            def read_image_as_base64() -> str:
                with open(page.image_path, "rb") as f:
                    return base64.b64encode(f.read()).decode()

            base64_image = await asyncio.to_thread(read_image_as_base64)
            user_content.append(
                {
                    "type": "image",
                    "source_type": "base64",
                    "data": base64_image,
                    "mime_type": "image/jpeg",
                }
            )

        return user_content

    async def _process_page_batch(
        self, pages: List[Page], instructions: Optional[str] = None
    ) -> Tuple[List[Page], dict]:
        """
        Process one or more pages in a single LLM call.

        Args:
            pages: List of Page objects (1-10 pages typically)
            instructions: Optional user instructions for LLM

        Returns:
            Tuple of (processed pages, token usage dict)
        """
        start_time = time.time()
        batch_page_numbers = [p.page_number for p in pages]

        # Build user content with page markers and images
        user_content = await self._build_user_content(pages)

        if not user_content:
            logger.warning(f"No valid pages to process in batch {batch_page_numbers}")
            return pages, {"input_tokens": 0, "output_tokens": 0}

        # Build system message with instructions
        prompt_template = (
            VISION_CORRECTION_PROMPT
            if self.mode == "correction"
            else VISION_PARSER_PROMPT
        )
        system_message = Template(prompt_template).render(
            user_instructions=instructions or ""
        )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_content},
        ]

        # Call LLM with timeout scaled to batch size
        batch_timeout = self.DEFAULT_TIMEOUT * len(pages)
        try:
            response = await asyncio.wait_for(
                self.llm.ainvoke(messages), timeout=batch_timeout
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"LLM call timed out after {batch_timeout}s for pages {batch_page_numbers}"
            )
            raise

        # Parse response for all pages in batch
        page_texts = self._parse_batch_response(response.content, pages)

        # Assign corrected content to pages
        for page, corrected_text in zip(pages, page_texts):
            page.corrected_content = (
                corrected_text if corrected_text else page.original_content
            )

        tokens = {
            "input_tokens": response.usage_metadata.get("input_tokens", 0),
            "output_tokens": response.usage_metadata.get("output_tokens", 0),
        }

        elapsed_time = time.time() - start_time
        logger.info(
            f"Processed pages {batch_page_numbers}: time={elapsed_time:.2f}s, "
            f"input_tokens={tokens['input_tokens']}, output_tokens={tokens['output_tokens']}"
        )

        return pages, tokens

    async def process_pages(
        self,
        pages: List[Page],
        output_dir: Optional[str] = None,
        file_name: Optional[str] = None,
        instructions: Optional[str] = None,
    ) -> ParserOutput:
        """
        Process pages using vision model.

        Args:
            pages: List of Page objects containing OCR text and image paths
            output_dir: Optional directory to save corrected output
            file_name: Name of the file being processed
            instructions: Optional user instructions for LLM

        Returns:
            ParserOutput with processed pages and token usage
        """
        try:
            start_time = time.time()
            total_pages = len(pages)
            pages_to_process = min(total_pages, self.DEFAULT_PAGE_LIMIT)

            logger.info(
                f"Starting vision {self.mode}: file={file_name or 'unknown'}, pages={pages_to_process}/{total_pages}, batch_size={self.batch_size}, concurrent_tasks={self.DEFAULT_CONCURRENCY}"
            )

            # Filter pages by word limit and page limit
            valid_pages = []
            skipped_count = 0

            for idx, page in enumerate(pages):
                if idx >= self.DEFAULT_PAGE_LIMIT:
                    page.corrected_content = page.original_content
                    skipped_count += 1
                    continue

                content_words = len((page.original_content or "").split())
                if content_words > self.DEFAULT_WORD_LIMIT:
                    logger.info(
                        f"Skipping page {page.page_number} - word count {content_words} exceeds limit {self.DEFAULT_WORD_LIMIT}"
                    )
                    page.corrected_content = page.original_content
                    skipped_count += 1
                    continue

                valid_pages.append(page)

            if not valid_pages:
                logger.info("No valid pages to process")
                return ParserOutput(
                    completion_time=0,
                    file_name=file_name or "unknown",
                    pages=pages,
                    input_tokens=0,
                    output_tokens=0,
                )

            # Batch pages by self.batch_size
            batches = [
                valid_pages[i : i + self.batch_size]
                for i in range(0, len(valid_pages), self.batch_size)
            ]

            logger.info(
                f"Processing {len(valid_pages)} pages in {len(batches)} batches"
            )

            # Process batches concurrently with retry logic
            semaphore = asyncio.Semaphore(self.DEFAULT_CONCURRENCY)

            async def run_batch_with_retry(
                batch: List[Page],
            ) -> Tuple[List[Page], dict]:
                for attempt in range(self.MAX_LLM_RETRY + 1):
                    try:
                        async with semaphore:
                            return await self._process_page_batch(batch, instructions)
                    except Exception as exc:
                        if attempt == self.MAX_LLM_RETRY:
                            batch_numbers = [p.page_number for p in batch]
                            logger.error(
                                f"Batch {batch_numbers} failed after {self.MAX_LLM_RETRY + 1} attempts: {exc}"
                            )
                            # Fallback to original content
                            for page in batch:
                                page.corrected_content = page.original_content
                            return batch, {"input_tokens": 0, "output_tokens": 0}

                        wait_time = 2**attempt
                        logger.warning(
                            f"Batch attempt {attempt + 1} failed: {exc}, retrying in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)

            # Execute all batches concurrently
            batch_results = await asyncio.gather(
                *[run_batch_with_retry(batch) for batch in batches]
            )

            gc.collect()

            # Flatten results and aggregate tokens
            all_processed_pages = []
            input_tokens = 0
            output_tokens = 0

            for batch_pages, tokens in batch_results:
                all_processed_pages.extend(batch_pages)
                input_tokens += tokens["input_tokens"]
                output_tokens += tokens["output_tokens"]

            elapsed_time = time.time() - start_time

            logger.info(
                f"Completed vision {self.mode}: file={file_name or 'unknown'}, time={elapsed_time:.2f}s, pages_processed={len(valid_pages)}, pages_skipped={skipped_count}, batches={len(batches)}, tokens={{input:{input_tokens}, output:{output_tokens}}}"
            )

            return ParserOutput(
                completion_time=elapsed_time,
                file_name=file_name or "unknown",
                pages=pages,  # Return all pages (including skipped ones)
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(
                f"Vision processing failed: file={file_name or 'unknown'}, time={elapsed_time:.2f}s, error={str(e)}"
            )
            raise

    def _prepare_images(
        self, file_path: str, page_limit: Optional[int] = None
    ) -> List[str]:
        """
        Prepare images from file path (PDF or image).

        Args:
            file_path: Path to PDF or image file
            page_limit: Optional limit on number of pages (PDF only)

        Returns:
            List of image paths
        """
        file_ext = os.path.splitext(file_path)[1].lower()
        is_pdf = file_ext == ".pdf"
        is_image = file_ext in [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"]

        if not is_pdf and not is_image:
            raise ValueError(f"Unsupported file type: {file_ext}")

        if is_pdf:
            # Convert PDF to images
            temp_dir = self._setup_temp_directory(file_path)
            return self._pdf_to_images(file_path, page_limit, temp_dir)
        else:
            # Single image file
            return [file_path]

    async def _process_images(
        self, image_paths: List[str], file_name: str, instructions: Optional[str] = None
    ) -> ParserOutput:
        """
        Process images using vision model.

        Args:
            image_paths: List of paths to image files
            file_name: Name of the source file for logging
            instructions: Optional user instructions for LLM

        Returns:
            ParserOutput with parsed content and token usage
        """
        try:
            # Create Page objects from image paths
            # In non-correction mode, we don't have OCR text, so original_content is empty
            pages = [
                Page(
                    page_number=i + 1,
                    original_content="",  # No OCR content in direct parsing
                    image_path=path,
                )
                for i, path in enumerate(image_paths)
            ]

            logger.info(f"Processing {len(pages)} images using vision parser")

            # Process all pages through process_pages
            result = await self.process_pages(
                pages=pages, file_name=file_name, instructions=instructions
            )

            return result

        except Exception as e:
            logger.error(f"Error processing images with vision parser: {str(e)}")
            raise

    def format_parser_output(self, result: ParserOutput, input_file: str) -> ParsedDocument:
        """
        Format the vision parser results into a ParsedDocument.

        Args:
            result: ParserOutput from vision corrector
            input_file: Path to the input file

        Returns:
            ParsedDocument with standardized parser output
        """
        total_pages = len(result.pages)
        formatted_pages = []

        for page in result.pages:
            header = f"========== Page {page.page_number} of {total_pages} =========="
            content = page.corrected_content if page.corrected_content else ""
            formatted_pages.append(f"{header}\n{content}\n")

        combined_text = "\n\n".join(formatted_pages)

        return ParsedDocument(
            input_file=input_file,
            extracted_data=[combined_text],
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )

    async def parse_file(
        self,
        file_path: Optional[str] = None,
        page_limit: Optional[int] = None,
        pages: Optional[List[Page]] = None,
        instructions: Optional[str] = None,
    ) -> Optional[ParsedDocument]:
        """
        Main entry point for parsing files using vision-based parsing.

        Supports flexible input options:
        - Option 1: Provide file_path (PDF/image) -> Auto converts to Page objects
        - Option 2: Provide pages (List[Page]) -> Process directly

        Args:
            file_path: Path to the file (PDF or image). Mutually exclusive with pages.
            page_limit: Optional limit on number of pages to process (PDF only)
            pages: List of Page objects to process directly. Mutually exclusive with file_path.

        Returns:
            ParsedDocument with extracted content and metadata, or None on failure.

        Raises:
            ValueError: If neither or both file_path and pages are provided
        """
        # Validate inputs
        if not file_path and not pages:
            raise ValueError("Either file_path or pages must be provided")
        if file_path and pages:
            raise ValueError("Provide only one: file_path OR pages")

        try:
            # Path 1: File provided → prepare images and create Page objects
            if file_path:
                # Get file info for logging
                file_size = os.path.getsize(file_path)
                file_size_kb = file_size / 1024
                file_name = os.path.basename(file_path)

                try:
                    # Prepare images (handles both PDF and image files)
                    image_paths = self._prepare_images(file_path, page_limit)

                    # Log info based on file type
                    file_ext = os.path.splitext(file_path)[1].lower()
                    if file_ext == ".pdf":
                        with fitz.open(file_path) as doc:
                            total_pages = len(doc)
                        pages_to_process = (
                            min(page_limit, total_pages) if page_limit else total_pages
                        )
                        logger.info(
                            f"Processing PDF with vision parser: file={file_name}, "
                            f"size={file_size_kb:.0f}KB, pages={pages_to_process}/{total_pages}"
                        )
                    else:
                        logger.info(
                            f"Processing image with vision parser: file={file_name}, "
                            f"size={file_size_kb:.0f}KB"
                        )

                    # Process images
                    parser_result = await self._process_images(
                        image_paths=image_paths,
                        file_name=file_name,
                        instructions=instructions,
                    )
                    input_file = file_path

                finally:
                    # Always cleanup temp directory
                    self._cleanup_temp_directory()

            # Path 2: Pages provided → process directly
            else:
                file_name = "page_list"
                input_file = "page_list"

                logger.info(f"Processing {len(pages)} pages with vision parser")

                # Process pages directly
                parser_result = await self.process_pages(
                    pages=pages, file_name=file_name, instructions=instructions
                )

            # Format output to match PDFParser format
            formatted_output = self.format_parser_output(
                result=parser_result, input_file=input_file
            )

            logger.info(
                f"Vision parsing complete: file={file_name}, "
                f"pages={len(parser_result.pages)}, "
                f"tokens={{input:{parser_result.input_tokens}, output:{parser_result.output_tokens}}}"
            )

            return formatted_output

        except Exception as e:
            logger.error(f"Error during vision parsing: {str(e)}", exc_info=True)
            # Ensure cleanup even on error
            if file_path:
                self._cleanup_temp_directory()
            return None
