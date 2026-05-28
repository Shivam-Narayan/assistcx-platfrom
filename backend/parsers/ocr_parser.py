import os
import json
import asyncio
import shutil
import time
import fitz
import gc
import numpy as np
from typing import Optional, List
from typing_extensions import deprecated
from dotenv import load_dotenv
from logger import configure_logging
from pathlib import Path
from pdf2image import convert_from_path
from PIL import Image

# Local modules
from .ocr_layout import TextLayoutGenerator

# from .vision_corrector import VisionCorrector
from .data_class import Page, ParserOutput

logger = configure_logging(__name__)

load_dotenv()


@deprecated("Use VisionParser instead.")
class OCRParser:
    """
    A class for extracting text from images and PDF using OCR.
    """

    def __init__(self, organization_schema: str):
        """
        Initialize the OCRParser with organization schema.
        File paths will be passed to individual processing methods.
        """
        # OCR Parser parameters
        self.organization_schema = organization_schema
        self.doctr_predictor = None
        self.temp_dir = None
        self._initialize_doctr_predictor()

        # Image conversion parameters
        self.image_dpi = 150
        self.image_format = "jpeg"
        self.max_width = 1500
        self.use_pdftocairo = True

        # Batch processing parameters
        self.page_batch_size = 10  # Default batch size for large PDFs

    def _initialize_doctr_predictor(self):
        """Initialize the ONNX DocTR predictor if in the attachment-worker container."""
        if os.environ.get("SERVICE_TYPE") == "attachment-worker":
            try:
                from onnxtr.models import ocr_predictor

                self.doctr_predictor = ocr_predictor(
                    det_arch="fast_base",
                    reco_arch="parseq",
                    det_bs=2,  # detection batch size
                    reco_bs=512,  # recognition batch size
                    assume_straight_pages=True,
                    straighten_pages=False,
                    # Preprocessing related parameters
                    preserve_aspect_ratio=True,
                    symmetric_pad=True,
                    detect_orientation=False,
                    detect_language=True,
                    resolve_lines=True,
                    resolve_blocks=True,
                    paragraph_break=0.035,
                )
                self.doctr_predictor.det_predictor.model.postprocessor.bin_thresh = 0.35
                self.doctr_predictor.det_predictor.model.postprocessor.box_thresh = 0.3
            except Exception as e:
                logger.error(
                    f"Failed to initialize OCR predictor: {str(e)}", exc_info=True
                )
        else:
            logger.info("OCR predictor not initialized.")

    def _setup_temp_directory(self, pdf_path: str) -> str:
        """Create a unique temp directory for the file"""
        base_name = Path(pdf_path).stem.replace(" ", "_")
        temp_dir = Path("/data/temp") / base_name
        os.makedirs(temp_dir, exist_ok=True)
        self.temp_dir = temp_dir
        return str(temp_dir)

    def _cleanup_temp_directory(self):
        """Clean up temp directory created by PDF parser"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
            except Exception as e:
                logger.warning(
                    f"Could not clean up temp directory {self.temp_dir}: {e}"
                )

    def _create_pdf_batch(
        self, source_pdf_path: str, start_page: int, end_page: int, batch_index: int
    ) -> str:
        """
        Create a batch PDF containing specified page range from source PDF.

        Args:
            source_pdf_path: Path to the source PDF file
            start_page: Starting page number (0-indexed)
            end_page: Ending page number (0-indexed, inclusive)
            batch_index: Batch number for file naming

        Returns:
            Path to the created batch PDF file
        """
        try:

            # Generate batch PDF filename
            base_name = Path(source_pdf_path).stem
            batch_filename = f"{base_name}_batch_{batch_index}.pdf"
            batch_path = os.path.join(self.temp_dir, batch_filename)

            # Create batch PDF using PyMuPDF
            with fitz.open(source_pdf_path) as source_doc, fitz.open() as batch_doc:
                # Insert the specified page range
                batch_doc.insert_pdf(source_doc, from_page=start_page, to_page=end_page)
                batch_doc.save(batch_path)

                return batch_path

        except Exception as e:
            logger.error(f"Error creating PDF batch {batch_index}: {e}")
            raise

    def _pdf_to_images(self, pdf_path, page_limit=None):
        """Convert PDF pages to images with optimized memory usage.

        Args:
            pdf_path (str): Path to the PDF file
            page_limit (int, optional): Number of first pages to process

        Returns:
            List[str]: Paths to the generated image files
        """
        try:

            base_name = os.path.splitext(os.path.basename(pdf_path))[0]

            # Configure conversion parameters
            convert_params = {
                "dpi": self.image_dpi,
                "fmt": self.image_format,
                "use_pdftocairo": self.use_pdftocairo,
                "single_file": False,
                "paths_only": True,
                "output_folder": str(self.temp_dir),
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
            else:
                # Process all pages
                pass

            # Convert PDF to images
            images = convert_from_path(pdf_path, **convert_params)
            # Force GC after bulk image creation to free pdf2image memory
            gc.collect()

            # Process image paths - no filtering needed as we already limited conversion
            result_paths = []
            for i, path in enumerate(images, start=1):
                # Check dimensions and resize if needed
                with Image.open(path) as original_img:
                    width, height = original_img.size
                    if width > self.max_width:
                        # Resize in one operation
                        new_height = int((self.max_width / width) * height)
                        resized_img = original_img.resize(
                            (self.max_width, new_height), Image.LANCZOS
                        )
                        resized_img.save(path, format=self.image_format)
                        resized_img.close()  # Explicitly close the resized image

                result_paths.append(path)

            return result_paths

        except Exception as e:
            logger.error(f"Error converting PDF: {str(e)}")
            self._cleanup_temp_directory()
            raise

    def _numpy_to_python(self, obj):
        """Convert numpy types to native Python types for JSON serialization"""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: self._numpy_to_python(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._numpy_to_python(item) for item in obj]
        return obj

    def _normalize_geometry(self, geometry):
        """
        Normalize geometry to return top-left and bottom-right coordinates
        regardless of input format (2-point or multi-point)
        """
        if isinstance(geometry, np.ndarray):
            geometry = geometry.tolist()

        if len(geometry) == 2:
            # Already in [[x1,y1], [x2,y2]] format
            return geometry
        else:
            # Multi-point format - find bounding box
            x_coords = [point[0] for point in geometry]
            y_coords = [point[1] for point in geometry]
            return [[min(x_coords), min(y_coords)], [max(x_coords), max(y_coords)]]

    def _sort_blocks_reading_order(self, blocks, tolerance=0.02):
        """
        Sort blocks in natural reading order (top-to-bottom, left-to-right).
        Works with both 2-point and multi-point geometry formats.
        """

        def get_block_position(block):
            # Normalize geometry and get top-left coordinates
            normalized_geometry = self._normalize_geometry(block["geometry"])
            x1, y1 = normalized_geometry[0]
            return (y1, x1)  # Return (y, x) for sorting

        def are_on_same_line(y1, y2, tolerance):
            return abs(y1 - y2) < tolerance

        # First sort all blocks by y-coordinate (top to bottom)
        blocks_sorted = sorted(blocks, key=lambda b: get_block_position(b)[0])

        # Group blocks that are roughly on the same line
        lines = []
        current_line = []
        current_y = None

        for block in blocks_sorted:
            y = get_block_position(block)[0]

            if current_y is None:
                current_line.append(block)
                current_y = y
            elif are_on_same_line(y, current_y, tolerance):
                current_line.append(block)
            else:
                # Sort current line by x-coordinate
                current_line.sort(key=lambda b: get_block_position(b)[1])
                lines.append(current_line)
                current_line = [block]
                current_y = y

        # Don't forget to add the last line
        if current_line:
            current_line.sort(key=lambda b: get_block_position(b)[1])
            lines.append(current_line)

        # Flatten the lines back into a single list
        return [block for line in lines for block in line]

    def _transform_ocr_blocks(self, ocr_json):
        """Return OCR json as per the blocks"""
        transformed_json = []
        for page in ocr_json.get("pages", []):
            page_data = {
                "page_idx": page.get("page_idx"),
                "dimensions": page.get("dimensions"),
                "orientation": page.get("orientation"),
                "blocks": [],
            }
            blocks = []
            for block in page.get("blocks", []):
                # Process all lines in the block
                block_lines = []
                for line in block.get("lines", []):
                    # Combine words in each line
                    line_text = " ".join(word["value"] for word in line["words"])
                    block_lines.append(line_text)

                # Combine all lines with newline character
                block_text = "\n".join(block_lines)

                # Get the block geometry
                geometry = block.get("geometry", [])

                if isinstance(geometry, (list, tuple)):
                    if len(geometry) == 2:
                        # If geometry already has exactly 2 points, ensure they're lists
                        simplified_geometry = [
                            list(point) if isinstance(point, tuple) else point
                            for point in geometry
                        ]
                    elif len(geometry) >= 4:
                        # If geometry has 4 or more points, find bounding box
                        x_coords = [float(point[0]) for point in geometry]
                        y_coords = [float(point[1]) for point in geometry]
                        top_left = [min(x_coords), min(y_coords)]
                        bottom_right = [max(x_coords), max(y_coords)]
                        simplified_geometry = [top_left, bottom_right]

                    # Only add blocks that have valid geometry
                    if (
                        simplified_geometry
                        and len(simplified_geometry) == 2
                        and all(
                            isinstance(point, list) and len(point) == 2
                            for point in simplified_geometry
                        )
                    ):
                        blocks.append(
                            {"text": block_text, "geometry": simplified_geometry}
                        )

            # Sort blocks in reading order
            sorted_blocks = self._sort_blocks_reading_order(blocks)
            page_data["blocks"] = sorted_blocks
            transformed_json.append(page_data)

        return transformed_json

    def _get_blocks_text(self, transformed_json):
        """
        Extract and combine texts from all blocks in the transformed JSON with double newlines.
        """
        all_texts = []

        for page_idx, page in enumerate(transformed_json, start=1):
            # Collect all block texts from the page
            page_texts = [block["text"] for block in page.get("blocks", [])]
            # Add page texts to main list
            all_texts.extend(page_texts)

        # Join all texts with double newlines
        return "\n\n".join(all_texts)

    def _transform_ocr_lines(self, ocr_json):
        transformed_json = []
        for page in ocr_json.get("pages", []):
            page_data = {
                "page_idx": page.get("page_idx"),
                "dimensions": page.get("dimensions"),
                "orientation": page.get("orientation"),
                "lines": [],
            }
            lines = []
            for block in page.get("blocks", []):
                for line in block.get("lines", []):
                    # Combine all words in the line
                    line_text = " ".join(word["value"] for word in line["words"])

                    # Get and normalize the geometry coordinates
                    geometry = line.get("geometry", [])

                    # Ensure geometry is a list of lists
                    if isinstance(geometry, (list, tuple)):
                        # Convert any numpy arrays or tuples to lists
                        geometry = self._numpy_to_python(geometry)

                        if len(geometry) == 2:
                            # Convert 2-point geometry to 4 points
                            top_left = (
                                geometry[0]
                                if isinstance(geometry[0], list)
                                else list(geometry[0])
                            )
                            bottom_right = (
                                geometry[1]
                                if isinstance(geometry[1], list)
                                else list(geometry[1])
                            )

                            # Create 4 corners from the bounding box
                            four_point_geometry = [
                                top_left,
                                [bottom_right[0], top_left[1]],
                                bottom_right,
                                [top_left[0], bottom_right[1]],
                            ]

                        elif len(geometry) >= 4:
                            # Keep original 4 points for 4-point geometry
                            four_point_geometry = [
                                list(point) if not isinstance(point, list) else point
                                for point in geometry[:4]
                            ]

                        # Validate geometry before adding
                        if (
                            four_point_geometry
                            and len(four_point_geometry) == 4
                            and all(
                                isinstance(point, list) and len(point) == 2
                                for point in four_point_geometry
                            )
                        ):
                            lines.append(
                                {"text": line_text, "geometry": four_point_geometry}
                            )

            page_data["lines"] = lines
            transformed_json.append(page_data)

        return transformed_json

    def _generate_text_layout(
        self, lines_json: List[dict], page_num: int
    ) -> Optional[str]:
        """
        Generates a text-based layout from OCR JSON data using spaces and newlines.
        Includes page headers and trims unnecessary left spacing while preserving relative positioning.
        """
        try:
            generator = TextLayoutGenerator()
            text_layout = generator.generate_layout(lines_json)
            if not text_layout:
                logger.warning("Text layout generation produced no output")
                return None

            return text_layout.strip()

        except Exception as e:
            logger.error(f"Error generating text layout: {e}")
            return None

    def _process_ocr_data(
        self,
        json_data: dict,
        image_paths: List[str],
        preserve_layout: bool = False,
        start_page_offset: int = 0,
    ) -> List[Page]:
        """
        Unified OCR data processing - eliminates duplicate logic across methods.

        Args:
            json_data: OCR JSON data from DocTR
            image_paths: List of image paths corresponding to pages
            preserve_layout: Whether to preserve original layout
            start_page_offset: Starting page number offset (for batch processing)

        Returns:
            List of Page objects ready for vision correction or output
        """
        try:
            # Transform OCR data (this handles all the geometry processing)
            blocks_json = self._transform_ocr_blocks(ocr_json=json_data)
            lines_json = self._transform_ocr_lines(ocr_json=json_data)

            # Process all pages efficiently
            all_pages = []
            page_numbers = range(
                start_page_offset + 1, start_page_offset + len(image_paths) + 1
            )

            for page_json, page_blocks, page_lines, page_num, image_path in zip(
                json_data["pages"], blocks_json, lines_json, page_numbers, image_paths
            ):
                # Generate text content based on layout preference
                text = (
                    self._generate_text_layout([page_lines], page_num)
                    if preserve_layout
                    else self._get_blocks_text([page_blocks])
                )

                # Create page object with all required data
                page = Page(
                    page_number=page_num,
                    original_content=text,
                    corrected_content=text,
                    ocr_json={"pages": [page_json]},
                    ocr_blocks=[page_blocks],
                    ocr_lines=[page_lines],
                    image_path=image_path,
                )
                all_pages.append(page)

            return all_pages

        except Exception as e:
            logger.error(f"Error in unified OCR data processing: {e}")
            return []

    # async def _apply_vision_correction(
    #     self,
    #     pages: List[Page],
    #     correction_details: bool = False,
    # ) -> ParserOutput:
    #     """
    #     Apply vision correction to OCR pages.

    #     Args:
    #         pages: List of pages to correct
    #         correction_details: Whether to include correction details

    #     Returns:
    #         ParserOutput with corrected pages and token usage
    #     """
    #     try:
    #         corrector = VisionCorrector(
    #             organization_schema=self.organization_schema,
    #             include_details=correction_details,
    #             parse_mode=True,
    #         )

    #         # Apply vision correction to OCR pages
    #         correction_result = await corrector.correct_pages(
    #             pages=pages, file_name=os.path.basename(self.file_path)
    #         )

    #         # Update pages with corrected content
    #         for page, corrected in zip(pages, correction_result.pages):
    #             page.corrected_content = corrected.corrected_content
    #             page.image_path = ""  # Clear image path after correction

    #         # Return output with token usage
    #         return ParserOutput(
    #             completion_time=0,  # Timing handled by main function
    #             file_name=os.path.basename(self.file_path),
    #             pages=pages,
    #             input_tokens=correction_result.input_tokens,
    #             output_tokens=correction_result.output_tokens,
    #         )

    #     except Exception as e:
    #         logger.error(f"Vision correction failed: {str(e)}")
    #         # Return output without token usage on error
    #         return ParserOutput(
    #             completion_time=0,
    #             file_name=os.path.basename(self.file_path),
    #             pages=pages,
    #         )

    def _process_pdf_in_batches(
        self,
        file_path: str,
        image_paths: Optional[List[str]] = None,
        page_limit: int = None,
        preserve_layout: bool = False,
        # vision_correction: bool = False,
        correction_details: bool = False,
    ) -> Optional[ParserOutput]:
        """
        Process large PDF in batches to avoid memory issues.

        Args:
            file_path: Path to the PDF file
            image_paths: Optional list of image paths corresponding to PDF pages
            page_limit: Number of first pages to process (applied across all batches)
            preserve_layout: Whether to preserve the original layout
            vision_correction: Whether to perform vision-based correction
            correction_details: Whether to include correction details in the output

        Returns:
            ParserOutput object containing aggregated results from all batches
        """
        try:
            from onnxtr.io import DocumentFile

            start_time = time.time()
            all_pages = []
            total_input_tokens = 0
            total_output_tokens = 0

            # Get PDF info and determine pages to process
            with fitz.open(file_path) as doc:
                total_pages = len(doc)
                pages_to_process = (
                    min(page_limit, total_pages) if page_limit else total_pages
                )

            # Calculate batches
            num_batches = (
                pages_to_process + self.page_batch_size - 1
            ) // self.page_batch_size

            for batch_idx in range(num_batches):
                batch_start_time = time.time()
                batch_pdf_path = None

                try:
                    # Calculate page range for this batch (0-indexed)
                    start_page = batch_idx * self.page_batch_size
                    end_page = min(
                        start_page + self.page_batch_size - 1, pages_to_process - 1
                    )

                    # logger.debug(
                    #     f"Processing batch {batch_idx + 1}/{num_batches} (pages {start_page + 1}-{end_page + 1})"
                    # )

                    # Create batch PDF
                    batch_pdf_path = self._create_pdf_batch(
                        file_path, start_page, end_page, batch_idx + 1
                    )

                    # Process batch using existing OCR pipeline
                    docs = DocumentFile.from_pdf(batch_pdf_path)
                    result = self.doctr_predictor(docs)

                    # Get batch image paths
                    batch_image_paths = (
                        image_paths[start_page : end_page + 1] if image_paths else []
                    )

                    if result is None:
                        logger.warning(
                            f"DocTR OCR failed for batch {batch_idx + 1}, creating empty pages for vision correction fallback"
                        )
                        # Create empty pages with image paths for vision correction
                        batch_pages = [
                            Page(
                                page_number=start_page + i + 1,
                                original_content="",
                                corrected_content="",
                                image_path=img_path if img_path else "",
                            )
                            for i, img_path in enumerate(batch_image_paths)
                        ]
                        all_pages.extend(batch_pages)
                        continue

                    # Process OCR results
                    ocr_json = result.export()
                    json_data = self._numpy_to_python(
                        json.loads(ocr_json) if isinstance(ocr_json, str) else ocr_json
                    )
                    # Free DocTR model tensors and GPU memory immediately
                    result = None
                    gc.collect()

                    # Process pages using unified processor (eliminates ~35 lines of duplicate logic)
                    if not batch_image_paths:
                        batch_image_paths = [""] * len(json_data.get("pages", []))

                    batch_pages = self._process_ocr_data(
                        json_data, batch_image_paths, preserve_layout, start_page
                    )
                    all_pages.extend(batch_pages)

                    batch_time = time.time() - batch_start_time
                    logger.info(
                        f"Processed OCR batch {batch_idx + 1} in {batch_time:.2f} seconds. (pages {start_page + 1}-{end_page + 1})"
                    )

                except Exception as e:
                    logger.error(f"Error processing batch {batch_idx + 1}: {e}")
                    continue

                finally:
                    # Clean up batch PDF immediately
                    if batch_pdf_path and os.path.exists(batch_pdf_path):
                        try:
                            os.remove(batch_pdf_path)
                            # logger.debug(
                            #     f"Cleaned up batch PDF: {os.path.basename(batch_pdf_path)}"
                            # )
                        except Exception as e:
                            logger.warning(f"Could not clean up batch PDF: {e}")

                    # Force garbage collection after each batch
                    gc.collect()

            if not all_pages:
                logger.error("No pages were successfully processed in any batch")
                return None

            # Apply vision correction if requested (to all pages at once)
            # NOTE: Vision correction moved to PDF parser - keeping this code for reference
            # if vision_correction:
            #     corrector = VisionCorrector(
            #         organization_schema=self.organization_schema,
            #         include_details=correction_details,
            #     )
            #     correction_result = asyncio.run(
            #         corrector.correct_pages(
            #             pages=all_pages,
            #             file_name=os.path.basename(file_path),
            #         )
            #     )
            #     total_input_tokens = correction_result.input_tokens
            #     total_output_tokens = correction_result.output_tokens
            #     logger.info("Vision correction completed for all batches")

            # Create final output
            total_time = time.time() - start_time
            output = ParserOutput(
                completion_time=total_time,
                file_name=os.path.basename(file_path),
                pages=all_pages,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
            )

            return output

        except Exception as e:
            logger.error(f"Error in batch PDF processing: {e}")
            return None

    def perform_image_ocr(
        self,
        image_paths: List[str],
        preserve_layout: bool = False,
        # vision_correction: bool = False,
        correction_details: bool = False,
    ) -> Optional[ParserOutput]:
        """
        Perform text extraction on a list of images using DocTR.

        Args:
            image_paths: List of paths to the input image files
            preserve_layout: Whether to preserve the original layout
            # vision_correction: Whether to perform vision-based correction
            correction_details: Whether to include correction details in the output

        Returns:
            ParserOutput object containing extraction results
        """
        try:
            from onnxtr.io import DocumentFile

            self.preserve_layout = preserve_layout
            start_time = time.time()

            # Step 1: Validate image paths
            for image_path in image_paths:
                if not os.path.exists(image_path):
                    logger.error(f"Image file not found: {image_path}")
                    return None

            # Step 2: Perform OCR on all images
            docs = DocumentFile.from_images(image_paths)
            result = self.doctr_predictor(docs)

            if result is None:
                logger.warning(
                    "DocTR OCR failed, creating empty pages for vision correction fallback"
                )
                # Create empty pages with image paths for vision correction
                all_pages = [
                    Page(
                        page_number=i + 1,
                        original_content="",
                        corrected_content="",
                        image_path=img_path,
                    )
                    for i, img_path in enumerate(image_paths)
                ]
            else:
                ocr_json = result.export()
                json_data = self._numpy_to_python(
                    json.loads(ocr_json) if isinstance(ocr_json, str) else ocr_json
                )

                # Force garbage collection after OCR processing
                gc.collect()

                # Step 3: Process all pages using unified processor (eliminates ~40 lines of duplicate logic)
                all_pages = self._process_ocr_data(
                    json_data, image_paths, self.preserve_layout
                )

            # Force garbage collection after processing
            gc.collect()

            # Step 4: Apply vision correction if requested
            # NOTE: Vision correction moved to PDF parser - keeping this code for reference
            # if vision_correction:
            #     corrector = VisionCorrector(
            #         organization_schema=self.organization_schema,
            #         include_details=correction_details,
            #     )
            #     output = asyncio.run(
            #         corrector.correct_pages(
            #             pages=all_pages,
            #             file_name="multi_image_processing",
            #         )
            #     )
            #     logger.info("Vision correction completed")
            # else:

            # Always clear image paths and create output (vision correction now handled in PDF parser)
            for page in all_pages:
                page.image_path = ""
            output = ParserOutput(
                completion_time=time.time() - start_time,
                file_name="multi_image_processing",
                pages=all_pages,
            )

            # Calculate total completion time
            total_time = time.time() - start_time
            output.completion_time = total_time

            return output

        except Exception as e:
            logger.error(f"Error in image OCR extraction: {str(e)}")
            return None

    def perform_pdf_ocr(
        self,
        file_path: str,
        page_limit: int = None,
        preserve_layout: bool = False,
        # vision_correction: bool = False,
        correction_details: bool = False,
        page_mode: bool = False,
        temp_dir: Optional[str] = None,
        image_paths: Optional[List[str]] = None,
    ) -> Optional[ParserOutput]:
        """
        Perform text extraction using DocTR.

        Args:
            file_path: Path to the PDF file
            page_limit: Number of first pages to process
            preserve_layout: Whether to preserve the original layout
            vision_correction: Whether to perform vision-based correction
            correction_details: Whether to include correction details in the output
            page_mode: Whether to use image-based processing (True) or PDF-based batch processing (False)
        """
        try:
            start_time = time.time()

            # Get file info
            file_size_kb = os.path.getsize(file_path) / 1024
            with fitz.open(file_path) as doc:
                total_pages = len(doc)
            pages_to_process = (
                min(page_limit, total_pages) if page_limit else total_pages
            )

            logger.info(
                f"Starting OCR: file={os.path.basename(file_path)}, size={file_size_kb:.0f}KB, pages={pages_to_process}, mode={'image' if page_mode else 'batch'}, preserve_layout={str(preserve_layout).lower()}"
            )

            # Setup temp directory - use provided or create our own
            if temp_dir:
                self.temp_dir = temp_dir
                # logger.debug(f"Using external temp directory: {temp_dir}")
            elif not self.temp_dir:
                self._setup_temp_directory(file_path)

            image_paths = None
            requires_images = page_mode

            if requires_images:
                # Use pre-generated images or convert PDF to images
                if image_paths:
                    # logger.debug(f"Using pre-generated images: {len(image_paths)} files")
                    pass
                else:
                    # Convert PDF to images when vision correction or page mode is enabled
                    image_paths = self._pdf_to_images(file_path, page_limit=page_limit)
                    if not image_paths:
                        raise Exception("Failed to convert PDF to images")

                # logger.debug(f"PDF converted to {len(image_paths)} images")
            else:
                # logger.debug("Skipping PDF to image conversion (not required)")
                pass

            # Step 2: Route to appropriate processing method
            if page_mode:
                # Image-based processing: use core OCR processor
                # logger.debug("Using image-based processing")
                result = self.perform_image_ocr(
                    image_paths=image_paths,
                    preserve_layout=preserve_layout,
                    # vision_correction=vision_correction,
                    correction_details=correction_details,
                )
            else:
                # PDF-based batch processing: include image paths
                # logger.debug("Using PDF-based batch processing")
                result = self._process_pdf_in_batches(
                    file_path=file_path,
                    image_paths=image_paths,
                    page_limit=page_limit,
                    preserve_layout=preserve_layout,
                    # vision_correction=vision_correction,
                    correction_details=correction_details,
                )

            if result:
                elapsed_time = time.time() - start_time
                logger.info(
                    f"Completed OCR: file={os.path.basename(file_path)}, time={elapsed_time:.2f}s, pages={len(result.pages)}, mode={'image' if page_mode else 'batch'}"
                )

            return result

        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(
                f"OCR failed: file={os.path.basename(file_path)}, time={elapsed_time:.2f}s, error={str(e)}"
            )
            # Only cleanup if we created the temp directory
            if not temp_dir:
                self._cleanup_temp_directory()
            return None

    def format_ocr_output(self, result: ParserOutput) -> dict:
        """
        Format the OCR results into a structured dictionary.

        Args:
            result: ParserOutput object containing OCR results

        Returns:
            Dictionary containing formatted output with:
            - json_result: Combined block JSON
            - original_content: Combined original content
            - corrected_content: Combined corrected content
            - correction_details: Combined correction details
        """
        total_pages = len(result.pages)
        formatted_output = {
            "json_result": [],
            "original_content": [],
            "corrected_content": [],
            "correction_details": [],
        }

        # Process each page
        for page in result.pages:
            # Format page header
            header = f"{'=' * 10} Page {page.page_number} of {total_pages} {'=' * 10}"

            # Add to original content
            formatted_output["original_content"].extend(
                [header, page.original_content, "", ""]
            )

            # Add to corrected content if available
            content = (
                page.corrected_content
                if page.corrected_content
                else page.original_content
            )
            formatted_output["corrected_content"].extend([header, content, "", ""])

            # Add correction details if available
            if page.correction_details:
                formatted_output["correction_details"].extend(
                    [header, page.correction_details, "", ""]
                )

            # Add to JSON result if available
            if page.ocr_blocks:
                formatted_output["json_result"].append(page.ocr_blocks[0])

        for key in ["original_content", "corrected_content", "correction_details"]:
            # Filter out None values and join, or use empty string if the list itself is falsy
            formatted_output[key] = "\n".join(
                str(s) if s is not None else "" for s in formatted_output[key] or []
            )

        return formatted_output


