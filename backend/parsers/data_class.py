from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Page:
    """Represents a processed page with its content and metadata"""

    page_number: int
    original_content: str
    corrected_content: Optional[str] = None
    correction_details: Optional[str] = None
    ocr_json: dict = None
    ocr_blocks: dict = None
    ocr_lines: dict = None
    image_path: str = ""


@dataclass
class ParserPage:
    """Represents a parsed page with its content and metadata"""

    page_number: int
    parsed_content: str
    image_path: str = ""


@dataclass
class ParserOutput:
    """Represents the final output of the OCR parsing process"""

    completion_time: float
    file_name: str
    pages: List[Page]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
