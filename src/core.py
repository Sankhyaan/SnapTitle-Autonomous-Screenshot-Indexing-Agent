"""SnapTitle core orchestrator: Detection, OCR/VLM Titling, Smart Duplicate Disambiguation, Popup UI, SQLite FTS5 Indexing, and Safe Renaming."""

import sys
import time
import logging
from pathlib import Path
from typing import Optional, Callable, Tuple

from .naming import (
    resolve_unique_filename,
    sanitize_title_to_filename,
    is_filename_colliding,
    get_file_capture_date,
)
from .renamer import safe_rename, rename_with_title
from .watcher import ScreenshotWatcher
from .ocr import extract_text_from_image, has_meaningful_text
from .llm import generate_title_from_text, generate_disambiguated_title, clean_llm_response
from .vlm import generate_caption_from_image
from .gemini import generate_title_and_caption_with_gemini
from .popup import PopupManager
from .database import DatabaseManager
from config.config import Config, load_config

logger = logging.getLogger("snaptitle.core")


class SnapTitleService:
    """Core service orchestrating screenshot detection, OCR/VLM titling, Popup UI, database indexing, and safe renaming."""

    def __init__(
        self,
        config: Optional[Config] = None,
        title_provider: Optional[Callable[[Path], Optional[str]]] = None
    ):
        """Initialize the SnapTitle service.

        Args:
            config: Optional Config instance; defaults to load_config().
            title_provider: Optional custom title override function for testing.
        """
        self.config = config or load_config()
        self.title_provider = title_provider
        self.popup_manager: Optional[PopupManager] = None

        # Initialize SQLite database indexer
        self.db = DatabaseManager(self.config.database_path)

        # Initialize Popup UI if enabled
        if self.config.show_popup:
            try:
                self.popup_manager = PopupManager()
            except Exception as e:
                logger.warning(f"Could not initialize PopupManager: {e}. Running in non-GUI mode.")

        # Initialize Watcher
        self.watcher = ScreenshotWatcher(
            watch_dir=self.config.screenshots_dir,
            on_new_screenshot=self._process_screenshot
        )

    def generate_title_and_context_for_screenshot(self, screenshot_path: Path) -> Tuple[str, str]:
        """Run the titling pipeline and return (title, context_content).

        Pipeline Strategy:
        1. If Gemini AI provider is enabled with an API key, run direct Multimodal Vision.
        2. Otherwise (or as fallback), run local dual-path OCR + VLM (Tesseract + Ollama).
        3. Pre-Popup Collision Disambiguation.
        4. Error Resilience: safe fallback if all providers fail.

        Args:
            screenshot_path: Path to the screenshot file.

        Returns:
            Tuple[str, str]: (Resolved title string, Extracted text or caption content)
        """
        # If custom title provider is supplied (e.g. for testing overrides), use it
        if self.title_provider is not None:
            custom_title = self.title_provider(screenshot_path)
            if custom_title:
                return custom_title, "Custom title override"

        # Step 0: Google Gemini Multimodal Vision (High Accuracy & Fast)
        if getattr(self.config, "ai_provider", "gemini") == "gemini" and getattr(self.config, "gemini_api_key", None):
            try:
                gemini_res = generate_title_and_caption_with_gemini(
                    image_path=screenshot_path,
                    api_key=self.config.gemini_api_key,
                    model=getattr(self.config, "gemini_model", "gemini-3.7-flash"),
                    timeout=8.0,
                    max_retries=1
                )
                if gemini_res:
                    gemini_title, gemini_content = gemini_res
                    logger.info(f"Gemini resolved title for '{screenshot_path.name}': '{gemini_title}'")
                    return gemini_title, gemini_content
            except Exception as gemini_err:
                logger.warning(f"Gemini processing error: {gemini_err}. Falling back to local OCR/VLM pipeline.")

        context_text = ""
        initial_title: Optional[str] = None

        # Step 1: Fast OCR Extraction with error handling
        try:
            ocr_text = extract_text_from_image(
                screenshot_path,
                tesseract_cmd=self.config.tesseract_cmd
            )
        except Exception as ocr_err:
            logger.warning(f"OCR extraction encountered error for '{screenshot_path.name}': {ocr_err}")
            ocr_text = ""

        # Step 2: Dual-Path Titling
        if has_meaningful_text(ocr_text, min_chars=5):
            # -------------------------------------------------------------
            # Branch A: Text-Heavy Path (OCR -> LLM)
            # -------------------------------------------------------------
            context_text = ocr_text
            logger.info(f"Text detected ({len(ocr_text)} chars) in '{screenshot_path.name}'. Using Text -> LLM path.")
            try:
                initial_title = generate_title_from_text(
                    ocr_text=ocr_text,
                    model=self.config.llm_model,
                    host=self.config.ollama_host
                )
            except Exception as llm_err:
                logger.warning(f"LLM call failed on OCR text: {llm_err}")

            # Fallback to OCR text snippet if LLM is offline or returned None
            if not initial_title and ocr_text:
                fallback_title = clean_llm_response(ocr_text, max_words=6)
                if fallback_title:
                    logger.info(f"LLM unavailable; extracted OCR fallback title: '{fallback_title}'")
                    initial_title = fallback_title
        else:
            # -------------------------------------------------------------
            # Branch B: No-Text / Sparse Path (VLM Caption -> LLM Title)
            # -------------------------------------------------------------
            logger.info(
                f"No meaningful text found in '{screenshot_path.name}'. Routing to Vision (VLM) fallback path..."
            )
            try:
                caption = generate_caption_from_image(
                    image_path=screenshot_path,
                    model=self.config.vlm_model,
                    host=self.config.ollama_host
                )

                if caption:
                    context_text = f"Image description: {caption}"
                    logger.info(f"Passing VLM caption to LLM for final titling: '{caption}'")
                    initial_title = generate_title_from_text(
                        ocr_text=context_text,
                        model=self.config.llm_model,
                        host=self.config.ollama_host
                    )
                    if not initial_title:
                        fallback_title = clean_llm_response(caption, max_words=6)
                        if fallback_title:
                            initial_title = fallback_title
                else:
                    logger.warning("VLM captioning returned empty.")

            except Exception as vlm_err:
                logger.warning(f"VLM pipeline encountered an error: {vlm_err}")

        current_title = initial_title or "screenshot"

        # Step 3: Smart Duplicate Disambiguation (Phase 5)
        capture_date = get_file_capture_date(screenshot_path)
        ext = screenshot_path.suffix or ".png"
        candidate_filename = sanitize_title_to_filename(
            title=current_title,
            capture_date=capture_date,
            original_extension=ext
        )

        if is_filename_colliding(self.config.screenshots_dir, candidate_filename, ignore_path=screenshot_path):
            logger.info(
                f"Filename collision detected for candidate '{candidate_filename}'. "
                f"Requesting smart LLM disambiguation..."
            )
            
            for attempt in range(1, 3):
                try:
                    alt_title = generate_disambiguated_title(
                        colliding_title=current_title,
                        context_text=context_text or current_title,
                        model=self.config.llm_model,
                        host=self.config.ollama_host
                    )

                    if alt_title:
                        alt_filename = sanitize_title_to_filename(
                            title=alt_title,
                            capture_date=capture_date,
                            original_extension=ext
                        )
                        if not is_filename_colliding(self.config.screenshots_dir, alt_filename, ignore_path=screenshot_path):
                            logger.info(
                                f"Smart collision resolution succeeded on attempt {attempt}/2: "
                                f"'{current_title}' -> '{alt_title}'"
                            )
                            return alt_title, context_text
                        else:
                            current_title = alt_title
                except Exception as disambig_err:
                    logger.warning(f"LLM disambiguation attempt {attempt} failed: {disambig_err}")

        return current_title, context_text

    def generate_title_for_screenshot(self, screenshot_path: Path) -> str:
        """Helper returning title string."""
        title, _ = self.generate_title_and_context_for_screenshot(screenshot_path)
        return title

    def _process_screenshot(self, screenshot_path: Path) -> Optional[Path]:
        """Handle a newly detected screenshot file end-to-end.

        1. Displays popup in loading state if popup UI enabled.
        2. Resolves title (OCR/VLM + smart disambiguation) and content context.
        3. Updates popup with AI title, allowing user edit / auto-save countdown.
        4. Resolves unique, sanitized, non-colliding filename (YYYY-MM-DD_title.ext).
        5. Safely renames the screenshot file in place with metadata preservation.
        6. Logs screenshot into SQLite database and FTS5 search index.
        7. Marks the target path ignored in watcher to prevent re-trigger loops.
        """
        try:
            logger.info(f"Processing detected screenshot: {screenshot_path.name}")
            orig_filename = screenshot_path.name
            capture_date = get_file_capture_date(screenshot_path)
            extracted_content_holder = [""]

            def title_resolver() -> str:
                title, content = self.generate_title_and_context_for_screenshot(screenshot_path)
                extracted_content_holder[0] = content
                return title

            # Step 1 & 2: Obtain Title (via Popup UI or direct resolution)
            if self.popup_manager and self.config.show_popup:
                title = self.popup_manager.show_popup_and_wait(
                    image_path=screenshot_path,
                    title_resolver=title_resolver,
                    duration_seconds=self.config.popup_duration_seconds,
                    fallback_title="screenshot"
                )
            else:
                title = title_resolver()
            
            # Verify file still exists before renaming (in case deleted or moved externally)
            if not screenshot_path.exists():
                logger.warning(f"Screenshot no longer exists on disk: {screenshot_path}")
                return None

            # Step 3: Resolve unique collision-free filename (YYYY-MM-DD_title.ext)
            target_filename = resolve_unique_filename(
                folder=self.config.screenshots_dir,
                title=title,
                original_path=screenshot_path,
                capture_date=capture_date
            )
            
            target_path = self.config.screenshots_dir / target_filename
            
            # Step 4: Mark destination path as ignored before renaming
            self.watcher.mark_ignored(target_path)
            
            # Step 5: Perform safe atomic rename with metadata preservation
            renamed_path = safe_rename(
                source_path=screenshot_path,
                target_filename=target_filename,
                target_folder=self.config.screenshots_dir
            )
            
            # Ensure renamed path is also marked ignored
            self.watcher.mark_ignored(renamed_path)

            # Step 6: Log screenshot into SQLite database & FTS5 search index
            try:
                self.db.log_screenshot(
                    original_filename=orig_filename,
                    final_filename=renamed_path.name,
                    file_path=renamed_path,
                    title=title,
                    extracted_content=extracted_content_holder[0],
                    capture_date=capture_date
                )
            except Exception as db_err:
                logger.error(f"Failed to log screenshot to database: {db_err}", exc_info=True)
            
            logger.info(f"Successfully processed: '{orig_filename}' -> '{renamed_path.name}'")
            return renamed_path

        except Exception as e:
            logger.error(f"Failed to process screenshot '{screenshot_path}': {e}", exc_info=True)
            return None

    def undo_last_rename(self) -> Tuple[bool, str, Optional[Path], Optional[Path]]:
        """Revert the most recent screenshot rename."""
        return self.db.undo_last_rename()

    def search_screenshots(self, query: str, limit: int = 20):
        """Search screenshot database for matching query text."""
        return self.db.search(query, limit=limit)

    def start(self):
        """Start the background screenshot watcher service."""
        logger.info(f"Starting SnapTitle Service watching: {self.config.screenshots_dir}")
        self.watcher.start()

    def stop(self):
        """Stop the background screenshot watcher service."""
        logger.info("Stopping SnapTitle Service...")
        self.watcher.stop()

    def get_watcher_status(self) -> dict:
        """Return the watcher's current diagnostic status."""
        return self.watcher.get_status()

    def get_service_status(self) -> dict:
        """Return a summary of the full service state for diagnostics.

        Returns:
            dict: Service status including watcher state, database path, and config summary.
        """
        return {
            "watcher": self.get_watcher_status(),
            "database_path": str(self.config.database_path),
            "screenshots_dir": str(self.config.screenshots_dir),
            "popup_enabled": self.config.show_popup,
            "llm_model": self.config.llm_model,
            "vlm_model": self.config.vlm_model,
        }


def main():
    """CLI entry point for running SnapTitle daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    config = load_config()
    print("=" * 60)
    print("  SnapTitle - Desktop Screenshot Automation Daemon")
    print("=" * 60)
    print(f"Screenshots folder : {config.screenshots_dir}")
    print(f"Popup UI           : {'Enabled (' + str(config.popup_duration_seconds) + 's)' if config.show_popup else 'Disabled'}")
    print(f"Text LLM Model     : {config.llm_model}")
    print(f"Vision VLM Model   : {config.vlm_model}")
    print(f"Database Path      : {config.database_path}")
    print(f"Tesseract Binary   : {config.tesseract_cmd or 'Auto-detected'}")
    print("Press Ctrl+C to stop...\n")

    service = SnapTitleService(config=config)
    service.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping SnapTitle...")
        service.stop()
        print("SnapTitle stopped.")


if __name__ == "__main__":
    main()
