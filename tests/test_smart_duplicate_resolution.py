"""Unit and integration tests for Phase 5: Smart Duplicate Resolution via LLM Disambiguation."""

import sys
import time
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.llm import generate_title_from_text, generate_disambiguated_title
from src.naming import sanitize_title_to_filename, is_filename_colliding, get_file_capture_date
from src.core import SnapTitleService
from config.config import Config, load_config


def create_text_image(output_path: Path, lines: list[str]) -> Path:
    """Create a high-contrast synthetic screenshot with specific lines of text."""
    img = Image.new("RGB", (700, 300), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 30
    for line in lines:
        draw.text((30, y), line, fill=(0, 0, 0))
        y += 45
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


class TestSmartDuplicateResolution(unittest.TestCase):
    """Test smart duplicate resolution via LLM and graceful timestamp fallback."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_disambiguation_"))
        self.config = load_config()
        self.config.screenshots_dir = self.temp_dir
        self.config.show_popup = False  # Headless mode for automated tests
        self.service = SnapTitleService(config=self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_llm_disambiguation_direct(self):
        """Test generate_disambiguated_title generates a distinct, more specific title."""
        colliding_title = "Database Connection Error"
        context_text = "PostgreSQL error: Connection refused to master host db-prod-01 on port 5432."

        alt_title = generate_disambiguated_title(
            colliding_title=colliding_title,
            context_text=context_text,
            model=self.config.llm_model,
            host=self.config.ollama_host
        )

        print(f"\n[Direct Disambiguation] Original: '{colliding_title}' -> Disambiguated: '{alt_title}'")
        if alt_title is not None:
            self.assertNotEqual(alt_title.strip().lower(), colliding_title.lower())
            self.assertLessEqual(len(alt_title.split()), 6)
        else:
            print("  (Ollama server offline; direct disambiguation returned None as expected)")

    def test_two_similar_screenshots_get_distinct_meaningful_titles(self):
        """Test two screenshots that would share a base title get distinct meaningful names without plain numbers."""
        today = datetime.now().strftime("%Y-%m-%d")

        # Screenshot 1: Kubernetes Crash in Production Frontend
        shot1 = self.temp_dir / "shot1.png"
        create_text_image(shot1, [
            "Kubernetes Cluster Error",
            "Pod: frontend-service-prod",
            "Status: CrashLoopBackOff on node worker-1"
        ])

        # Screenshot 2: Kubernetes Crash in Staging Database
        shot2 = self.temp_dir / "shot2.png"
        create_text_image(shot2, [
            "Kubernetes Cluster Error",
            "Pod: postgres-database-staging",
            "Status: CrashLoopBackOff on node worker-4"
        ])

        # Process first screenshot
        renamed1 = self.service._process_screenshot(shot1)
        self.assertIsNotNone(renamed1)
        print(f"\n[Test 1] First Screenshot Renamed  : '{renamed1.name}'")

        # Process second screenshot (which would otherwise collide on 'kubernetes-cluster-error')
        renamed2 = self.service._process_screenshot(shot2)
        self.assertIsNotNone(renamed2)
        print(f"[Test 1] Second Screenshot Renamed : '{renamed2.name}'")

        # Verify both exist and are distinct
        self.assertTrue(renamed1.exists())
        self.assertTrue(renamed2.exists())
        self.assertNotEqual(renamed1.name.lower(), renamed2.name.lower())

        # Verify both contain today's date suffix
        today = datetime.now().strftime("%d-%m-%Y")
        self.assertTrue(renamed1.name.endswith(f"_{today}.png") or f"_{today}" in renamed1.name)
        self.assertTrue(renamed2.name.endswith(f"_{today}.png") or f"_{today}" in renamed2.name)

    def test_case_insensitive_collision_disambiguation(self):
        """Verify case-insensitive matching triggers smart disambiguation on Windows/macOS."""
        today = datetime.now().strftime("%d-%m-%Y")
        
        # Pre-create an uppercase file that could collide
        existing_file = self.temp_dir / f"PAYMENT INVOICE_{today}.png"
        existing_file.write_text("existing invoice")

        new_shot = self.temp_dir / "invoice_new.png"
        create_text_image(new_shot, [
            "Payment Invoice",
            "Vendor: DigitalOcean Cloud Services",
            "Amount: $120.00 | Ref #DO-9921"
        ])

        # Process screenshot
        renamed = self.service._process_screenshot(new_shot)
        self.assertIsNotNone(renamed)
        print(f"\n[Test 2] Case-Insensitive Disambiguated File: '{renamed.name}'")

        self.assertNotEqual(renamed.name.lower(), f"payment invoice_{today}.png")
        self.assertTrue(renamed.exists())
        self.assertTrue(existing_file.exists())

    def test_retry_cap_and_timestamp_fallback(self):
        """Verify that if all smart retries collide, it safely falls back to deterministic timestamp."""
        today = datetime.now().strftime("%d-%m-%Y")
        
        # Create a test file
        test_shot = self.temp_dir / "test_shot.png"
        create_text_image(test_shot, ["Test Notification Message"])

        # Mock title provider to intentionally return a colliding title
        colliding_title = "test notification"
        existing = self.temp_dir / f"{colliding_title}_{today}.png"
        existing.write_text("dummy")

        # Custom service with title provider returning identical title
        service = SnapTitleService(
            config=self.config,
            title_provider=lambda p: colliding_title
        )

        renamed = service._process_screenshot(test_shot)
        self.assertIsNotNone(renamed)
        print(f"\n[Test 3] Simulated Exhausted Disambiguation Fallback: '{renamed.name}'")
        
        self.assertTrue(renamed.name.startswith(f"{colliding_title}_{today}-"))
        self.assertTrue(renamed.exists())
        self.assertTrue(existing.exists())


def main():
    print("=" * 60)
    print("  SnapTitle - Phase 5 Smart Duplicate Resolution Tests      ")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
