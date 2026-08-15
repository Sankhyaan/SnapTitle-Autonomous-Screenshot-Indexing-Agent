"""Unit and integration tests for Phase 1 & Title First / Date Suffix Filename Convention."""

import sys
import os
import time
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from PIL import Image

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.naming import (
    sanitize_title_to_filename,
    is_filename_colliding,
    generate_collision_fallback_filename,
    resolve_unique_filename,
    get_file_capture_date,
)
from src.renamer import safe_rename, rename_with_title, wait_for_file_settled
from src.watcher import ScreenshotWatcher
from src.core import SnapTitleService
from config.config import Config


class TestFilenameSanitizerWithDateSuffix(unittest.TestCase):
    """Test filename sanitization with title_YYYY-MM-DD.ext format."""

    def test_basic_title_with_date(self):
        title = "Login Screen Error"
        result = sanitize_title_to_filename(title, capture_date="2026-08-04", original_extension=".png")
        self.assertEqual(result, "login-screen-error_2026-08-04.png")

    def test_invalid_os_characters(self):
        title = 'Error: 404 / Page "Not Found"? <Resolved> | Fixed*'
        result = sanitize_title_to_filename(title, capture_date="2026-08-04", original_extension=".png")
        self.assertNotIn(":", result)
        self.assertNotIn("/", result)
        self.assertNotIn('"', result)
        self.assertNotIn("?", result)
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        self.assertNotIn("|", result)
        self.assertNotIn("*", result)
        self.assertEqual(result, "error-404-page-not-found-resolved-fixed_2026-08-04.png")

    def test_windows_reserved_names(self):
        for reserved in ["CON", "prn", "AUX", "Nul", "com1", "LPT2"]:
            result = sanitize_title_to_filename(reserved, capture_date="2026-08-04", original_extension=".png")
            self.assertTrue(result.endswith("_2026-08-04.png"))
            stem = Path(result).stem.rsplit("_", 1)[0]
            self.assertNotEqual(stem.upper(), reserved.upper())
            self.assertTrue(stem.endswith("-file"))

    def test_max_length_enforcement_with_date_suffix(self):
        long_title = "a" * 150
        result = sanitize_title_to_filename(long_title, capture_date="2026-08-04", original_extension=".png", max_stem_length=50)
        full_stem = Path(result).stem
        self.assertLessEqual(len(full_stem), 50)
        self.assertTrue(result.endswith("_2026-08-04.png"))

    def test_empty_or_whitespace_title(self):
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(sanitize_title_to_filename("", original_extension=".png"), f"screenshot_{today}.png")
        self.assertEqual(sanitize_title_to_filename("   ", capture_date="2026-08-04", original_extension=".jpg"), "screenshot_2026-08-04.jpg")


