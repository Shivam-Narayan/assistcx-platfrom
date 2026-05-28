# Default libraries
import os
import gc
import time
import asyncio
import shutil
from typing import Optional

# Installed libraries
import fitz
import numpy as np
from PIL import Image
from dotenv import load_dotenv

# Custom libraries
from logger import configure_logging
from sqlalchemy.orm import Session

# Local modules
from .vision_parser import VisionParser
from schemas.parsed_document_schema import ParsedDocument

logger = configure_logging(__name__)

load_dotenv()


class PDFParser:
    """
    A class for parsing text content from PDF files, supporting both native and scanned PDFs.
    """

    # Default configuration constants
    MAX_PDF_PAGES = 50
    OCR_PAGE_LIMIT = None
    SPLIT_PDF_PAGES = False
    FIX_PAGE_ROTATION = True
    PRESERVE_PAGE_LAYOUT = True
    PAGE_MODE = False
    DATA_PARSING = False
    BLANK_PAGE_THRESHOLD = 99.8

    def __init__(
        self,
        file_path,
        organization_schema,
        db: Session = None,
        polling_config: Optional[dict] = None,
    ):
        """Initializes a new instance of the PDFParser class."""
        self.file_path = file_path
        self.organization_schema = organization_schema
        self.db = db
        self.polling_config = polling_config
        self.temp_dir = None

    def _setup_temp_directory(self, file_path: str):
        """Create temp directory for PDF processing workflow"""
        if not self.temp_dir:
            base_name = os.path.basename(file_path).replace(" ", "_").replace(".", "_")
            self.temp_dir = f"/data/temp/{base_name}_pdf_processing"
            os.makedirs(self.temp_dir, exist_ok=True)
        return self.temp_dir

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

    def _get_mailbox_configs(self):
        """Get configuration values with defaults."""
        if self.polling_config:
            return {
                "max_pdf_pages": self.polling_config.get(
                    "max_pdf_pages", self.MAX_PDF_PAGES
                ),
                "ocr_page_limit": self.polling_config.get(
                    "ocr_page_limit", self.OCR_PAGE_LIMIT
                ),
                "split_pdf_pages": self.polling_config.get(
                    "split_pdf_pages", self.SPLIT_PDF_PAGES
                ),
                "fix_page_rotation": self.polling_config.get(
                    "fix_page_rotation", self.FIX_PAGE_ROTATION
                ),
                "preserve_page_layout": self.polling_config.get(
                    "preserve_page_layout", self.PRESERVE_PAGE_LAYOUT
                ),
                "page_mode": self.polling_config.get("page_mode", self.PAGE_MODE),
                "data_parsing": self.polling_config.get(
                    "data_parsing", self.DATA_PARSING
                ),
            }
        else:
            return {
                "max_pdf_pages": self.MAX_PDF_PAGES,
                "ocr_page_limit": self.OCR_PAGE_LIMIT,
                "split_pdf_pages": self.SPLIT_PDF_PAGES,
                "fix_page_rotation": self.FIX_PAGE_ROTATION,
                "preserve_page_layout": self.PRESERVE_PAGE_LAYOUT,
                "page_mode": self.PAGE_MODE,
                "data_parsing": self.DATA_PARSING,
            }

    def is_page_blank(self, page, dpi=300):
        """Detect blank pages using pixel count method with proper cleanup.

        Returns:
            tuple: (is_blank: bool, white_percentage: float)
        """
        pix = None
        img = None
        gray_img = None

        try:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            gray_img = img.convert("L")

            from PIL import ImageFilter

            gray_img = gray_img.filter(ImageFilter.MedianFilter(size=3))

            gray_array = np.array(gray_img)

            total_pixels = gray_array.size
            white_pixels = np.sum(gray_array > 250)
            white_percentage = (white_pixels / total_pixels) * 100

            rounded_percentage = round(white_percentage, 1)
            is_blank = rounded_percentage >= self.BLANK_PAGE_THRESHOLD

            return is_blank, white_percentage

        except Exception as e:
            logger.error(f"Error in blank page detection: {e}")
            return False, 0.0

        finally:
            for obj in [gray_img, img]:
                if obj is not None and hasattr(obj, "close"):
                    obj.close()
            pix = None
            gc.collect()

    def split_pdf_file(self, input_path):
        """
        Split the PDF into multiple files at blank pages, excluding the blank pages.
        If no blank pages are found or if any error occurs, return the original file path.
        """

        try:
            with fitz.open(input_path) as doc:
                dir_name, base_name = os.path.split(input_path)
                base_name = base_name.rsplit(".", 1)[0]

                output_files = []
                split_pages = []
                non_blank_pages = []
                blank_pages = []

                if doc.is_closed or doc.page_count == 0:
                    logger.error(
                        f"Invalid or empty PDF document: {os.path.basename(input_path)}"
                    )
                    return [input_path]

                all_page_info = []
                for page_num, page in enumerate(doc):
                    is_blank, white_percentage = self.is_page_blank(page)
                    page_number = page_num + 1
                    status = "BLANK" if is_blank else "CONTENT"
                    all_page_info.append(
                        f"{page_number}({status},{white_percentage:.1f}%)"
                    )

                    if is_blank:
                        blank_pages.append(page_number)
                        if non_blank_pages:
                            split_pages.append(
                                (non_blank_pages[0], non_blank_pages[-1])
                            )
                            non_blank_pages = []
                    else:
                        non_blank_pages.append(page_num)

                if non_blank_pages:
                    split_pages.append((non_blank_pages[0], non_blank_pages[-1]))

                pages_info = ", ".join(all_page_info)
                logger.info(
                    f"Blank page analysis: total={len(all_page_info)}, blank={len(blank_pages)}, pages=[{pages_info}]"
                )

                total_splits = len(split_pages)

                if total_splits == 1:
                    start_page, end_page = split_pages[0]
                    if start_page == 0 and end_page == doc.page_count - 1:
                        logger.info(
                            f"No blank pages found in PDF: {os.path.basename(input_path)}"
                        )
                        return [input_path]

                for split_index, (start_page, end_page) in enumerate(split_pages):
                    new_doc = None
                    try:
                        new_doc = fitz.open()
                        new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)

                        output_path = os.path.join(
                            dir_name,
                            f"{base_name}-{split_index + 1}_of_{total_splits}.pdf",
                        )
                        new_doc.save(output_path)
                        output_files.append(output_path)

                    except Exception as e:
                        logger.error(f"Error creating split {split_index + 1}: {e}")
                        continue
                    finally:
                        if new_doc:
                            new_doc.close()

                if not output_files:
                    return [input_path]

                return output_files

        except Exception as e:
            logger.error(f"Error while splitting PDF {input_path}: {e}")
            return [input_path]

    def strip_pdf_file(self, input_pdf_path, max_pages, output_pdf_path=None):
        """Strip longer PDF file to the specified maximum length."""
        with fitz.open(input_pdf_path) as doc:
            num_pages = len(doc)

            if num_pages > max_pages:
                doc.delete_pages(from_page=max_pages, to_page=num_pages - 1)

                if not output_pdf_path:
                    temp_output_path = f"{input_pdf_path}_temp.pdf"
                    doc.save(temp_output_path)
                    os.replace(temp_output_path, input_pdf_path)
                    output_pdf_path = input_pdf_path
                    logger.debug(
                        f"PDF stripped to {max_pages} pages: {os.path.basename(input_pdf_path)}"
                    )
                else:
                    doc.save(output_pdf_path)
                    logger.debug(
                        f"PDF stripped to {max_pages} pages: {os.path.basename(output_pdf_path)}"
                    )
            else:
                if not output_pdf_path:
                    output_pdf_path = input_pdf_path

        return output_pdf_path

    async def parse_pdf_with_vision(self) -> Optional[ParsedDocument]:
        """Extracts text content from the PDF using vision parser."""
        pdf_start_time = time.time()

        try:
            config = self._get_mailbox_configs()
            max_pdf_pages = config["max_pdf_pages"]
            ocr_page_limit = config["ocr_page_limit"]
            split_pdf_pages = config["split_pdf_pages"]
            preserve_page_layout = config["preserve_page_layout"]

            file_size = os.path.getsize(self.file_path)
            file_size_kb = file_size / 1024
            with fitz.open(self.file_path) as doc:
                page_count = len(doc)

            logger.info(
                f"Processing PDF: file={os.path.basename(self.file_path)}, size={file_size_kb:.0f}KB, pages={page_count}, config={{ocr_limit:{ocr_page_limit if ocr_page_limit else 'None'}, max_pages:{max_pdf_pages}, preserve_layout:{str(preserve_page_layout).lower()}}}"
            )

            self._setup_temp_directory(self.file_path)

            stripped_file = self.strip_pdf_file(self.file_path, max_pdf_pages)

            vision_start = time.time()
            vision_parser = VisionParser(
                organization_schema=self.organization_schema,
                db=self.db,
                mode="parsing",
            )
            result = await vision_parser.parse_file(
                file_path=stripped_file, page_limit=ocr_page_limit
            )
            vision_time = time.time() - vision_start

            del vision_parser
            gc.collect()

            total_elapsed = time.time() - pdf_start_time
            overhead = total_elapsed - vision_time

            logger.info(
                f"Completed PDF processing: file={os.path.basename(self.file_path)}, total_time={total_elapsed:.2f}s, breakdown={{vision:{vision_time:.2f}s, overhead:{overhead:.2f}s}}"
            )

            if result:
                return ParsedDocument(
                    input_file=self.file_path,
                    extracted_data=result.extracted_data,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
            return None

        except Exception as e:
            logger.error(f"Error occurred during PDF extraction: {e}")
            return None

        finally:
            self._cleanup_temp_directory()

    def extract_pdf_data(self) -> Optional[ParsedDocument]:
        """Extract PDF data using vision parsing based on configuration."""
        config = self._get_mailbox_configs()
        data_parsing = config["data_parsing"]

        if data_parsing:
            return asyncio.run(self.parse_pdf_with_vision())
        else:
            return ParsedDocument(
                input_file=self.file_path,
                extracted_data=[],
            )
