"""Filename sanitization, date suffix assembly, collision detection, and unique name resolution."""

import os
import re
import sys
import unicodedata
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Set, Union

# Windows reserved device names (case-insensitive)
WINDOWS_RESERVED_NAMES: Set[str] = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

# Characters prohibited in filenames across Windows, macOS, and Linux
# Windows prohibits: < > : " / \ | ? * and ASCII 0-31
INVALID_CHARS_REGEX = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Date suffix pattern matching _YYYY-MM-DD
DATE_SUFFIX_REGEX = re.compile(r"_(\d{4}-\d{2}-\d{2})(?:-\d{6}(?:-\d+)?)?$")


def parse_filename_date(filename_or_path: Optional[Union[str, Path]]) -> Optional[str]:
    """Extract capture date (YYYY-MM-DD) from a managed SnapTitle filename.

    Args:
        filename_or_path: Filename string or Path object (e.g. 'error-log_2026-08-15.png').

    Returns:
        Optional[str]: Date string 'YYYY-MM-DD' if found, else None.
    """
    if not filename_or_path:
        return None
    path_obj = Path(filename_or_path)
    stem = path_obj.stem
    match = DATE_SUFFIX_REGEX.search(stem)
    if match:
        return match.group(1)
    return None


def extract_title_stem(filename_or_path: Optional[Union[str, Path]]) -> str:
    """Extract the base title slug from a managed SnapTitle filename, removing date suffix.

    Args:
        filename_or_path: Filename string or Path object (e.g. 'app-error_2026-08-15.png').

    Returns:
        str: Base title slug (e.g. 'app-error').
    """
    if not filename_or_path:
        return ""
    path_obj = Path(filename_or_path)
    stem = path_obj.stem
    cleaned = DATE_SUFFIX_REGEX.sub("", stem)
    return cleaned if cleaned else stem


def get_file_capture_date(file_path: Path) -> str:
    """Extract the original capture/creation date of a screenshot in YYYY-MM-DD format.

    Reads creation/modification metadata from the filesystem before any renaming occurs.

    Args:
        file_path: Path to the screenshot file.

    Returns:
        str: Formatted date string (e.g. '2026-08-15').
    """
    try:
        if file_path.exists():
            stat_result = file_path.stat()
            # On Windows, st_ctime is creation time; on macOS, st_birthtime is creation time
            creation_time = getattr(stat_result, "st_birthtime", None)
            if creation_time is None:
                # On Windows, st_ctime is creation time; on Unix, it is metadata change time
                if sys.platform.startswith("win"):
                    creation_time = stat_result.st_ctime
                else:
                    creation_time = stat_result.st_mtime
            
            # Use the earliest of creation and modification timestamp
            ts = min(creation_time, stat_result.st_mtime) if creation_time else stat_result.st_mtime
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        pass

    return datetime.now().strftime("%Y-%m-%d")


def sanitize_title_to_filename(
    title: str,
    capture_date: Optional[Union[str, datetime, date]] = None,
    original_extension: str = ".png",
    max_stem_length: int = 100
) -> str:
    """Convert a title string and capture date into a safe filename formatted as title_YYYY-MM-DD.ext.

    Format: sanitized-title-text_YYYY-MM-DD.png

    Conventions:
    - Appends capture date in YYYY-MM-DD format prefixed by an underscore '_'.
    - Normalizes Unicode characters.
    - Strips prohibited OS characters (< > : " / \\ | ? * and control chars).
    - Converts title text to lowercase-with-hyphens (kebab-case).
    - Collapses multiple hyphens and whitespace into a single hyphen.
    - Trims leading/trailing hyphens, periods, and spaces.
    - Prevents collisions with Windows reserved device names (e.g. CON, NUL, PRN).
    - Enforces maximum character length on the overall filename stem (accounting for date suffix).
    - Preserves the original file extension in lowercase.

    Args:
        title: The input title or description.
        capture_date: Optional capture date (str 'YYYY-MM-DD', datetime, or date). Defaults to today.
        original_extension: The file extension (including leading dot, e.g. '.png').
        max_stem_length: Maximum allowed total length for the stem including date suffix.

    Returns:
        str: Safe, sanitized filename with title first, date suffix, and extension.
    """
    max_stem_length = max(15, int(max_stem_length))
    # 1. Format date suffix (YYYY-MM-DD)
    if isinstance(capture_date, (datetime, date)):
        date_suffix = capture_date.strftime("%Y-%m-%d")
    elif isinstance(capture_date, str) and len(capture_date.strip()) >= 10:
        date_suffix = capture_date.strip()[:10]
    else:
        date_suffix = datetime.now().strftime("%Y-%m-%d")

    # 2. Sanitize title text
    if not title or not title.strip():
        title_stem = "screenshot"
    else:
        # Normalize unicode (NFKD)
        normalized = unicodedata.normalize("NFKD", title)
        
        # Replace invalid OS characters with hyphens
        cleaned = INVALID_CHARS_REGEX.sub("-", normalized)
        
        # Replace remaining unwanted symbols (keep alphanumeric, hyphens, underscores, dots)
        cleaned = re.sub(r"[^\w\s\-_.]", "-", cleaned, flags=re.UNICODE)
        
        # Convert spaces and underscores to hyphens and lowercase
        cleaned = re.sub(r"[\s_]+", "-", cleaned).lower()
        
        # Collapse multiple hyphens
        cleaned = re.sub(r"-+", "-", cleaned)
        
        # Strip leading and trailing hyphens, dots, and whitespace
        title_stem = cleaned.strip("- .")
        
        if not title_stem:
            title_stem = "screenshot"

    # Handle Windows reserved names (e.g. "con", "nul", "prn")
    if title_stem.upper() in WINDOWS_RESERVED_NAMES:
        title_stem = f"{title_stem}-file"

    # 3. Assemble full stem: title-stem_YYYY-MM-DD
    # Reserve space for date suffix (10 chars) + underscore (1 char) = 11 chars
    max_title_len = max(10, max_stem_length - len(date_suffix) - 1)
    if len(title_stem) > max_title_len:
        title_stem = title_stem[:max_title_len].rstrip("- .")
        if not title_stem:
            title_stem = "screenshot"

    full_stem = f"{title_stem}_{date_suffix}"

    # Clean and normalize extension
    ext = original_extension.lower().strip()
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ".png"

    return f"{full_stem}{ext}"