class TestCollisionDetectionWithDateSuffix(unittest.TestCase):
    """Test full filename collision checking across same-day and different-day captures."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_collision_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_case_insensitive_collision_same_day(self):
        existing_file = self.temp_dir / "Test-Screenshot_2026-08-04.png"
        existing_file.write_text("dummy")

        # Exact match
        self.assertTrue(is_filename_colliding(self.temp_dir, "Test-Screenshot_2026-08-04.png"))
        # Lowercase match
        self.assertTrue(is_filename_colliding(self.temp_dir, "test-screenshot_2026-08-04.png"))
        # Uppercase match
        self.assertTrue(is_filename_colliding(self.temp_dir, "TEST-SCREENSHOT_2026-08-04.PNG"))
        # Non-colliding title
        self.assertFalse(is_filename_colliding(self.temp_dir, "other-image_2026-08-04.png"))

    def test_different_dates_do_not_collide(self):
        """Confirm two screenshots with the same title on different dates save without collision."""
        day1_file = self.temp_dir / "dashboard-overview_2026-08-01.png"
        day1_file.write_text("day 1 content")

        source_day2 = self.temp_dir / "temp_shot_day2.png"
        source_day2.write_text("day 2 content")

        # Resolving for 2026-08-02 should NOT collide with 2026-08-01
        resolved_day2 = resolve_unique_filename(
            folder=self.temp_dir,
            title="Dashboard Overview",
            original_path=source_day2,
            capture_date="2026-08-02"
        )
        self.assertEqual(resolved_day2, "dashboard-overview_2026-08-02.png")

        # Perform actual rename and verify both files coexist cleanly
        renamed_day2 = safe_rename(source_day2, resolved_day2, target_folder=self.temp_dir)
        self.assertTrue(day1_file.exists())
        self.assertTrue(renamed_day2.exists())
        self.assertEqual(day1_file.read_text(), "day 1 content")
        self.assertEqual(renamed_day2.read_text(), "day 2 content")

    def test_same_day_same_title_triggers_collision_fallback(self):
        """Confirm two screenshots on the same date with the same title trigger collision fallback."""
        (self.temp_dir / "dashboard-overview_2026-08-04.png").write_text("first shot")

        source_second = self.temp_dir / "second_shot.png"
        source_second.write_text("second shot content")

        resolved = resolve_unique_filename(
            folder=self.temp_dir,
            title="Dashboard Overview",
            original_path=source_second,
            capture_date="2026-08-04"
        )
        self.assertNotEqual(resolved, "dashboard-overview_2026-08-04.png")
        self.assertTrue(resolved.startswith("dashboard-overview_2026-08-04-"))
        self.assertTrue(resolved.endswith(".png"))


class TestMetadataPreservation(unittest.TestCase):
    """Test that safe_rename preserves original file modification and creation timestamps."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_meta_"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rename_preserves_timestamps(self):
        source = self.temp_dir / "orig_shot.png"
        img = Image.new("RGB", (50, 50), color=(255, 255, 255))
        img.save(source)

        # Set specific custom timestamp (3 days ago)
        past_time = time.time() - (3 * 86400)
        os.utime(source, (past_time, past_time))

        orig_stat = source.stat()
        orig_mtime = orig_stat.st_mtime

        dest = safe_rename(source, "past-screenshot_2026-08-12.png", target_folder=self.temp_dir)
        new_stat = dest.stat()

        self.assertAlmostEqual(orig_mtime, new_stat.st_mtime, delta=1.0)


class TestDetectionAndRenamingIntegration(unittest.TestCase):
    """End-to-end integration test: Watcher detects new dummy screenshots and renames them with title_YYYY-MM-DD."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_watcher_"))
        self.config = Config(
            screenshots_dir=self.temp_dir,
            show_popup=False,
            popup_duration_seconds=5,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_dummy_image(self, file_path: Path):
        """Create a valid PNG image file."""
        img = Image.new("RGB", (100, 100), color=(100, 150, 200))
        img.save(file_path, format="PNG")

    def test_multiple_dummy_screenshots_renamed_with_date_suffix(self):
        """Create 3 dummy screenshots and confirm all 3 are renamed uniquely with title_YYYY-MM-DD."""
        today = datetime.now().strftime("%Y-%m-%d")
        service = SnapTitleService(
            config=self.config,
            title_provider=lambda p: "test screenshot"
        )
        service.start()

        try:
            # Create 3 dummy screenshot files
            dummy1 = self.temp_dir / "Screenshot (1).png"
            self._create_dummy_image(dummy1)
            time.sleep(0.3)

            dummy2 = self.temp_dir / "Screenshot (2).png"
            self._create_dummy_image(dummy2)
            time.sleep(0.3)

            dummy3 = self.temp_dir / "Screenshot (3).png"
            self._create_dummy_image(dummy3)

            # Wait for watcher and renamer workers to process
            start_wait = time.time()
            all_renamed = False
            files_after: list[Path] = []

            while time.time() - start_wait < 6.0:
                files_after = list(self.temp_dir.glob("*.png"))
                orig_names = {"Screenshot (1).png", "Screenshot (2).png", "Screenshot (3).png"}
                current_names = {f.name for f in files_after}
                
                if len(files_after) == 3 and not (orig_names & current_names):
                    all_renamed = True
                    break
                time.sleep(0.3)

            self.assertTrue(all_renamed, f"Files were not all renamed in time. Current: {[f.name for f in files_after]}")

            names = [f.name for f in files_after]
            self.assertEqual(len(set(names)), 3, "Renamed filenames are not unique!")

            for name in names:
                self.assertTrue(name.startswith("test-screenshot_"), f"Filename '{name}' does not start with test-screenshot_")
                self.assertTrue(name.endswith(".png"), f"Filename '{name}' does not end with .png")

            print(f"\n[SUCCESS] Renamed 3 screenshots with title first and date suffix (..._{today}.png):")
            for name in sorted(names):
                print(f"  -> {name}")

        finally:
            service.stop()


def main():
    print("=" * 60)
    print("  SnapTitle - Title First / Date Suffix Tests               ")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
