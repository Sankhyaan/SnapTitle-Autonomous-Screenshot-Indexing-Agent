"""Integration and unit tests for Phase 3: Vision-Language Model (VLM) Fallback."""

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

from src.ocr import extract_text_from_image, has_meaningful_text
from src.vlm import generate_caption_from_image
from src.core import SnapTitleService
from config.config import load_config, Config


def create_landscape_image(output_path: Path) -> Path:
    """Generate a textless photo/landscape (sky, sun, mountains/hills)."""
    img = Image.new("RGB", (600, 400), color=(135, 206, 235))  # Sky blue
    draw = ImageDraw.Draw(img)

    # Golden Sun
    draw.ellipse([(420, 40), (520, 140)], fill=(255, 215, 0), outline=(255, 165, 0))

    # Rolling green hills/mountains
    draw.polygon([(0, 400), (150, 200), (350, 400)], fill=(34, 139, 34))
    draw.polygon([(200, 400), (450, 180), (600, 400)], fill=(46, 170, 46))
    draw.rectangle([(0, 320), (600, 400)], fill=(50, 205, 50))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


def create_icon_ui_image(output_path: Path) -> Path:
    """Generate a textless icon-only UI navigation bar."""
    img = Image.new("RGB", (600, 200), color=(30, 30, 40))  # Dark mode UI
    draw = ImageDraw.Draw(img)

    # Home icon (triangle + square)
    draw.polygon([(80, 70), (120, 40), (160, 70)], fill=(220, 220, 220))
    draw.rectangle([(90, 70), (150, 130)], fill=(220, 220, 220))

    # Search icon (magnifying glass)
    draw.ellipse([(260, 60), (310, 110)], outline=(220, 220, 220), width=6)
    draw.line([(300, 100), (330, 130)], fill=(220, 220, 220), width=6)

    # Settings gear icon (circle)
    draw.ellipse([(440, 60), (500, 120)], fill=(220, 220, 220))
    draw.ellipse([(460, 80), (480, 100)], fill=(30, 30, 40))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


def create_diagram_image(output_path: Path) -> Path:
    """Generate a textless flowchart diagram (blocks connected by arrows)."""
    img = Image.new("RGB", (600, 300), color=(240, 245, 250))
    draw = ImageDraw.Draw(img)

    # Box 1 (Blue)
    draw.rectangle([(50, 90), (180, 210)], fill=(70, 130, 240), outline=(30, 80, 180), width=3)
    
    # Arrow 1 -> 2
    draw.line([(180, 150), (250, 150)], fill=(40, 40, 60), width=5)
    draw.polygon([(250, 135), (275, 150), (250, 165)], fill=(40, 40, 60))

    # Box 2 (Orange)
    draw.rectangle([(275, 90), (405, 210)], fill=(245, 140, 50), outline=(200, 100, 20), width=3)
    
    # Arrow 2 -> 3
    draw.line([(405, 150), (475, 150)], fill=(40, 40, 60), width=5)
    draw.polygon([(475, 135), (500, 150), (475, 165)], fill=(40, 40, 60))

    # Box 3 (Green)
    draw.rectangle([(500, 90), (580, 210)], fill=(50, 190, 90), outline=(30, 140, 60), width=3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, format="PNG")
    return output_path


