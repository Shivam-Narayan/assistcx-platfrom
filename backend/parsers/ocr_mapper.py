import json
import re
from difflib import SequenceMatcher
from logger import configure_logging
from typing_extensions import deprecated

logger = configure_logging(__name__)


@deprecated("Use VisionParser instead.")
class OCRBlockMapper:
    def __init__(self):
        self.ocr_pages = None
        self._cached_blocks = []

    def prepare_text(self, text):
        """Return sanitized text and token tuple for matching."""
        if text is None:
            return "", tuple()
        cleaned = re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()
        tokens = tuple(token for token in cleaned.split() if token)
        return cleaned, tokens

    def _geometry_area(self, geometry):
        """Approximate area of a geometry box for tie-breaking."""
        if (
            isinstance(geometry, list)
            and len(geometry) == 2
            and all(
                isinstance(point, (list, tuple)) and len(point) == 2
                for point in geometry
            )
        ):
            try:
                (x1, y1), (x2, y2) = geometry
                return abs(float(x2) - float(x1)) * abs(float(y2) - float(y1))
            except (TypeError, ValueError):
                return None
        return None

    def _prepare_block_cache(self):
        """Pre-compute normalized and sanitized forms of OCR blocks for matching."""
        self._cached_blocks = []
        for page in self.ocr_pages or []:
            page_idx = page.get("page_idx")
            for block in page.get("blocks", []):
                text = block.get("text", "")
                sanitized, tokens = self.prepare_text(text)
                self._cached_blocks.append(
                    {
                        "page_idx": page_idx,
                        "geometry": block.get("geometry"),
                        "sanitized": sanitized,
                        "tokens": set(tokens),
                        "token_count": len(tokens),
                        "area": self._geometry_area(block.get("geometry")),
                    }
                )

    def find_block_geometry(self, original_text):
        """Find the geometry and page index of a block containing the original text."""
        if not original_text or not self._cached_blocks:
            return None, None

        sanitized_original, original_tokens_tuple = self.prepare_text(original_text)
        original_tokens = set(original_tokens_tuple)
        original_token_count = len(original_tokens_tuple)

        best_score = None
        best_match = None

        for block in self._cached_blocks:
            block_tokens = block["tokens"]

            overlap_tokens = (
                original_tokens & block_tokens if original_tokens else set()
            )
            overlap_count = len(overlap_tokens)

            coverage = (
                overlap_count / original_token_count if original_token_count else 0.0
            )
            block_coverage = (
                overlap_count / block["token_count"] if block["token_count"] else 0.0
            )

            fuzzy_score = 0.0
            if (
                overlap_count == 0
                and len(sanitized_original) >= 5
                and block["sanitized"]
            ):
                fuzzy_score = SequenceMatcher(
                    None, sanitized_original, block["sanitized"]
                ).ratio()

            if overlap_count == 0 and fuzzy_score < 0.85:
                continue

            candidate_score = (
                overlap_count,
                coverage,
                block_coverage,
                fuzzy_score,
                block["area"] if block["area"] is not None else 0.0,
            )

            if best_score is None or candidate_score > best_score:
                best_score = candidate_score
                best_match = (
                    block["page_idx"],
                    block["geometry"],
                    overlap_count,
                    coverage,
                    fuzzy_score,
                )

        if not best_match:
            return None, None

        page_idx, geometry, overlap_count, coverage, fuzzy_score = best_match

        meets_threshold = (
            overlap_count >= (2 if original_token_count >= 2 else 1)
            or coverage >= 0.6
            or fuzzy_score >= (0.9 if original_token_count >= 2 else 0.95)
        )

        if meets_threshold:
            return page_idx, geometry

        return None, None

    def process_meta_field(self, field):
        """Add geometry and page_idx to a meta__fields entry."""
        if not isinstance(field, dict) or "original_text" not in field:
            return field

        original_text = field.get("original_text", "")
        page_idx, geometry = self.find_block_geometry(original_text)
        field["geometry"] = geometry if geometry else []
        field["page_idx"] = page_idx
        return field

    def apply_ocr_mapping(self, ai_data, ocr_pages):
        """Update meta__fields in ai_data with geometry and page_idx."""
        self.ocr_pages = ocr_pages or []
        self._prepare_block_cache()

        def process_item(item):
            # if isinstance(item, dict) and "meta__fields" in item:
            if (
                isinstance(item, dict)
                and "meta__fields" in item
                and item["meta__fields"] is not None
            ):
                item["meta__fields"] = {
                    k: self.process_meta_field(v)
                    for k, v in item["meta__fields"].items()
                }
            return item

        if isinstance(ai_data, list):
            return [process_item(item) for item in ai_data]
        return process_item(ai_data)


