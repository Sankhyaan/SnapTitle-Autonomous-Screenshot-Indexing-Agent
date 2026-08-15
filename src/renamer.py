"""Safe file renaming and atomic move operations with Windows lock retry and metadata preservation."""

import os
import time
import shutil
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Union

from .naming import resolve_unique_filename, get_file_capture_date

logger = logging.getLogger("snaptitle.renamer")


def wait_for_file_settled(
    file_path: Path,
    timeout: float = 2.5,
    poll_interval: float = 0.1,
    min_stable_duration: float = 0.2
) -> bool:
    """Wait until a file has finished being written by the OS/screenshot tool and is unlocked.

    Args:
        file_path: Path to the target file.
        timeout: Maximum seconds to wait.
        poll_interval: Polling frequency in seconds.
        min_stable_duration: Required time with stable non-zero file size.

    Returns:
        bool: True if file is ready and accessible, False if timeout reached.
    """
    start_time = time.time()
    last_size = -1
    stable_since: Optional[float] = None

    while time.time() - start_time < timeout:
        if not file_path.exists():
            time.sleep(poll_interval)
            continue

        try:
            current_size = file_path.stat().st_size
            
            # File must not be 0 bytes (unless an empty file is truly stable)
            if current_size > 0 and current_size == last_size:
                if stable_since is None:
                    stable_since = time.time()
                elif (time.time() - stable_since) >= min_stable_duration:
                    # Attempt a test open in append mode to confirm no write locks
                    with open(file_path, "a+b"):
                        pass
                    return True
            else:
                last_size = current_size
                stable_since = None
        except (OSError, PermissionError):
            # File is currently locked by another process
            stable_since = None

        time.sleep(poll_interval)

    return file_path.exists() and file_path.stat().st_size > 0


def safe_rename(
    source_path: Path,
    target_filename: str,
    target_folder: Optional[Path] = None,
    max_retries: int = 5,
    initial_delay: float = 0.1
) -> Path:
    """Safely rename or move a screenshot file to target_filename with lock retry logic and metadata preservation.

    Preserves the original file's creation and modification timestamps.

    Args:
        source_path: The existing screenshot file path.
        target_filename: The target filename (e.g. '2026-08-15_error-404.png').
        target_folder: Optional target directory; defaults to source_path.parent.
        max_retries: Number of attempts to handle transient OS file locks.
        initial_delay: Initial retry backoff delay in seconds.

    Returns:
        Path: The new destination path of the renamed file.

    Raises:
        FileNotFoundError: If source_path does not exist.
        OSError: If renaming fails after all retries.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source file does not exist: {source_path}")

    # Capture original timestamps before rename
    orig_stat = source_path.stat()
    orig_atime = orig_stat.st_atime
    orig_mtime = orig_stat.st_mtime

    dest_folder = target_folder or source_path.parent
    dest_path = dest_folder / target_filename

    # If source and destination are identical, nothing to do
    if source_path.resolve() == dest_path.resolve():
        logger.info(f"Source and destination are identical: {source_path}")
        return dest_path

    delay = initial_delay
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            # os.replace provides atomic rename on POSIX and Windows
            os.replace(source_path, dest_path)
            # Ensure modification and access timestamps are preserved
            try:
                os.utime(dest_path, (orig_atime, orig_mtime))
            except Exception:
                pass
            logger.info(f"Successfully renamed '{source_path.name}' -> '{dest_path.name}'")
            return dest_path
        except (PermissionError, OSError) as err:
            last_error = err
            logger.debug(
                f"Rename attempt {attempt}/{max_retries} failed for '{source_path.name}' -> '{dest_path.name}': {err}"
            )
            time.sleep(delay)
            delay *= 1.5

    # Fallback to shutil.move if os.replace persistently encountered permission issues
    try:
        shutil.move(str(source_path), str(dest_path))
        try:
            os.utime(dest_path, (orig_atime, orig_mtime))
        except Exception:
            pass
        logger.info(f"Fallback move succeeded: '{source_path.name}' -> '{dest_path.name}'")
        return dest_path
    except Exception as final_err:
        logger.error(f"Failed to rename '{source_path}' to '{dest_path}': {final_err}")
        raise last_error or final_err


def rename_with_title(
    source_path: Path,
    title: str,
    target_folder: Optional[Path] = None,
    capture_date: Optional[Union[str, datetime, date]] = None
) -> Path:
    """End-to-end helper to sanitize title, resolve duplicates, and safely rename file with date prefix.

    Args:
        source_path: Original screenshot file path.
        title: Raw title string (manual or AI-generated).
        target_folder: Optional target folder; defaults to source_path.parent.
        capture_date: Optional capture date string/datetime.

    Returns:
        Path: The resulting renamed file path.
    """
    folder = target_folder or source_path.parent
    final_filename = resolve_unique_filename(
        folder=folder,
        title=title,
        original_path=source_path,
        capture_date=capture_date
    )
    return safe_rename(source_path, final_filename, target_folder=folder)
