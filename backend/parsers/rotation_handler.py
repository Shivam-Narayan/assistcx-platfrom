# Standard library imports
import io
import os
import gc
import sys
import time
from typing import Generator, Optional

# Third-party imports
import cv2
import img2pdf
import numpy as np
import pytesseract
from pytesseract import TesseractError
from deskew import determine_skew
from pdf2image import convert_from_path
from pdf2image.exceptions import PDFPageCountError
from PIL import ExifTags, Image, ImageEnhance

# Local imports (assuming a logger module exists)
from logger import configure_logging

logger = configure_logging(__name__)


class RotationHandler:
    """Handles rotation correction for images and PDFs with resource optimization.

    Designed to process files sequentially in-memory for speed while minimizing resource
    usage in Docker environments. Supports page-by-page PDF processing and detailed logging.

    Configuration:
        Adjust the class constants below to optimize for your specific environment:
        - PDF_DPI: Higher DPI for better quality but more memory usage
        - CONFIDENCE_THRESHOLD: Lower for more aggressive rotation, higher for conservative
    """

    # Constants for image and PDF processing
    PDF_DPI = 200  # Higher DPI for better orientation detection
    TEXT_SHARPEN_FACTOR = 1.3  # Sharpening factor for text enhancement
    TEXT_CONTRAST_FACTOR = 1.2  # Contrast enhancement factor for text
    TEXT_BRIGHTNESS_BOOST = 1.02  # Brightness boost for text clarity
    DEFAULT_MIN_WIDTH = 1200  # Minimum image width in pixels
    DEFAULT_MAX_WIDTH = 1500  # Maximum image width in pixels
    DEFAULT_PADDING = 50  # Padding around content after cropping
    JPEG_QUALITY = 75  # JPEG quality for saving images

    # Constants for resource management
    BLANK_IMAGE_THRESHOLD = 0.3  # Threshold for blank image detection (percentage)
    SKEW_DETECTION_THRESHOLD = 0.05  # Minimum skew angle threshold for correction
    CONFIDENCE_THRESHOLD = 1.5  # Minimum confidence score for Tesseract OSD

    def __init__(self):
        """Initialize the RotationHandler."""
        pass

    def _fix_exif_rotation(self, pil_image: Image.Image) -> Image.Image:
        """Correct image orientation based on EXIF data.

        Args:
            pil_image (Image.Image): Input image.

        Returns:
            Image.Image: Image with corrected orientation.
        """
        try:
            exif = pil_image._getexif()
            if exif:
                exif = {
                    ExifTags.TAGS[k]: v for k, v in exif.items() if k in ExifTags.TAGS
                }
                orientation = exif.get("Orientation", 1)
                logger.info(f"Detected EXIF orientation: {orientation}")
                if orientation == 3:
                    return pil_image.rotate(180, expand=True)
                elif orientation == 6:
                    return pil_image.rotate(270, expand=True)
                elif orientation == 8:
                    return pil_image.rotate(90, expand=True)
        except (AttributeError, KeyError, IndexError):
            # logger.debug("No valid EXIF data found for orientation correction")
            pass
        return pil_image

    def _crop_whitespace(
        self, image: Image.Image, padding: int = DEFAULT_PADDING
    ) -> Image.Image:
        """Crop whitespace around the image content with improved content detection.

        Args:
            image (Image.Image): Input image.
            padding (int): Padding to add around the detected content.

        Returns:
            Image.Image: Cropped image with padding.
        """
        # Convert to grayscale and enhance contrast
        gray_img = ImageEnhance.Contrast(image.convert("L")).enhance(1.5)
        gray_array = np.array(gray_img)

        # Apply adaptive thresholding to detect content
        thresh = cv2.adaptiveThreshold(
            gray_array,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            21,
            5,
        )  # Increased blockSize and C

        # Find contours to determine content boundaries
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            # logger.debug("No contours detected, returning original image")
            return image

        # Compute bounding box from all contours
        x_min, y_min, x_max, y_max = image.width, image.height, 0, 0
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            x_min = min(x_min, x)
            y_min = min(y_min, y)
            x_max = max(x_max, x + w)
            y_max = max(y_max, y + h)

        # Apply padding and ensure bounds are within image dimensions
        left = max(0, x_min - padding)
        top = max(0, y_min - padding)
        right = min(image.width, x_max + padding)
        bottom = min(image.height, y_max + padding)

        # Log the detected content area
        # logger.debug(f"Detected content area: ({x_min}, {y_min}, {x_max}, {y_max})")
        # logger.info(f"Cropping image to bbox: ({left}, {top}, {right}, {bottom})")

        # Crop the image
        cropped = image.crop((left, top, right, bottom))
        if cropped.size == (0, 0):
            logger.warning("Cropping resulted in empty image, returning original")
            return image

        return cropped

    def _resize_image(
        self,
        image: Image.Image,
        min_width: int = DEFAULT_MIN_WIDTH,
        max_width: int = DEFAULT_MAX_WIDTH,
    ) -> Image.Image:
        """Resize the image to meet width constraints while preserving aspect ratio.

        Args:
            image (Image.Image): Input image.
            min_width (int): Minimum width in pixels.
            max_width (int): Maximum width in pixels.

        Returns:
            Image.Image: Resized image.
        """
        width, height = image.size
        aspect_ratio = width / height
        new_width = width
        if min_width > 0 and width < min_width:
            new_width = min_width
        if max_width > 0 and new_width > max_width:
            new_width = max_width
        if new_width != width:
            new_height = int(new_width / aspect_ratio)
            scale_factor = new_width / width
            if scale_factor > 1.5 or scale_factor < 0.5:
                intermediate_w = width + (new_width - width) // 2
                intermediate_h = height + (new_height - height) // 2
                image = image.resize((intermediate_w, intermediate_h), Image.BOX)
                # logger.debug(
                #     f"Intermediate resize to: {intermediate_w}x{intermediate_h}"
                # )
            image = image.resize((new_width, new_height), Image.LANCZOS)
            # logger.debug(f"Resized image to: {new_width}x{new_height}")
        return image

    def _enhance_image(self, image: Image.Image) -> Image.Image:
        """Enhance the image for better text clarity.

        Applies sharpening, contrast enhancement, brightness adjustment, noise reduction,
        and adaptive processing based on image statistics.

        Args:
            image (Image.Image): Input image.

        Returns:
            Image.Image: Enhanced image.
        """
        # First sharpen for text clarity
        enhanced = ImageEnhance.Sharpness(image).enhance(self.TEXT_SHARPEN_FACTOR)

        # Apply contrast enhancement
        enhanced = ImageEnhance.Contrast(enhanced).enhance(self.TEXT_CONTRAST_FACTOR)

        # Apply brightness enhancement
        enhanced = ImageEnhance.Brightness(enhanced).enhance(self.TEXT_BRIGHTNESS_BOOST)

        # Convert to OpenCV for advanced processing
        cv_image = cv2.cvtColor(np.array(enhanced), cv2.COLOR_RGB2BGR)
        gray = (
            cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
            if len(cv_image.shape) == 3
            else cv_image
        )

        # Better denoising with optimal parameters
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # Get mean and std for adaptive processing
        mean_val, std_val = np.mean(denoised), np.std(denoised)

        # Apply CLAHE for better text contrast - critical for OCR
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        denoised = clahe.apply(denoised)

        # Optimize for text content
        if 30 < mean_val < 220:
            # Better adaptive thresholding parameters
            binary = cv2.adaptiveThreshold(
                denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 13, 8
            )
            # Morphological operations to clean up text
            kernel = np.ones((2, 2), np.uint8)
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            binary = cv2.medianBlur(binary, 3)

            enhanced_text = Image.fromarray(binary)
            # Blend with original for better OCR results
            alpha = 0.7  # Increased from 0.6 for stronger text enhancement
            final_enhanced = Image.blend(
                enhanced,
                (
                    enhanced_text.convert("RGB")
                    if len(cv_image.shape) == 3
                    else enhanced_text
                ),
                alpha,
            )

            # Clean up intermediate image
            enhanced_text.close()

            return final_enhanced

        return enhanced

    def _rotate_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        """Rotate the image by the given angle with a white background.

        Args:
            image (np.ndarray): Input image in BGR format.
            angle (float): Rotation angle in degrees.

        Returns:
            np.ndarray: Rotated image.
        """
        h, w = image.shape[:2]
        center = (w / 2, h / 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        abs_cos, abs_sin = abs(rotation_matrix[0, 0]), abs(rotation_matrix[0, 1])
        new_w, new_h = int(h * abs_sin + w * abs_cos), int(h * abs_cos + w * abs_sin)
        rotation_matrix[0, 2] += (new_w / 2) - center[0]
        rotation_matrix[1, 2] += (new_h / 2) - center[1]
        rotated_img = cv2.warpAffine(
            image,
            rotation_matrix,
            (new_w, new_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255),
        )
        gray = cv2.cvtColor(rotated_img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
        coords = cv2.findNonZero(binary)
        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            margin_percent = 0.025
            margin_x = int(rotated_img.shape[1] * margin_percent)
            margin_y = int(rotated_img.shape[0] * margin_percent)
            x = max(0, x - margin_x)
            y = max(0, y - margin_y)
            w = min(rotated_img.shape[1] - x, w + 2 * margin_x)
            h = min(rotated_img.shape[0] - y, h + 2 * margin_y)
            rotated_img = rotated_img[y : y + h, x : x + w]
            # logger.debug(f"Trimmed rotated image to: ({x}, {y}, {x+w}, {y+h})")
        else:
            # logger.debug(
            #     "No non-white content detected after rotation, returning full image"
            # )
            pass
        return rotated_img

    def _deskew_image(self, image: np.ndarray) -> tuple[np.ndarray, float, bool]:
        """Correct image skew using the deskew package.

        Args:
            image (np.ndarray): Input image in BGR format.

        Returns:
            tuple[np.ndarray, float, bool]: (deskewed_image, detected_angle, was_applied)
        """
        try:
            grayscale = (
                cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                if len(image.shape) == 3
                else image
            )

            # Apply contrast enhancement for better line detection
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(grayscale)

            # Use class constant for skew detection threshold
            angle = determine_skew(enhanced)

            if angle is None or abs(angle) < self.SKEW_DETECTION_THRESHOLD:
                # No significant skew detected or below threshold
                return image, 0.0, False

            # Skew detected and above threshold - apply correction
            return self._rotate_image(image, angle), angle, True
        except Exception as e:
            logger.error(f"Deskew error: {str(e)}", exc_info=True)
            return image, 0.0, False

    def _detect_orientation(
        self, pil_image: Image.Image
    ) -> tuple[Optional[int], float]:
        """Detect image orientation using Tesseract OCR with confidence checking.

        Args:
            pil_image (Image.Image): Input image.

        Returns:
            tuple: (Detected orientation in degrees (0, 90, 180, 270) or None, confidence score)
        """
        cropped_img = None
        gray_img = None

        try:
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")

            # Crop whitespace before OCR
            cropped_img = self._crop_whitespace(pil_image)
            gray_img = cropped_img.convert("L")

            # Get OSD output with confidence information
            osd_output = pytesseract.image_to_osd(gray_img, config="--psm 0")

            angle = None
            confidence = 0

            for line in osd_output.split("\n"):
                if "Orientation in degrees" in line:
                    angle = int(line.split(":")[1].strip())
                elif "Orientation confidence" in line:
                    confidence = float(line.split(":")[1].strip())

            # Only return angle if confidence is above threshold
            if angle is not None and confidence >= self.CONFIDENCE_THRESHOLD:
                # logger.debug(
                #     f"Detected orientation: {angle}°, confidence: {confidence:.2f}"
                # )
                return angle, confidence
            else:
                # logger.debug(
                #     f"Low confidence orientation: {angle}°, confidence: {confidence:.2f}, skipping rotation"
                # )
                return None, confidence

        except TesseractError:
            # logger.debug("Tesseract OSD failed, likely due to insufficient text")
            return None, 0.0
        except Exception as e:
            logger.error(f"Orientation detection error: {str(e)}", exc_info=True)
            return None, 0.0

        finally:
            # Clean up temporary images
            if cropped_img is not None and cropped_img != pil_image:
                cropped_img.close()
            if gray_img is not None:
                gray_img.close()

    def _is_blank_image(
        self, image: np.ndarray, threshold_percent: float = None
    ) -> tuple[bool, float]:
        """Check if the image is blank based on non-white pixel percentage.

        Args:
            image (np.ndarray): Input image in BGR format.
            threshold_percent (float): Maximum percentage of non-white pixels to consider image as blank.
                                     If None, uses class constant BLANK_IMAGE_THRESHOLD.

        Returns:
            tuple: (is_blank flag, non-white percentage)
        """
        if threshold_percent is None:
            threshold_percent = self.BLANK_IMAGE_THRESHOLD

        try:
            gray = (
                cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                if len(image.shape) == 3
                else image
            )

            # Apply light noise reduction to handle compression artifacts
            gray = cv2.medianBlur(gray, 3)

            # Use consistent threshold - only very white pixels (251-255) are considered white
            non_white_percent = (
                np.sum(gray <= 250) / (gray.shape[0] * gray.shape[1])
            ) * 100

            is_blank = non_white_percent < threshold_percent
            # logger.info(f"Non-white content percentage: {non_white_percent:.2f}%")
            return is_blank, non_white_percent

        except Exception as e:
            logger.error(f"Blank detection error: {str(e)}", exc_info=True)
            return False, 100.0

    def _process_image(
        self, pil_image: Image.Image
    ) -> tuple[Image.Image, int, float, tuple[bool, float, str, str, int, float]]:
        """Apply rotation correction, deskewing, cropping, resizing, and enhancement to the image.

        Cropping, resizing, and enhancement are applied to all non-blank pages, even if no
        rotation correction is needed.

        Args:
            pil_image (Image.Image): Input image.

        Returns:
            tuple: (Processed image, applied rotation, confidence, log details)
                   where log details are (is_blank, non_white_percent, initial_size,
                   final_size, detected_orientation, skew_angle)
        """
        initial_size = f"{pil_image.width}x{pil_image.height}"

        bgr_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # Check for blank image and handle separately
        is_blank, non_white_percent = self._is_blank_image(bgr_image)
        if is_blank:
            # logger.debug("Blank image detected, skipping rotation")
            resized_blank = self._resize_image(pil_image)
            final_size = f"{resized_blank.width}x{resized_blank.height}"
            return (
                resized_blank,
                0,
                0.0,
                (True, non_white_percent, initial_size, final_size, 0, 0.0),
            )

        # Step 1: Deskew the image
        deskewed_bgr, skew_angle, _ = self._deskew_image(bgr_image)
        deskewed_pil = Image.fromarray(cv2.cvtColor(deskewed_bgr, cv2.COLOR_BGR2RGB))

        # Step 2: Detect and apply orientation correction if needed
        orientation, confidence = self._detect_orientation(deskewed_pil)
        detected_orientation = orientation if orientation is not None else 0
        angle = 0 if orientation is None else orientation % 360

        processed_pil = deskewed_pil  # Default to deskewed image

        if angle != 0:
            # Trust Tesseract OSD - it's already filtered by CONFIDENCE_THRESHOLD
            rotated_bgr = self._rotate_image(deskewed_bgr, angle)
            processed_pil = Image.fromarray(cv2.cvtColor(rotated_bgr, cv2.COLOR_BGR2RGB))
            # Clean up the deskewed image since we're using the rotated one
            deskewed_pil.close()

        # Step 3: Always apply cropping, resizing, and enhancement

        # Apply transformations with cleanup
        resized_pil = self._resize_image(processed_pil)
        if resized_pil != processed_pil:
            processed_pil.close()

        cropped_pil = self._crop_whitespace(resized_pil)
        if cropped_pil != resized_pil:
            resized_pil.close()

        enhanced_pil = self._enhance_image(cropped_pil)
        if enhanced_pil != cropped_pil:
            cropped_pil.close()

        final_size = f"{enhanced_pil.width}x{enhanced_pil.height}"
        return (
            enhanced_pil,
            angle,
            confidence,
            (
                False,
                non_white_percent,
                initial_size,
                final_size,
                detected_orientation,
                skew_angle,
            ),
        )

    def _process_single_page(self, page_data: tuple) -> tuple[bytes, int, float]:
        """Process a single PDF page and return processed image bytes with rotation info.

        Args:
            page_data: Tuple of (page_image, page_number, total_pages)

        Returns:
            tuple: (Processed image as JPEG bytes, rotation angle, confidence)
        """
        page_image, page_number, total_pages = page_data
        processed_img = None

        try:
            # logger.debug(f"Processing page {page_number}/{total_pages}")
            processed_img, angle, confidence, details = self._process_image(page_image)

            is_blank, percent, initial_size, final_size, detected, skew = details
            blank_str = "True" if is_blank else "False"
            percent_str = f"{percent:.2f}%" if percent is not None else "N/A"
            summary = (
                f"Processed page {page_number}/{total_pages}: "
                f"blank={blank_str} ({percent_str}), "
                f"skew:{skew:.2f}°, "
                f"rotation:{detected}°/conf={confidence:.2f}, "
                f"size: {initial_size}→{final_size}"
            )
            logger.info(summary)

            # Convert to bytes
            with io.BytesIO() as f:
                processed_img.save(
                    f, format="JPEG", quality=self.JPEG_QUALITY, optimize=True
                )
                result = f.getvalue()

            return result, angle, confidence

        except Exception as e:
            logger.error(f"Error processing page {page_number}: {str(e)}")
            # Return original image as fallback
            with io.BytesIO() as f:
                page_image.save(f, format="JPEG", quality=self.JPEG_QUALITY)
                return f.getvalue(), 0, 0.0

        finally:
            # Explicit cleanup of PIL image objects
            if processed_img is not None:
                processed_img.close()
            if page_image is not None:
                page_image.close()

    def handle_image_rotation(
        self, image_path: str, output_path: Optional[str] = None
    ) -> bool:
        """Process a single image: fix orientation, deskew, crop, resize, enhance, and save.

        Args:
            image_path (str): Path to the input image file.
            output_path (Optional[str]): Path to save the output image; defaults to input path.

        Returns:
            bool: True if processing succeeds, False otherwise.
        """
        logger.info(f"Starting image rotation handling for file: {image_path}")
        output_path = output_path or image_path

        pil_img = None
        processed_img = None

        try:
            if not os.path.exists(image_path):
                logger.error(f"Image file not found: {image_path}")
                return False

            pil_img = Image.open(image_path)
            pil_img = self._fix_exif_rotation(pil_img)
            processed_img, _, _, _ = self._process_image(pil_img)

            processed_img.save(
                output_path,
                format="PNG" if output_path.lower().endswith(".png") else "JPEG",
                quality=self.JPEG_QUALITY,
                optimize=True,
            )
            logger.info(f"Image successfully saved to: {output_path}")
            return True

        except Exception as e:
            logger.error(
                f"Image processing error for file={image_path}: {str(e)}", exc_info=True
            )
            return False

        finally:
            # Clean up image objects
            if pil_img is not None:
                pil_img.close()
            if processed_img is not None:
                processed_img.close()

    def _pdf_to_images_generator(
        self, pdf_path: str
    ) -> Generator[Image.Image, None, None]:
        """Yield PDF pages as images one at a time to minimize memory usage.

        Args:
            pdf_path (str): Path to the input PDF file.

        Yields:
            Image.Image: A single page as a PIL image.

        Raises:
            Exception: If PDF conversion fails.
        """
        try:
            # Use generator directly from pdf2image for true streaming
            for page in convert_from_path(
                pdf_path,
                dpi=self.PDF_DPI,
                single_file=False,
                thread_count=1,  # Limit threads to control memory
                first_page=None,
                last_page=None,
            ):
                yield page
                # Note: The caller is responsible for closing the yielded image

        except PDFPageCountError as e:
            logger.error(f"PDF conversion error for file={pdf_path}: {str(e)}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected PDF conversion error for file={pdf_path}: {str(e)}",
                exc_info=True,
            )
            raise

    def handle_pdf_rotation(
        self,
        pdf_path: str,
        output_path: Optional[str] = None,
        page_limit: Optional[int] = None,
    ) -> bool:
        """Process a PDF file, correcting rotation page by page sequentially, and save the result.

        Args:
            pdf_path (str): Path to the input PDF file.
            output_path (Optional[str]): Path to save the processed PDF; defaults to input path.
            page_limit (Optional[int]): Maximum number of pages to process; defaults to None (all pages).

        Returns:
            bool: True if processing succeeds, False otherwise.
        """
        output_path = output_path or pdf_path
        t0 = time.time()

        # Track rotation results for summary
        rotation_results = []  # Will store (angle, confidence) tuples

        try:
            if not os.path.exists(pdf_path):
                logger.error(f"PDF file not found: {pdf_path}")
                return False

            # Get total page count and file size
            import fitz

            with fitz.open(pdf_path) as doc:
                total_pages = len(doc)

            size_before = os.path.getsize(pdf_path)
            size_before_kb = size_before / 1024

            # Apply page limit if specified
            pages_to_process = (
                min(total_pages, page_limit) if page_limit else total_pages
            )

            logger.info(
                f"Starting rotation handler: file={os.path.basename(pdf_path)}, size_before={size_before_kb:.0f}KB, pages={pages_to_process}, dpi={self.PDF_DPI}"
            )

            # Process pages sequentially using generator to control memory
            all_processed_bytes = []
            page_generator = self._pdf_to_images_generator(pdf_path)

            for page_number, page_image in enumerate(page_generator, 1):
                # Stop processing if we've reached the page limit
                if page_limit and page_number > page_limit:
                    page_image.close()
                    break

                try:
                    # Process page directly
                    result_bytes, angle, conf = self._process_single_page(
                        (page_image, page_number, pages_to_process)
                    )
                    all_processed_bytes.append(result_bytes)
                    rotation_results.append((angle, conf))

                except Exception as e:
                    logger.error(f"Error processing page {page_number}: {str(e)}")
                    # Use original image as fallback
                    with io.BytesIO() as f:
                        page_image.save(
                            f,
                            format="JPEG",
                            quality=self.JPEG_QUALITY,
                        )
                        all_processed_bytes.append(f.getvalue())
                        rotation_results.append((0, 0.0))
                    page_image.close()

                # Cleanup after each page to minimize memory usage
                gc.collect()

            # Save the final PDF
            if all_processed_bytes:
                with open(output_path, "wb") as f:
                    f.write(img2pdf.convert(all_processed_bytes))

                # Get file size after rotation
                size_after = os.path.getsize(output_path)
                size_after_kb = size_after / 1024

                # Format rotation results
                rotation_summary = ", ".join(
                    [f"{angle}°/{conf:.2f}" for angle, conf in rotation_results]
                )

                # Log completion with summary
                elapsed_time = time.time() - t0
                logger.info(
                    f"Completed rotation handler: file={os.path.basename(pdf_path)}, time={elapsed_time:.2f}s, size_after={size_after_kb:.0f}KB, rotations/confidence=[{rotation_summary}]"
                )

                # Clear processed bytes from memory
                all_processed_bytes.clear()
                gc.collect()

                return True
            else:
                logger.error("No processed pages to save")
                return False

        except Exception as e:
            logger.error(
                f"PDF processing error for file={pdf_path}: {str(e)}", exc_info=True
            )
            return False
        finally:
            # Final cleanup
            if "all_processed_bytes" in locals():
                all_processed_bytes.clear()
            gc.collect()


if __name__ == "__main__":
    input_file = "./data/multiple pages_rotated.pdf"
    if not os.path.exists(input_file):
        logger.error(f"Input file not found: {input_file}")
        sys.exit(1)

    file_base, file_ext = os.path.splitext(input_file)
    output_file = f"{file_base}-fixed{file_ext}"
    is_pdf = file_ext.lower() == ".pdf"
    page_limit = 1

    handler = RotationHandler()
    logger.info(f"Processing {'PDF' if is_pdf else 'image'} file: {input_file}")
    success = (
        handler.handle_pdf_rotation if is_pdf else handler.handle_image_rotation
    )(input_file, output_file)
    logger.info(f"{'Success' if success else 'Failed'} processing file: {input_file}")
    sys.exit(0 if success else 1)
