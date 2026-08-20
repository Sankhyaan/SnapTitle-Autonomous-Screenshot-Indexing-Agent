"""Environment and Dependency Verification Test for SnapTitle.

Tests:
1. Configuration loading and screenshot directory auto-detection.
2. Tesseract OCR on a synthesized sample image.
3. Local Ollama LLM call with a test prompt.
"""

import sys
import os
from pathlib import Path 
from PIL import Image, ImageDraw, ImageFont

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import load_config, find_tesseract_binary


def create_sample_image(output_path: Path) -> Path:
    """Create a clean sample image with text for OCR testing."""
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Draw simple readable text
    text_lines = [
        "SnapTitle Verification Test",
        "Error 404: Resource Not Found",
        "System timestamp: 2026-08-15"
    ]
    y_offset = 30
    for line in text_lines:
        draw.text((40, y_offset), line, fill=(0, 0, 0))
        y_offset += 45

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path)
    return output_path


def test_config():
    """Test configuration loading and screenshot directory detection."""
    print("\n" + "=" * 60)
    print("1. Testing Configuration & Auto-Detection")
    print("=" * 60)
    config = load_config()
    print(f"[OK] Screenshots Directory : {config.screenshots_dir}")
    print(f"[OK] Popup Duration        : {config.popup_duration_seconds}s")
    print(f"[OK] LLM Model             : {config.llm_model}")
    print(f"[OK] VLM Model             : {config.vlm_model}")
    print(f"[OK] Ollama Host           : {config.ollama_host}")
    print(f"[OK] Database Path         : {config.database_path}")
    return config


def test_tesseract(config):
    """Test Tesseract OCR extraction on a sample image."""
    print("\n" + "=" * 60)
    print("2. Testing Tesseract OCR")
    print("=" * 60)

    try:
        import pytesseract
    except ImportError:
        print("[FAIL] 'pytesseract' is not installed in the Python environment.")
        return False

    tesseract_bin = find_tesseract_binary(config.tesseract_cmd)
    if tesseract_bin:
        pytesseract.pytesseract.tesseract_cmd = tesseract_bin
        print(f"[INFO] Tesseract executable found: {tesseract_bin}")
    else:
        print("[WARN] Tesseract executable NOT found in PATH or standard install paths.")
        print("       -> To install on Windows, run:")
        print("          winget install UB-Mannheim.TesseractOCR")
        print("          or download from: https://github.com/UB-Mannheim/tesseract/wiki")
        return False

    sample_img_path = PROJECT_ROOT / "tests" / "sample_ocr.png"
    create_sample_image(sample_img_path)
    print(f"[INFO] Generated sample test image at: {sample_img_path}")

    try:
        image = Image.open(sample_img_path)
        extracted_text = pytesseract.image_to_string(image).strip()
        print("[SUCCESS] Extracted OCR Text:")
        print("-" * 40)
        print(extracted_text if extracted_text else "(No text detected)")
        print("-" * 40)
        return True
    except Exception as e:
        print(f"[FAIL] Tesseract OCR execution failed: {e}")
        return False


def test_ollama(config):
    """Test local Ollama LLM response."""
    print("\n" + "=" * 60)
    print(f"3. Testing Ollama Model Call ({config.llm_model})")
    print("=" * 60)

    try:
        import ollama
    except ImportError:
        print("[FAIL] 'ollama' Python library is not installed.")
        return False

    test_prompt = "Generate a concise 3-to-5 word title for a screenshot showing: 'Error 404: Resource Not Found in user dashboard'. Respond with only the title."
    print(f"[INFO] Sending test prompt to Ollama ({config.llm_model})...")

    try:
        client = ollama.Client(host=config.ollama_host)
        # Check if Ollama service is reachable
        models_info = client.list()
        available_models = [m.model for m in models_info.models] if hasattr(models_info, "models") else []
        print(f"[INFO] Ollama is running. Available local models: {available_models}")

        # Check if target model is present
        target_model = config.llm_model
        model_found = any(target_model in m for m in available_models)

        if not model_found and available_models:
            print(f"[WARN] Target model '{target_model}' not found in local models.")
            print(f"       Using first available model '{available_models[0]}' for testing...")
            target_model = available_models[0]
        elif not model_found:
            print(f"[WARN] Target model '{target_model}' is not pulled yet.")
            print(f"       -> Run: ollama pull {target_model}")
            return False

        response = client.generate(
            model=target_model,
            prompt=test_prompt,
        )
        response_text = response.get("response", "").strip()
        print("[SUCCESS] Ollama Response:")
        print("-" * 40)
        print(response_text)
        print("-" * 40)
        return True

    except Exception as e:
        print(f"[WARN] Could not connect to Ollama or run inference: {e}")
        print("       -> If Ollama is not installed, install it from: https://ollama.com/download")
        print("          or run: winget install Ollama.Ollama")
        print("       -> Make sure the Ollama app/service is running: ollama serve")
        print(f"       -> Pull required models: ollama pull {config.llm_model} && ollama pull {config.vlm_model}")
        return False


import unittest


class TestEnvironmentSetup(unittest.TestCase):
    """Automated unit test suite verifying configuration loading and dependency detection."""

    def test_config_loading(self):
        """Verify configuration object loads with non-empty defaults."""
        config = load_config()
        self.assertIsNotNone(config.screenshots_dir)
        self.assertIsNotNone(config.database_path)
        self.assertGreater(config.popup_duration_seconds, 0)
        self.assertTrue(isinstance(config.to_dict(), dict))

    def test_sample_image_generation(self):
        """Verify test sample image generation creates a valid image file."""
        sample_path = PROJECT_ROOT / "tests" / "sample_ocr.png"
        created = create_sample_image(sample_path)
        self.assertTrue(created.exists())
        self.assertGreater(created.stat().st_size, 0)

    def test_image_extension_validation(self):
        """Verify image extension validator matches supported formats in uppercase and lowercase."""
        from config.config import is_supported_image_extension
        self.assertTrue(is_supported_image_extension(".png"))
        self.assertTrue(is_supported_image_extension(".PNG"))
        self.assertTrue(is_supported_image_extension(".jpg"))
        self.assertTrue(is_supported_image_extension("JPEG"))
        self.assertTrue(is_supported_image_extension(Path("screenshot.WEBP")))
        self.assertFalse(is_supported_image_extension(".pdf"))
        self.assertFalse(is_supported_image_extension(".txt"))

    def test_config_timeouts_and_retries(self):
        """Verify timeout and retry defaults in Config object."""
        config = load_config()
        self.assertGreater(config.llm_timeout, 0)
        self.assertGreater(config.vlm_timeout, 0)
        self.assertGreaterEqual(config.llm_max_retries, 1)
        cfg_dict = config.to_dict()
        self.assertIn("llm_timeout", cfg_dict)
        self.assertIn("vlm_timeout", cfg_dict)
        self.assertIn("llm_max_retries", cfg_dict)


def main():
    print("============================================================")
    print("               SnapTitle Environment Test                   ")
    print("============================================================")

    config = test_config()
    tesseract_ok = test_tesseract(config)
    ollama_ok = test_ollama(config)

    print("\n" + "=" * 60)
    print("                     SUMMARY")
    print("=" * 60)
    print(f"  Configuration & Folders : [OK]")
    print(f"  Tesseract OCR           : [{'OK' if tesseract_ok else 'PENDING INSTALL'}]")
    print(f"  Ollama AI Inference     : [{'OK' if ollama_ok else 'PENDING INSTALL / PULL'}]")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
