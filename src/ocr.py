"""OCR extraction and text filtering module using Tesseract."""

import re
import logging
from pathlib import Path
from typing import Optional
from PIL import Image

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore

logger = logging.getLogger("snaptitle.ocr")

# Minimum meaningful characters threshold
MIN_MEANINGFUL_TEXT_LENGTH = 5


def has_meaningful_text(text: Optional[str], min_chars: int = MIN_MEANINGFUL_TEXT_LENGTH) -> bool:
    """Check if the extracted OCR text contains meaningful readable characters.

    Strips whitespace and non-alphanumeric noise to ensure genuine text content.

    Args:
        text: Extracted OCR text string.
        min_chars: Minimum required alphanumeric characters (default: 5).

    Returns:
        bool: True if text meets or exceeds threshold, False otherwise.
    """
    if not text:
        return False

    # Extract alphanumeric characters to filter out stray OCR speckles/symbols
    alphanumeric_chars = re.findall(r"\w", text)
    return len(alphanumeric_chars) >= min_chars


def extract_text_from_image(
    image_path: Path,
    tesseract_cmd: Optional[str] = None
) -> str:
    """Extract text from an image using Tesseract OCR.

    Args:
        image_path: Path to the screenshot image file.
        tesseract_cmd: Optional path to Tesseract binary.

    Returns:
        str: Extracted and cleaned text, or empty string if no text/error.
    """
    if pytesseract is None:
        logger.error("pytesseract is not available in the current environment.")
        return ""

    if not image_path.exists():
        logger.warning(f"Image path does not exist for OCR: {image_path}")
        return ""

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    elif not hasattr(pytesseract.pytesseract, "tesseract_cmd") or pytesseract.pytesseract.tesseract_cmd == "tesseract":
        from config.config import find_tesseract_binary
        detected = find_tesseract_binary()
        if detected:
            pytesseract.pytesseract.tesseract_cmd = detected

    try:
        with Image.open(image_path) as img:
            # Convert palette/RGBA images to RGB for optimal OCR compatibility
            if img.mode in ("P", "RGBA", "LA"):
                img = img.convert("RGB")

            extracted = pytesseract.image_to_string(img)
            cleaned_text = extracted.strip()
            logger.debug(f"OCR extracted {len(cleaned_text)} characters from {image_path.name}")
            return cleaned_text

    except Exception as err:
        logger.error(f"OCR extraction failed for '{image_path}': {err}", exc_info=True)
        return ""
