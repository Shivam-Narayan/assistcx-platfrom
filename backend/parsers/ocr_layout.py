import json
import argparse
from typing import List, Dict, Tuple
from dataclasses import dataclass
from collections import defaultdict
from statistics import mean
from typing_extensions import deprecated


@dataclass
class TextLine:
    text: str
    x: float
    y: float
    width: float
    height: float


@deprecated("Use VisionParser instead.")
class TextLayoutGenerator:
    def __init__(self, max_width: int = 120, max_height: int = 60):
        """
        Initialize the TextLayoutGenerator with configuration parameters.

        Args:
            max_width: Maximum width of the output in characters
            max_height: Maximum height of the output in lines
        """
        self.max_width = max_width
        self.max_height = max_height
        self.row_tolerance = 0.01
        self.gap_threshold = 0.02
        self.density_threshold = 60
        self.density_gap_threshold = 0.03

    def normalize_coordinates(
        self, geometry: List[List[float]]
    ) -> Tuple[float, float, float, float]:
        """
        Convert geometry points to normalized x, y, width, height.
        """
        x_coords = [point[0] for point in geometry]
        y_coords = [point[1] for point in geometry]

        x = min(x_coords)
        y = min(y_coords)
        width = max(x_coords) - x
        height = max(y_coords) - y

        return x, y, width, height

    def is_dense_text_rows(self, rows: List[List[TextLine]]) -> bool:
        """
        Determines if rows represent dense text based on number of rows and their distribution.
        """
        if len(rows) < self.density_threshold:
            return False

        gaps = []
        for i in range(len(rows) - 1):
            current_y = rows[i][0].y
            next_y = rows[i + 1][0].y
            gap = next_y - current_y
            gaps.append(gap)

        if gaps:
            avg_gap = mean(gaps)
            return avg_gap < self.density_gap_threshold

        return False

    def group_lines_by_row(self, lines: List[TextLine]) -> List[List[TextLine]]:
        """
        Group lines that belong to the same row based on vertical position.
        """
        sorted_lines = sorted(lines, key=lambda x: x.y)
        rows = []
        current_row = []
        current_y = None

        for line in sorted_lines:
            if current_y is None:
                current_row = [line]
                current_y = line.y
            elif abs(line.y - current_y) <= self.row_tolerance:
                current_row.append(line)
            else:
                rows.append(sorted(current_row, key=lambda x: x.x))
                current_row = [line]
                current_y = line.y

        if current_row:
            rows.append(sorted(current_row, key=lambda x: x.x))

        return rows

    def format_row(self, row: List[TextLine]) -> str:
        """
        Format a row of text lines maintaining relative spacing while preserving long text.
        """
        if not row:
            return ""

        # Sort by x position first to handle overlaps
        positions = []
        total_width = 0

        for line in row:
            pos = int(line.x * self.max_width)
            # Calculate approximate text width in characters
            text_width = len(line.text)
            total_width = max(total_width, pos + text_width)
            positions.append((pos, line.text))

        # Adjust max_width if content requires more space
        effective_width = max(self.max_width, total_width + 5)  # Add small buffer

        # Sort by position
        positions.sort()
        output = [" " * effective_width]

        for pos, text in positions:
            # If position would push text beyond even the extended width,
            # adjust position to ensure text fits
            if pos + len(text) > effective_width:
                pos = max(0, effective_width - len(text))

            # Write the text at the position
            output[0] = output[0][:pos] + text + output[0][pos + len(text) :]

        return output[0].rstrip()

    def format_dense_text(self, lines: List[Dict], max_words_per_line: int = 20) -> str:
        """
        Format dense text with word wrapping and appropriate vertical spacing.
        """
        if not lines:
            return ""

        def wrap_text(text: str) -> List[str]:
            """Helper function to wrap text at word boundaries"""
            words = text.split()
            wrapped_lines = []
            current_line = []

            for word in words:
                if len(current_line) < max_words_per_line:
                    current_line.append(word)
                else:
                    wrapped_lines.append(" ".join(current_line))
                    current_line = [word]

            if current_line:
                wrapped_lines.append(" ".join(current_line))

            return wrapped_lines

        # Initialize output with first line
        first_line_wrapped = wrap_text(lines[0]["text"])
        output_parts = ["\n".join(first_line_wrapped)]
        prev_y = lines[0]["geometry"][0][1]  # Y-coordinate of first line

        for line in lines[1:]:
            current_y = line["geometry"][0][1]
            vertical_gap = current_y - prev_y
            wrapped_lines = wrap_text(line["text"])

            # Determine line breaks based on vertical gap
            if vertical_gap > self.gap_threshold * 2:
                # Large gap - likely a new section/heading
                output_parts.append("\n\n" + "\n".join(wrapped_lines))
            elif vertical_gap > self.gap_threshold:
                # Medium gap - likely a new paragraph
                output_parts.append("\n\n" + "\n".join(wrapped_lines))
            else:
                # Small gap - continuation of paragraph
                output_parts.append("\n" + "\n".join(wrapped_lines))

            prev_y = current_y

        return "".join(output_parts)

    def convert_to_text_lines(self, page: Dict) -> List[TextLine]:
        """
        Convert JSON lines to TextLine objects.
        """
        text_lines = []
        for line in page["lines"]:
            x, y, width, height = self.normalize_coordinates(line["geometry"])
            text_lines.append(
                TextLine(text=line["text"], x=x, y=y, width=width, height=height)
            )
        return text_lines

    def find_content_left_margin(self, formatted_lines: List[str]) -> int:
        """
        Find the common left margin (number of leading spaces) across all non-empty lines.
        """
        if not formatted_lines:
            return 0

        # Get leading spaces for all non-empty lines
        margins = []
        for line in formatted_lines:
            if line.strip():  # Only consider non-empty lines
                leading_spaces = len(line) - len(line.lstrip())
                margins.append(leading_spaces)

        # Return the minimum common margin, or 0 if no valid margins
        return min(margins) if margins else 0

    def shift_content_left(self, formatted_text: str) -> str:
        """
        Shift page content to the left while preserving relative spacing and header alignment.
        """
        # Split into lines
        lines = formatted_text.split("\n")

        # Separate header (first two lines) from content
        header_lines = lines[:2] if len(lines) >= 2 else lines
        content_lines = lines[2:] if len(lines) >= 2 else []

        # Find the common left margin in content
        margin = self.find_content_left_margin(content_lines)

        # Shift content lines left by removing common margin
        shifted_content = []
        for line in content_lines:
            if line.strip():  # For non-empty lines, remove margin
                shifted_content.append(line[margin:])
            else:  # Preserve empty lines
                shifted_content.append(line)

        # Combine header and shifted content
        result = header_lines + shifted_content
        return "\n".join(result)

    def generate_layout(self, json_data: str) -> str:
        """
        Generate text layout from OCR JSON data.
        """
        if isinstance(json_data, str):
            data = json.loads(json_data)
        else:
            data = json_data

        output_text = ""

        for page_idx, page in enumerate(data, 1):
            # header = f"{'=' * 10} Page {page_idx} of {len(data)} {'=' * 10}"
            # page_text = header + "\n\n"
            page_text = ""

            text_lines = self.convert_to_text_lines(page)
            rows = self.group_lines_by_row(text_lines)

            if self.is_dense_text_rows(rows):
                formatted_text = self.format_dense_text(page["lines"])
                page_text += formatted_text
            else:
                formatted_rows = []
                for row in rows:
                    formatted_row = self.format_row(row)
                    if formatted_row:
                        formatted_rows.append(formatted_row)
                page_text += "\n".join(formatted_rows)

            # Shift content left while preserving header
            page_text = self.shift_content_left(page_text)
            output_text += page_text + "\n\n"

        return output_text.rstrip()


# def main():
#     """
#     Example usage of the TextLayoutGenerator.
#     """
#     # Load input data
#     input_path = "./output/po-5-lines.json"
#     with open(input_path, "r") as f:
#         input_data = json.load(f)

#     # Create generator instance and generate layout
#     generator = TextLayoutGenerator()
#     text_layout = generator.generate_layout(input_data)

#     # Save to file
#     output_path = "document_layout.txt"
#     with open(output_path, "w", encoding="utf-8") as f:
#         f.write(text_layout)


# if __name__ == "__main__":
#     main()