if __name__ == "__main__":
    import sys

    # Simple test setup
    file_path = "./data/test.pdf"  # Update this path for your test file
    organization_schema = "test_org"

    # Create OCR parser instance
    ocr_parser = OCRParser(organization_schema)
    print(f"Created OCR parser for organization: {organization_schema}")

    # Perform OCR with default settings
    print(f"Processing file: {file_path}")
    result = ocr_parser.perform_pdf_ocr(
        file_path=file_path,
        preserve_layout=True,
        page_limit=5,  # Process only first 5 pages
        # vision_correction=False,  # Set to True if you want vision correction
        correction_details=False,
    )

    if result:
        # Format and display results
        formatted_output = ocr_parser.format_ocr_output(result)

        print(f"\n{'='*50}")
        print(f"Processing completed in {result.completion_time:.2f} seconds")
        print(f"Processed {len(result.pages)} pages from {os.path.basename(file_path)}")

        if result.input_tokens and result.output_tokens:
            print(
                f"Vision correction tokens - Input: {result.input_tokens}, Output: {result.output_tokens}"
            )

        print(f"\n{'='*50}")
        print("EXTRACTED TEXT:")
        print(f"{'='*50}")
        print(formatted_output["corrected_content"])

        # Optionally save to file
        output_file = f"{os.path.splitext(file_path)[0]}_ocr_output.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(formatted_output["corrected_content"])
        print(f"\nOutput saved to: {output_file}")

    else:
        print("OCR processing failed!")
        sys.exit(1)