def is_filename_colliding(
    folder: Path,
    candidate_filename: str,
    ignore_path: Optional[Path] = None
) -> bool:
    """Check if candidate_filename already exists in folder (case-insensitively).

    Matches against the full filename including date suffix.

    Args:
        folder: The directory containing existing files.
        candidate_filename: The target filename to check (e.g. 'error-404_2026-08-15.png').
        ignore_path: Optional path of the source file being renamed (to avoid self-collision).

    Returns:
        bool: True if collision detected, False otherwise.
    """
    if not folder.exists() or not folder.is_dir():
        return False

    candidate_lower = candidate_filename.lower()
    ignore_resolved = ignore_path.resolve() if ignore_path and ignore_path.exists() else None

    try:
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            
            # If checking against the source file itself, skip it
            if ignore_resolved and entry.resolve() == ignore_resolved:
                continue

            if entry.name.lower() == candidate_lower:
                return True
    except OSError:
        # Fallback to direct path check if iterdir fails
        candidate_path = folder / candidate_filename
        if candidate_path.exists():
            if ignore_resolved and candidate_path.resolve() == ignore_resolved:
                return False
            return True

    return False


def generate_collision_fallback_filename(
    sanitized_filename: str,
    timestamp: Optional[datetime] = None
) -> str:
    """Generate a deterministic fallback filename with timestamp suffix upon same-day collision.

    Format: title-stem_YYYY-MM-DD-HHMMSS-xxx.png

    Args:
        sanitized_filename: The sanitized base filename (e.g. 'app-error_2026-08-15.png').
        timestamp: Optional datetime object; defaults to datetime.now().

    Returns:
        str: Timestamped unique fallback filename.
    """
    path_obj = Path(sanitized_filename)
    stem = path_obj.stem
    ext = path_obj.suffix or ".png"

    ts = timestamp or datetime.now()
    time_str = ts.strftime("%H%M%S")
    micro_str = ts.strftime("%f")[:3]

    return f"{stem}-{time_str}-{micro_str}{ext}"


def resolve_unique_filename(
    folder: Path,
    title: str,
    original_path: Path,
    capture_date: Optional[Union[str, datetime, date]] = None,
    max_stem_length: int = 100
) -> str:
    """Resolve a safe, sanitized, and collision-free filename in target folder with date suffix.

    1. Determines capture date from file metadata (or parameter).
    2. Sanitizes title and assembles candidate filename: title_YYYY-MM-DD.ext.
    3. Checks for collisions (case-insensitively against FULL filename).
       - Files with same title on different dates will NOT collide.
    4. If colliding on same day, appends deterministic timestamp suffix.

    Args:
        folder: Destination folder path.
        title: Desired title string.
        original_path: Original screenshot file path.
        capture_date: Optional capture date. If None, read from original_path metadata.
        max_stem_length: Max allowed character length for filename stem.

    Returns:
        str: Final unique filename formatted as title_YYYY-MM-DD.ext.
    """
    ext = original_path.suffix or ".png"
    effective_date = capture_date or get_file_capture_date(original_path)

    candidate = sanitize_title_to_filename(
        title=title,
        capture_date=effective_date,
        original_extension=ext,
        max_stem_length=max_stem_length
    )

    if not is_filename_colliding(folder, candidate, ignore_path=original_path):
        return candidate

    # Collision detected (same day, same title): apply deterministic timestamp fallback
    fallback = generate_collision_fallback_filename(candidate)
    
    # Final safety check in case sub-second collision occurs
    counter = 1
    while is_filename_colliding(folder, fallback, ignore_path=original_path):
        p = Path(fallback)
        fallback = f"{p.stem}-{counter}{p.suffix}"
        counter += 1

    return fallback
