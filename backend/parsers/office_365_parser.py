# Custom libraries
from logger import configure_logging

# Default libraries
import os

# Installed libraries
from docling.document_converter import DocumentConverter

from schemas.parsed_document_schema import ParsedDocument

logger = configure_logging(__name__)


class Office365Parser:
    """
    A class for parsing Microsoft Office content (.docx, .pptx, .xlsx).
    Uses docling to dynamically handle all three file types.
    """

    SUPPORTED_EXTENSIONS = {".docx", ".pptx", ".xlsx"}

    FILE_TYPE_NAMES = {
        ".docx": "Word",
        ".pptx": "PowerPoint",
        ".xlsx": "Excel",
    }

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_extension = os.path.splitext(file_path)[1].lower()

        if self.file_extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension: {self.file_extension}. "
                f"Supported extensions: {self.SUPPORTED_EXTENSIONS}"
            )

    def extract_office_data(self) -> ParsedDocument:
        """
        Extracts data from Office files (.docx, .pptx, .xlsx) using docling.

        Returns:
            ParsedDocument with extracted text content.
        """
        try:
            file_type_name = self.FILE_TYPE_NAMES.get(
                self.file_extension, "Office document"
            )
            logger.info(f"Converting {file_type_name} to plain text")

            converter = DocumentConverter()
            result = converter.convert(self.file_path)
            plain_text = result.document.export_to_markdown()

            if not plain_text or not plain_text.strip():
                logger.warning(
                    f"Converted {file_type_name} file but extracted content is empty"
                )
                plain_text = f"(No extractable content from {file_type_name} file)"

            logger.info(f"Converted {file_type_name} to plain text successfully")
            return ParsedDocument(
                input_file=self.file_path,
                extracted_data=[plain_text],
            )

        except Exception as e:
            file_type_name = self.FILE_TYPE_NAMES.get(
                self.file_extension, "Office document"
            )
            logger.error(
                f"An error occurred in parsing {file_type_name} to plain text: {e}"
            )
            return ParsedDocument(
                input_file=self.file_path,
                extracted_data=[f"Error parsing {file_type_name} file: {str(e)}"],
            )
