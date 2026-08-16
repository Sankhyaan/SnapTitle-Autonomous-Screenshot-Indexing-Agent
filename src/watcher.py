"""Filesystem watcher using Watchdog to detect new screenshot images."""

import os
import time
import logging
import threading
from pathlib import Path
from typing import Callable, Set, Optional, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from .renamer import wait_for_file_settled

logger = logging.getLogger("snaptitle.watcher")

# Supported image file extensions for screenshots
SUPPORTED_IMAGE_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif",
    ".jfif", ".heic", ".heif", ".avif", ".dib"
}

# Temporary or intermediate file patterns to ignore
IGNORED_SUFFIXES: Set[str] = {
    ".tmp", ".crdownload", ".part", ".swp", ".lock", ".temp"
}


def is_supported_image(file_path: Path) -> bool:
    """Check if the given path has a supported screenshot image extension.

    Args:
        file_path: File path to inspect.

    Returns:
        bool: True if extension is in SUPPORTED_IMAGE_EXTENSIONS, False otherwise.
    """
    return file_path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


class ScreenshotEventHandler(FileSystemEventHandler):
    """Event handler for capturing new screenshot image files."""

    def __init__(
        self,
        on_new_screenshot: Callable[[Path], None],
        ignore_cache_ttl: float = 15.0
    ):
        super().__init__()
        self.on_new_screenshot = on_new_screenshot
        self.ignore_cache_ttl = ignore_cache_ttl
        
        # Track recently processed/renamed files to prevent infinite loops: {path_str: timestamp}
        self._processed_files: Dict[str, float] = {}
        self._lock = threading.Lock()

    def mark_as_ignored(self, path: Path):
        """Mark a file path to be ignored by the watcher (e.g. when SnapTitle renames it)."""
        with self._lock:
            self._cleanup_old_cache()
            self._processed_files[str(path.resolve())] = time.time()
            self._processed_files[str(path.absolute())] = time.time()

    def is_ignored(self, path: Path) -> bool:
        """Check if a path was recently processed or explicitly ignored."""
        with self._lock:
            self._cleanup_old_cache()
            p_res = str(path.resolve())
            p_abs = str(path.absolute())
            return p_res in self._processed_files or p_abs in self._processed_files

    def get_ignored_count(self) -> int:
        """Return the number of currently tracked ignored paths in cache."""
        with self._lock:
            self._cleanup_old_cache()
            return len(self._processed_files)

    def clear_ignored_cache(self) -> None:
        """Clear all entries from the ignored files cache."""
        with self._lock:
            self._processed_files.clear()

    def _cleanup_old_cache(self) -> None:
        """Purge cache entries older than ignore_cache_ttl."""
        now = time.time()
        expired = [k for k, ts in self._processed_files.items() if now - ts > self.ignore_cache_ttl]
        for k in expired:
            del self._processed_files[k]

    def _is_candidate_image(self, file_path: Path) -> bool:
        """Check if a file path qualifies as a newly created screenshot image."""
        # Ignore temporary / hidden files
        if file_path.name.startswith((".", "~$")):
            return False

        ext = file_path.suffix.lower()
        if ext in IGNORED_SUFFIXES:
            return False

        if not is_supported_image(file_path):
            return False

        return True

    def _handle_candidate_file(self, file_path: Path):
        """Process candidate file in a background worker to avoid blocking the watchdog observer."""
        if not self._is_candidate_image(file_path):
            return

        if self.is_ignored(file_path):
            logger.debug(f"Ignoring previously handled/renamed file: {file_path.name}")
            return

        # Mark immediately to prevent duplicate triggers while waiting for file settling
        self.mark_as_ignored(file_path)

        def worker():
            try:
                # Wait for OS / screenshot tool to complete writing the file
                if not wait_for_file_settled(file_path, timeout=3.0):
                    logger.warning(f"File did not settle within timeout: {file_path}")
                    return

                if not file_path.exists():
                    logger.debug(f"File vanished before processing: {file_path}")
                    return

                logger.info(f"New screenshot detected: {file_path.name}")
                self.on_new_screenshot(file_path)

            except Exception as err:
                logger.error(f"Error handling detected screenshot '{file_path}': {err}", exc_info=True)

        threading.Thread(target=worker, daemon=True).start()

    def on_created(self, event: FileCreatedEvent):
        """Watchdog callback when a new file is created."""
        if event.is_directory:
            return
        self._handle_candidate_file(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent):
        """Watchdog callback when a file is moved/renamed into the directory (e.g. from tmp)."""
        if event.is_directory:
            return
        dest = Path(event.dest_path)
        if not self.is_ignored(dest):
            self._handle_candidate_file(dest)


class ScreenshotWatcher:
    """Manager for watching the screenshot directory."""

    def __init__(
        self,
        watch_dir: Path,
        on_new_screenshot: Callable[[Path], None]
    ):
        self.watch_dir = Path(watch_dir)
        self.on_new_screenshot = on_new_screenshot
        self.handler = ScreenshotEventHandler(on_new_screenshot=on_new_screenshot)
        self.observer = Observer()
        self._is_running = False

    def start(self):
        """Start monitoring the screenshot directory."""
        if self._is_running:
            return

        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(self.handler, path=str(self.watch_dir), recursive=False)
        self.observer.start()
        self._is_running = True
        logger.info(f"Started screenshot watcher on: {self.watch_dir}")

    def stop(self):
        """Stop monitoring the screenshot directory."""
        if not self._is_running:
            return

        self.observer.stop()
        self.observer.join(timeout=2.0)
        self._is_running = False
        logger.info("Stopped screenshot watcher.")

    @property
    def is_running(self) -> bool:
        return self._is_running

    def mark_ignored(self, path: Path):
        """Mark a path to be ignored by this watcher instance."""
        self.handler.mark_as_ignored(path)

    def clear_ignored_cache(self):
        """Clear the watcher's internal ignored file cache."""
        self.handler.clear_ignored_cache()
