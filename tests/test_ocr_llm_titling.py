"""Integration and unit tests for Phase 2: OCR + LLM Titling Pipeline."""

import sys
import time
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ocr import extract_text_from_image, has_meaningful_text, binarize_image, preprocess_image_for_ocr, deduplicate_lines
from src.llm import generate_title_from_text, clean_llm_response, redact_sensitive_info
from src.core import SnapTitleService
from config.config import load_config, Config


def create_text_image(file_path: Path, lines: list[str], size: tuple[int, int] = (700, 250)) -> Path:
    """Helper to generate a clean synthetic screenshot with specified text lines."""
    img = Image.new("RGB", size, color=(245, 245, 250))
    draw = ImageDraw.Draw(img)

    y = 30
    for line in lines:
        draw.text((30, y), line, fill=(20, 20, 30))
        y += 40

    file_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(file_path, format="PNG")
    return file_path


class TestOCRModule(unittest.TestCase):
    """Test OCR extraction and text filtering."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_ocr_"))
        self.config = load_config()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_has_meaningful_text_threshold(self):
        # Empty or whitespace
        self.assertFalse(has_meaningful_text(""))
        self.assertFalse(has_meaningful_text("   "))
        self.assertFalse(has_meaningful_text(None))

        # Too short (< 5 alphanumeric chars)
        self.assertFalse(has_meaningful_text("Hi!"))
        self.assertFalse(has_meaningful_text("..."))
        self.assertFalse(has_meaningful_text("a b"))

        # Valid meaningful text (>= 5 chars)
        self.assertTrue(has_meaningful_text("Hello World"))
        self.assertTrue(has_meaningful_text("Error 404"))
        self.assertTrue(has_meaningful_text("Release v2.0"))

    def test_ocr_extraction_on_image(self):
        img_path = self.temp_dir / "sample_text.png"
        create_text_image(img_path, ["Server Error: Connection Refused", "Host: localhost:5432"])

        extracted = extract_text_from_image(img_path, tesseract_cmd=self.config.tesseract_cmd)
        self.assertTrue(has_meaningful_text(extracted))
        self.assertIn("Connection", extracted)

    def test_image_binarization_and_preprocessing(self):
        """Verify binarize_image and preprocess_image_for_ocr functions on test image."""
        img_path = self.temp_dir / "prep_test.png"
        create_text_image(img_path, ["Preprocessing Test Line"])

        with Image.open(img_path) as raw_img:
            processed = preprocess_image_for_ocr(raw_img)
            self.assertIsNotNone(processed)
            self.assertEqual(processed.mode, "L")

            binarized = binarize_image(raw_img, threshold=128)
            self.assertIsNotNone(binarized)
            self.assertEqual(binarized.mode, "1")

    def test_deduplicate_lines_removes_consecutive_repeats(self):
        """Verify consecutive duplicate lines are collapsed by deduplicate_lines."""
        text = "Header Line\nHeader Line\nContent A\nContent B\nContent B\nFooter"
        result = deduplicate_lines(text)
        self.assertEqual(result, "Header Line\nContent A\nContent B\nFooter")

        # Empty and single-line edge cases
        self.assertEqual(deduplicate_lines(""), "")
        self.assertEqual(deduplicate_lines("Only one line"), "Only one line")


class TestLLMResponseCleaningAndPrivacy(unittest.TestCase):
    """Test response cleaning, word limiting, and privacy guardrails."""

    def test_clean_llm_response_removes_quotes_and_prefixes(self):
        raw = 'Title: "PostgreSQL Connection Error On Server"'
        cleaned = clean_llm_response(raw)
        self.assertEqual(cleaned, "PostgreSQL Connection Error On Server")

        raw_markdown = '**Suggested Title:** `Team Deployment Chat Meeting`'
        cleaned = clean_llm_response(raw_markdown)
        self.assertEqual(cleaned, "Team Deployment Chat Meeting")

    def test_clean_llm_response_enforces_word_limit(self):
        raw = "This is an extremely long title description with way too many words than permitted"
        cleaned = clean_llm_response(raw, max_words=6)
        words = cleaned.split()
        self.assertLessEqual(len(words), 6)

    def test_redact_sensitive_info(self):
        text = "My secret token is password = supersecret123 and credit card is 4111-2222-3333-4444."
        redacted = redact_sensitive_info(text)
        self.assertNotIn("supersecret123", redacted)
        self.assertNotIn("4111-2222-3333-4444", redacted)


class TestRealScreenshotsEndToEndTitling(unittest.TestCase):
    """End-to-end testing with realistic screenshots (error, chat, article, sparse)."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_e2e_"))
        self.config = load_config()
        self.config.screenshots_dir = self.temp_dir
        self.config.show_popup = False
        self.service = SnapTitleService(config=self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_error_message_screenshot_titling(self):
        """Test screenshot with an error message generates an error-related title."""
        img_path = self.temp_dir / "Screenshot_Error.png"
        create_text_image(img_path, [
            "DatabaseConnectionError: Connection to PostgreSQL failed",
            "FATAL: password authentication failed for user postgres",
            "Server: localhost:5432 | Status: DISCONNECTED"
        ])

        title = self.service.generate_title_for_screenshot(img_path)
        print(f"\n[Test 1] Error Screenshot -> Generated Title: '{title}'")
        self.assertTrue(len(title.split()) <= 6)
        self.assertTrue(any(w in title.lower() for w in ["database", "connection", "postgresql", "error", "auth", "failed"]))

    def test_chat_screenshot_titling(self):
        """Test screenshot with a chat conversation generates a chat/discussion title."""
        img_path = self.temp_dir / "Screenshot_Chat.png"
        create_text_image(img_path, [
            "Alice [10:15 AM]: Hey team, are we ready for the v2.4 deployment?",
            "Bob [10:16 AM]: Yes, all QA tests passed. Starting release deployment at 3 PM.",
            "Charlie [10:17 AM]: Sounds great, monitoring dashboard is ready."
        ])

        title = self.service.generate_title_for_screenshot(img_path)
        print(f"[Test 2] Chat Screenshot -> Generated Title: '{title}'")
        self.assertTrue(len(title.split()) <= 6)
        self.assertTrue(any(w in title.lower() for w in ["deployment", "release", "chat", "team", "qa", "discussion"]))

    def test_article_screenshot_titling(self):
        """Test screenshot with an article/documentation snippet generates a topic title."""
        img_path = self.temp_dir / "Screenshot_Article.png"
        create_text_image(img_path, [
            "Python 3.13 Release Highlights",
            "Free-threaded CPython without GIL and JIT compiler improvements.",
            "Significant performance enhancements in standard library modules."
        ])

        title = self.service.generate_title_for_screenshot(img_path)
        print(f"[Test 3] Article Screenshot -> Generated Title: '{title}'")
        self.assertTrue(len(title.split()) <= 6)
        self.assertTrue(any(w in title.lower() for w in ["python", "release", "highlights", "cpython", "jit", "compiler"]))

    def test_sparse_screenshot_threshold_skips_llm(self):
        """Test screenshot with no/sparse text triggers threshold check."""
        img_path = self.temp_dir / "Screenshot_Blank.png"
        # Create an image with just 2 dots / no meaningful text
        create_text_image(img_path, [".."])

        extracted = extract_text_from_image(img_path, tesseract_cmd=self.config.tesseract_cmd)
        self.assertFalse(has_meaningful_text(extracted))

        title = self.service.generate_title_for_screenshot(img_path)
        print(f"[Test 4] Sparse Screenshot -> Resulting Title: '{title}'")
        self.assertTrue(len(title.split()) <= 6)
        self.assertTrue(len(title) > 0)

    def test_full_pipeline_detection_and_renaming(self):
        """Test complete watcher detection -> OCR -> LLM titling -> safe renaming."""
        self.service.start()
        try:
            test_file = self.temp_dir / "Screenshot 2026-08-15 at 2.00.00 PM.png"
            create_text_image(test_file, [
                "Payment Invoice #98421",
                "Total Amount Due: $150.00",
                "Vendor: Cloud Hosting Services Inc."
            ])

            # Wait for detection and renaming
            start = time.time()
            renamed_file: Path | None = None
            while time.time() - start < 15.0:
                files = list(self.temp_dir.glob("*.png"))
                for f in files:
                    if f.name != test_file.name:
                        renamed_file = f
                        break
                if renamed_file:
                    break
                time.sleep(0.4)

            self.assertIsNotNone(renamed_file, "Screenshot was not automatically renamed by watcher service.")
            print(f"[Pipeline Test] Original -> Renamed File: '{renamed_file.name}'")
            today = datetime.now().strftime("%Y-%m-%d")
            self.assertTrue(renamed_file.name.endswith(f"_{today}.png") or f"_{today}" in renamed_file.name, f"Renamed file '{renamed_file.name}' missing date suffix '_{today}.png'")
            self.assertTrue(renamed_file.name.endswith(".png"))
            self.assertTrue(any(w in renamed_file.name for w in ["payment", "invoice", "hosting", "cloud", "services"]))

        finally:
            self.service.stop()


def main():
    print("=" * 60)
    print("      SnapTitle - Phase 2 OCR + LLM Titling Tests           ")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