class TestVLMFallback(unittest.TestCase):
    """Test vision model captioning and titling for textless screenshots."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="snaptitle_test_vlm_"))
        self.config = load_config()
        self.config.screenshots_dir = self.temp_dir
        self.config.vlm_model = "moondream:latest"
        self.config.show_popup = False
        self.service = SnapTitleService(config=self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_landscape_image_titling(self):
        """Test a textless landscape/photo gets titled via VLM caption -> LLM."""
        img_path = self.temp_dir / "landscape_photo.png"
        create_landscape_image(img_path)

        # Confirm OCR finds no text
        ocr_text = extract_text_from_image(img_path, tesseract_cmd=self.config.tesseract_cmd)
        self.assertFalse(has_meaningful_text(ocr_text))

        # Generate title via dual pipeline
        title = self.service.generate_title_for_screenshot(img_path)
        print(f"\n[VLM Test 1] Landscape Photo -> Title: '{title}'")
        self.assertTrue(len(title.split()) <= 6)

    def test_icon_ui_image_titling(self):
        """Test an icon-only UI screenshot gets titled via VLM caption -> LLM."""
        img_path = self.temp_dir / "icons_ui.png"
        create_icon_ui_image(img_path)

        ocr_text = extract_text_from_image(img_path, tesseract_cmd=self.config.tesseract_cmd)
        self.assertFalse(has_meaningful_text(ocr_text))

        title = self.service.generate_title_for_screenshot(img_path)
        print(f"[VLM Test 2] Icon UI -> Title: '{title}'")
        self.assertTrue(len(title.split()) <= 6)

    def test_diagram_image_titling(self):
        """Test an unlabeled diagram gets titled via VLM caption -> LLM."""
        img_path = self.temp_dir / "diagram.png"
        create_diagram_image(img_path)

        ocr_text = extract_text_from_image(img_path, tesseract_cmd=self.config.tesseract_cmd)
        self.assertFalse(has_meaningful_text(ocr_text))

        title = self.service.generate_title_for_screenshot(img_path)
        print(f"[VLM Test 3] Diagram -> Title: '{title}'")
        self.assertTrue(len(title.split()) <= 6)

    def test_vlm_failure_graceful_fallback(self):
        """Test that if the VLM fails or times out, the service falls back gracefully to a safe title without crashing."""
        img_path = self.temp_dir / "blank.png"
        img = Image.new("RGB", (100, 100), color=(10, 10, 10))
        img.save(img_path)

        # Create service with unreachable host to simulate failure/timeout
        bad_config = Config(
            screenshots_dir=self.temp_dir,
            vlm_model="non_existent_model_xyz",
            ollama_host="http://127.0.0.1:19999"  # unused port to trigger immediate connection failure
        )
        fallback_service = SnapTitleService(config=bad_config)
        
        title = fallback_service.generate_title_for_screenshot(img_path)
        print(f"[VLM Test 4] Simulated Failure -> Fallback Title: '{title}'")
        self.assertEqual(title, "screenshot")

    def test_dual_path_end_to_end_watcher(self):
        """Test end-to-end watcher with both text screenshot (Branch A) and no-text screenshot (Branch B)."""
        self.service.start()
        try:
            # 1. Text screenshot (Branch A)
            text_shot = self.temp_dir / "Screenshot_Text.png"
            img1 = Image.new("RGB", (400, 100), color=(255, 255, 255))
            draw1 = ImageDraw.Draw(img1)
            draw1.text((20, 35), "Kubernetes Pod CrashLoopBackOff Error", fill=(0, 0, 0))
            img1.save(text_shot)

            time.sleep(1.0)

            # 2. No-text screenshot (Branch B)
            photo_shot = self.temp_dir / "Screenshot_Photo.png"
            create_landscape_image(photo_shot)

            # Wait for watcher to rename both
            start_wait = time.time()
            all_renamed = False
            files_after: list[Path] = []

            while time.time() - start_wait < 35.0:
                files_after = list(self.temp_dir.glob("*.png"))
                names = {f.name for f in files_after}
                if len(files_after) == 2 and "Screenshot_Text.png" not in names and "Screenshot_Photo.png" not in names:
                    all_renamed = True
                    break
                time.sleep(0.5)

            today = datetime.now().strftime("%Y-%m-%d")
            for f in files_after:
                self.assertTrue(f"_{today}" in f.name, f"File '{f.name}' missing date suffix '_{today}'")

            print("\n[Dual-Path E2E Success] Renamed Files:")
            for f in sorted(files_after, key=lambda x: x.name):
                print(f"  -> {f.name}")

        finally:
            self.service.stop()


def main():
    print("=" * 60)
    print("      SnapTitle - Phase 3 VLM Fallback Tests                ")
    print("=" * 60)
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
