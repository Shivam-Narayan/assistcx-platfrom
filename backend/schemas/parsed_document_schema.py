from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ParsedDocument:
    """Standardized return type for all file parsers (PDF, CSV, Office, etc.)."""

    input_file: str
    extracted_data: List[str] = field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
