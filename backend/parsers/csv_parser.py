# Custom libraries
from logger import configure_logging

# Default libraries
from typing import Optional

# Installed libraries
import numpy as np
import pandas as pd

from schemas.parsed_document_schema import ParsedDocument

logger = configure_logging(__name__)


class CSVParser:
    """
    A class for parsing CSV content.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path

    def extract_csv_data(self) -> Optional[ParsedDocument]:
        try:
            logger.info("Converting CSV to plain text")
            df = pd.read_csv(self.file_path, encoding="utf-8")
            df = df.replace({pd.NA: "--", np.nan: "--"})
            df = df.astype(str)
            plain_text = df.to_markdown(index=False, tablefmt="plain")
            logger.info("Converted CSV to plain text successfully")
            return ParsedDocument(
                input_file=self.file_path,
                extracted_data=[plain_text],
            )

        except Exception as e:
            logger.error(f"An error occurred in parsing CSV to plain text: {e}")
            return None
