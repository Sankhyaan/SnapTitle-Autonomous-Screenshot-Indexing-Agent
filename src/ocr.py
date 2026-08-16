"""OCR extraction, image preprocessing, and text filtering module using Tesseract."""

import re
import logging
from pathlib import Path
from typing import Optional
from PIL import Image, ImageOps, ImageEnhance

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore

logger = logging.getLogger("snaptitle.ocr")

# Minimum meaningful characters threshold
MIN_MEANINGFUL_TEXT_LENGTH = 5


def clean_extracted_text(text: Optional[str]) -> str:
    """Normalize and clean raw OCR text for downstream processing and LLM prompts.

    - Removes non-printable control characters (retains standard newlines and spaces).
    - Collapses excessive blank lines to at most two newlines.
    - Normalizes horizontal spaces on individual lines.

    Args:
        text: Raw OCR extracted text string.

    Returns:
        str: Cleaned and normalized text string.
    """
    if not text:
        return ""

    # Remove non-printable control characters (ASCII 0-31 except tab, LF, CR)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize horizontal whitespace per line
    lines = [re.sub(r"[^\S\r\n]+", " ", line).strip() for line in cleaned.splitlines()]

    # Collapse excessive blank lines
    result_lines = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 1:
                result_lines.append("")
        else:
            blank_count = 0
            result_lines.append(line)

    return "\n".join(result_lines).strip()


def has_meaningful_text(text: Optional[str], min_chars: int = MIN_MEANINGFUL_TEXT_LENGTH) -> bool:
    """Check if the extracted OCR text contains meaningful readable characters.

    Strips whitespace and non-alphanumeric noise to ensure genuine text content.
    Filters out noise speckles and single-character repetition.

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
    if len(alphanumeric_chars) < min_chars:
        return False

    # Reject text if it consists entirely of a single repeated character
    unique_chars = set(c.lower() for c in alphanumeric_chars)
    if len(unique_chars) == 1 and len(alphanumeric_chars) > 3:
        return False

    return True


def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """Apply grayscale conversion, auto-contrast, and sharpening to enhance OCR accuracy.

    Args:
        img: Input PIL Image.

    Returns:
        Image.Image: Preprocessed PIL Image ready for Tesseract recognition.
    """
    try:
        # Convert to Grayscale
        gray = img.convert("L")
        
        # Auto-contrast normalization
        contrasted = ImageOps.autocontrast(gray, cutoff=1)
        
        # Slight sharpness boost
        enhancer = ImageEnhance.Sharpness(contrasted)
        sharpened = enhancer.enhance(1.4)
        return sharpened
    except Exception as e:
        logger.debug(f"Image preprocessing fallback to raw RGB: {e}")
        return img.convert("RGB") if img.mode != "RGB" else img


def extract_text_from_image(
    image_path: Path,
    tesseract_cmd: Optional[str] = None
) -> str:
    """Extract text from an image using Tesseract OCR with automatic image optimization.

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
            # Preprocess image to maximize character clarity for Tesseract
            processed_img = preprocess_image_for_ocr(img)
            extracted = pytesseract.image_to_string(processed_img)
            cleaned_text = extracted.strip()
            
            # If standard pass yielded no text on converted image, try raw fallback
            if not has_meaningful_text(cleaned_text):
                raw_rgb = img.convert("RGB")
                fallback_extracted = pytesseract.image_to_string(raw_rgb).strip()
                if has_meaningful_text(fallback_extracted):
                    cleaned_text = fallback_extracted

            final_text = clean_extracted_text(cleaned_text)
            logger.debug(f"OCR extracted {len(final_text)} characters from {image_path.name}")
            return final_text

    except Exception as err:
        logger.error(f"OCR extraction failed for '{image_path}': {err}", exc_info=True)
        return ""
