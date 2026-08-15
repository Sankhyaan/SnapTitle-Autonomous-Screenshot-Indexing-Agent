"""Unit and integration tests for Phase 6: Database Storage, FTS5 Search Index, and Undo."""

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

from src.database import DatabaseManager
from src.core import SnapTitleService
from config.config import Config


def create_sample_image(output_path: Path, lines: list[str]) -> Path:
    """Create a high-contrast test screenshot with custom lines."""
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    y = 20
    for line in lines:
        draw.text((20, y), line, fill=(0, 0, 0))
        y += 40
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


class TestDatabaseAndFTS5Search(unittest.TestCase):
    """Test SQLite schema, FTS5 full-text indexing, and search queries."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_db_"))
        self.db_path = self.temp_dir / "test_snaptitle.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_and_fts_search(self):
        """Test logging multiple screenshots and searching via FTS5 tokens."""
        # Log 1: npm error log
        self.db.log_screenshot(
            original_filename="Screenshot 1.png",
            final_filename="npm-install-eacces-permission-error_2026-08-15.png",
            file_path=self.temp_dir / "npm-install-eacces-permission-error_2026-08-15.png",
            title="npm install EACCES error",
            extracted_content="npm ERR! code EACCES npm ERR! syscall access npm ERR! path /usr/local/lib/node_modules",
            capture_date="2026-08-15"
        )

        # Log 2: Cloud Invoice
        self.db.log_screenshot(
            original_filename="Screenshot 2.png",
            final_filename="aws-monthly-billing-invoice_2026-08-15.png",
            file_path=self.temp_dir / "aws-monthly-billing-invoice_2026-08-15.png",
            title="AWS Monthly Billing Invoice",
            extracted_content="Amazon Web Services Invoice #AWS-9942 Total Due $415.00 Account ID 98214",
            capture_date="2026-08-15"
        )

        # Search for "npm error"
        results_npm = self.db.search("npm error")
        self.assertEqual(len(results_npm), 1)
        self.assertEqual(results_npm[0]["title"], "npm install EACCES error")

        # Search for "Invoice 415"
        results_invoice = self.db.search("Invoice 415")
        self.assertEqual(len(results_invoice), 1)
        self.assertEqual(results_invoice[0]["final_filename"], "aws-monthly-billing-invoice_2026-08-15.png")

        # Search for non-existent term
        results_empty = self.db.search("nonexistentterm123")
        self.assertEqual(len(results_empty), 0)

    def test_undo_last_rename(self):
        """Test undo_last_rename restores the original filename on disk."""
        orig_file = self.temp_dir / "Screenshot (Original).png"
        orig_file.write_text("dummy image data")

        renamed_path = self.temp_dir / "renamed-screenshot_2026-08-15.png"
        shutil.move(orig_file, renamed_path)

        self.db.log_screenshot(
            original_filename="Screenshot (Original).png",
            final_filename="renamed-screenshot_2026-08-15.png",
            file_path=renamed_path,
            title="Renamed Screenshot",
            extracted_content="Some content",
            capture_date="2026-08-15"
        )

        # Confirm renamed file exists
        self.assertTrue(renamed_path.exists())
        self.assertFalse(orig_file.exists())

        # Execute Undo
        success, msg, current_p, restored_p = self.db.undo_last_rename()
        self.assertTrue(success)
        print(f"\n[Undo Test] {msg}")

        # Confirm original file was restored on disk
        self.assertTrue(orig_file.exists())
        self.assertFalse(renamed_path.exists())

        # Attempt second undo when no more active renames exist
        success_2, msg_2, _, _ = self.db.undo_last_rename()
        self.assertFalse(success_2)


class TestEndToEndPhase6Pipeline(unittest.TestCase):
    """End-to-end watcher test verifying Detection -> AI Titling -> Renaming -> DB Indexing -> Search."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_e2e_p6_"))
        self.db_path = self.temp_dir / "data" / "snaptitle.db"
        self.config = Config(
            screenshots_dir=self.temp_dir,
            show_popup=False,
            database_path=self.db_path
        )
        self.service = SnapTitleService(config=self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pipeline_indexes_and_is_searchable(self):
        """Test processing a screenshot indexes it in SQLite and makes it instantly searchable."""
        self.service.start()
        try:
            shot_file = self.temp_dir / "Screenshot_Postgres.png"
            create_sample_image(shot_file, [
                "PostgreSQL Database Connection Error",
                "Connection refused to host db-primary on port 5432",
                "FATAL: terminating connection due to administrator command"
            ])

            # Wait for watcher processing
            start_wait = time.time()
            renamed: Path | None = None
            while time.time() - start_wait < 15.0:
                files = list(self.temp_dir.glob("*.png"))
                for f in files:
                    if f.name != "Screenshot_Postgres.png":
                        renamed = f
                        break
                if renamed:
                    break
                time.sleep(0.3)

            # Wait for database index entry to commit
            start_db = time.time()
            search_results = []
            while time.time() - start_db < 5.0:
                search_results = self.service.search_screenshots("PostgreSQL Connection")
                if search_results:
                    break
                time.sleep(0.3)

            self.assertGreaterEqual(len(search_results), 1, "Expected search to find indexed screenshot.")
            first_match = search_results[0]
            self.assertEqual(first_match["final_filename"], renamed.name)
            print(f"[E2E Pipeline Test] Search Match Found: Title='{first_match['title']}' | Path='{first_match['file_path']}'")

        finally:
            self.service.stop()


def main():
    print("=" * 60)
    print("  SnapTitle - Phase 6 Database, Search & Undo Tests         ")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
