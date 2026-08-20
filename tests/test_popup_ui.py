"""Unit and integration tests for Phase 4: Popup UI, Countdown, User Editing, and Renaming."""

import sys
import time
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path 
import tkinter as tk 
from PIL import Image, ImageDraw

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.popup import ScreenshotPopup, PopupManager
from src.core import SnapTitleService
from config.config import Config, load_config


def create_test_image(output_path: Path, title_text: str = "Invoice Receipt Summary") -> Path:
    """Helper to generate a clean synthetic screenshot with readable text."""
    img = Image.new("RGB", (500, 200), color=(240, 245, 255))
    draw = ImageDraw.Draw(img)
    draw.text((30, 40), title_text, fill=(20, 30, 60))
    draw.text((30, 90), "Amount: $240.00 | Date: 2026-08-15", fill=(60, 60, 80))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


class TestPopupUIUnit(unittest.TestCase):
    """Test ScreenshotPopup lifecycle, loading state, title update, editing, and timer dismissal."""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_popup_"))
        self.sample_img = self.temp_dir / "sample.png"
        create_test_image(self.sample_img)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_popup_initial_loading_state(self):
        """Verify popup displays thumbnail and begins in 'Naming...' state without countdown."""
        popup = ScreenshotPopup(
            master=self.root,
            image_path=self.sample_img,
            duration_seconds=5
        )
        self.root.update()

        try:
            # Check loading badge
            self.assertEqual(popup.status_badge.cget("text"), "⚡ Naming...")
            # Entry should be disabled in loading state
            self.assertEqual(str(popup.entry.cget("state")), "disabled")
            # Timer is not active yet
            self.assertFalse(popup._timer_running)
        finally:
            popup.destroy()

    def test_popup_set_title_activates_countdown(self):
        """Verify set_title populates title, enables text box, and starts countdown timer."""
        popup = ScreenshotPopup(
            master=self.root,
            image_path=self.sample_img,
            duration_seconds=5
        )
        self.root.update()

        try:
            popup.set_title("Invoice Receipt Summary")
            self.root.update()

            # Status badge updated
            self.assertIn("AI Ready", popup.status_badge.cget("text"))
            # Entry enabled and populated
            self.assertEqual(str(popup.entry.cget("state")), "normal")
            self.assertEqual(popup.title_var.get(), "Invoice Receipt Summary")
            # Timer is now running
            self.assertTrue(popup._timer_running)
        finally:
            popup.destroy()

    def test_popup_user_edit_preservation(self):
        """Verify that when user edits the text, confirm returns the EDITED title."""
        confirmed_title = []

        popup = ScreenshotPopup(
            master=self.root,
            image_path=self.sample_img,
            duration_seconds=5,
            on_confirmed=lambda title: confirmed_title.append(title)
        )
        self.root.update()

        try:
            popup.set_title("Original AI Title")
            self.root.update()

            # Simulate user editing the text box
            popup.title_var.set("My Custom Edited Invoice Name")
            self.root.update()

            # Trigger confirm
            popup._on_confirm_click()
            self.root.update()

            self.assertEqual(len(confirmed_title), 1)
            self.assertEqual(confirmed_title[0], "My Custom Edited Invoice Name")
        finally:
            if not popup._is_closed:
                popup.destroy()

    def test_popup_early_close_saves_immediately(self):
        """Verify clicking close saves immediately with current title."""
        saved_titles = []
        popup = ScreenshotPopup(
            master=self.root,
            image_path=self.sample_img,
            duration_seconds=5,
            on_confirmed=lambda title: saved_titles.append(title)
        )
        self.root.update()

        try:
            popup.set_title("Fast Close Title")
            self.root.update()

            # Early close click
            popup._on_confirm_click()
            self.root.update()

            self.assertEqual(len(saved_titles), 1)
            self.assertEqual(saved_titles[0], "Fast Close Title")
            self.assertTrue(popup._is_closed)
        finally:
            if not popup._is_closed:
                popup.destroy()


class TestPopupManagerIntegration(unittest.TestCase):
    """Test PopupManager threaded lifecycle and auto-dismissal."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_pm_"))
        self.sample_img = self.temp_dir / "invoice.png"
        create_test_image(self.sample_img)
        self.manager = PopupManager()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_popup_manager_auto_dismiss(self):
        """Test show_popup_and_wait with short duration auto-dismisses and returns AI title."""
        def simulated_ai_resolver():
            time.sleep(0.3)  # Simulate OCR/LLM latency
            return "Monthly Server Bill Invoice"

        t0 = time.time()
        result = self.manager.show_popup_and_wait(
            image_path=self.sample_img,
            title_resolver=simulated_ai_resolver,
            duration_seconds=1  # 1 second for fast unit testing
        )
        elapsed = time.time() - t0

        print(f"\n[Popup Manager Test] Auto-dismissed in {elapsed:.2f}s with title: '{result}'")
        self.assertEqual(result, "Monthly Server Bill Invoice")
        self.assertGreaterEqual(elapsed, 1.0)


class TestFullEndToEndPipelineWithPopup(unittest.TestCase):
    """End-to-end watcher test with active Popup UI."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_e2e_popup_"))
        self.config = Config(
            screenshots_dir=self.temp_dir,
            show_popup=True,
            popup_duration_seconds=1  # 1 second auto-dismiss for test speed
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pipeline_with_popup_renames_screenshot(self):
        """Test dropping a new screenshot triggers popup, resolves title, and renames file."""
        service = SnapTitleService(
            config=self.config,
            title_provider=lambda p: "Q3 Financial Statement"
        )
        service.start()

        try:
            test_file = self.temp_dir / "Screenshot (99).png"
            create_test_image(test_file, "Q3 Financial Statement")

            # Wait for watcher -> popup -> timeout -> safe rename
            start_wait = time.time()
            renamed_file: Path | None = None
            today = datetime.now().strftime("%Y-%m-%d")

            while time.time() - start_wait < 10.0:
                files = list(self.temp_dir.glob("*.png"))
                for f in files:
                    if f.name != "Screenshot (99).png":
                        renamed_file = f
                        break
                if renamed_file:
                    break
                time.sleep(0.3)

            self.assertIsNotNone(renamed_file, "Screenshot was not renamed through the popup pipeline.")
            print(f"\n[End-to-End Popup Pipeline] Original -> Renamed File: '{renamed_file.name}'")
            self.assertTrue(renamed_file.name.startswith("q3-financial-statement_"))
            self.assertTrue(renamed_file.name.endswith(f"_{today}.png"))

        finally:
            service.stop()


def main():
    print("=" * 60)
    print("      SnapTitle - Phase 4 Popup UI & Integration Tests       ")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