def test_mapper():
    """Test function to demonstrate usage."""
    ai_data = [
        {
            "document_type": "STANDARD INVOICE",
            "invoice_number": "9164384771",
            "invoice_date": "08/29/2025",
            "purchase_order": "47040479",
            "gr_number": "5000478740",
            "total_amount": "2,206.05",
            "payment_terms": "NET 30",
            "line_items": [
                {
                    "item_description": "NI BLK NITROGEN INDUSTRIAL BULK",
                    "quantity": "630,300",
                    "unit_price": "0.35",
                    "amount": "2,206.05",
                    "currency": "USD",
                }
            ],
            "meta__fields": {
                "invoice_number": {
                    "original_text": "INVOICE NO.    9164384771",
                    "confidence_score": 100,
                },
                "invoice_date": {
                    "original_text": "INVOICE DATE    08/29/2025",
                    "confidence_score": 100,
                },
                "purchase_order": {
                    "original_text": "SAP PO#: 47040479",
                    "confidence_score": 100,
                },
                "gr_number": {
                    "original_text": "SAP GR#: 5000478740,",
                    "confidence_score": 100,
                },
                "total_amount": {
                    "original_text": "PAY THIS AMOUNT $ 2,206.05",
                    "confidence_score": 100,
                },
                "payment_terms": {
                    "original_text": "PAYMENT TERMS    NET 30",
                    "confidence_score": 100,
                },
                "line_items[0].item_description": {
                    "original_text": "NI BLK NITROGEN INDUSTRIAL BULK (Vol: 630300 FT3) ALTO Qty 630300 SCF",
                    "confidence_score": 95,
                },
                "line_items[0].quantity": {
                    "original_text": "QTY    630, 300 SCF",
                    "confidence_score": 95,
                },
                "line_items[0].unit_price": {
                    "original_text": "UNIT PRICE   0.35",
                    "confidence_score": 95,
                },
            },
        }
    ]

    ocr_pages = [
        {
            "page_idx": 0,
            "blocks": [
                {
                    "text": "Airgas. PO Box 1152\nan Air Liquide company Tulsa, OK 74101",
                    "geometry": [[0.03, 0.03], [0.34, 0.15]],
                },
                {
                    "text": "INVOICE NO. INVOICE DATE\n9164384771 08/29/2025",
                    "geometry": [[0.21, 0.39], [0.53, 0.46]],
                },
                {
                    "text": "INVOICE DATE",
                    "geometry": [[0.45, 0.05], [0.50, 0.06]],
                },
                {
                    "text": "INVOICE NO.",
                    "geometry": [[0.63, 0.05], [0.69, 0.06]],
                },
                {
                    "text": "Invoice Submission\nSAP PO# 47040479\nSAP GR# 5000478740,",
                    "geometry": [[0.10, 0.68], [0.29, 0.76]],
                },
                {
                    "text": "PAYMENT TERMS\nNET 30",
                    "geometry": [[0.65, 0.39], [0.80, 0.48]],
                },
                {
                    "text": "PAY THIS AMOUNT\n$ 2,206.05",
                    "geometry": [[0.85, 0.05], [0.92, 0.08]],
                },
                {
                    "text": "ORDERED BY\nQTY\nSHIP'D\n630, 300 SCF",
                    "geometry": [[0.36, 0.42], [0.47, 0.48]],
                },
                {
                    "text": "UNIT PRICE UOM\n0.35 CCF",
                    "geometry": [[0.65, 0.44], [0.80, 0.48]],
                },
                {
                    "text": "ORDERI NO.\n1142259267\nDELIVERY NO.I\nDESCRIPTION.\n8156066442 NI BLK\nNITROGEN INDUSTRIAL BULK (Vol: 630300 FT3)\nALTO Qty 630300 SCF",
                    "geometry": [[0.05, 0.39], [0.49, 0.53]],
                },
                {
                    "text": "ORDER DATE\n08/26/2025\nAMOUNT\n2,206.05",
                    "geometry": [[0.83, 0.42], [0.94, 0.48]],
                },
                {
                    "text": "2,206.05",
                    "geometry": [[0.84, 0.54], [0.92, 0.55]],
                },
                {
                    "text": "34408611916438477100002206053",
                    "geometry": [[0.53, 0.31], [0.86, 0.32]],
                },
            ],
        }
    ]

    mapper = OCRBlockMapper()
    result = mapper.apply_ocr_mapping(ai_data, ocr_pages)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    test_mapper()
