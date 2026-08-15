"""SnapTitle: Automatic desktop screenshot organizer and AI-powered namer."""

from .naming import (
    sanitize_title_to_filename,
    is_filename_colliding,
    generate_collision_fallback_filename,
    resolve_unique_filename,
    get_file_capture_date,
)
from .renamer import (
    safe_rename,
    rename_with_title,
    wait_for_file_settled,
)
from .watcher import (
    ScreenshotWatcher,
    ScreenshotEventHandler,
)
from .ocr import (
    extract_text_from_image,
    has_meaningful_text,
)
from .llm import (
    generate_title_from_text,
    generate_disambiguated_title,
    clean_llm_response,
    redact_sensitive_info,
)
from .vlm import (
    generate_caption_from_image,
)
from .popup import (
    ScreenshotPopup,
    PopupManager,
)
from .database import (
    DatabaseManager,
)
from .core import (
    SnapTitleService,
)

__version__ = "0.4.0"
__all__ = [
    "sanitize_title_to_filename",
    "is_filename_colliding",
    "generate_collision_fallback_filename",
    "resolve_unique_filename",
    "get_file_capture_date",
    "safe_rename",
    "rename_with_title",
    "wait_for_file_settled",
    "ScreenshotWatcher",
    "ScreenshotEventHandler",
    "extract_text_from_image",
    "has_meaningful_text",
    "generate_title_from_text",
    "generate_disambiguated_title",
    "clean_llm_response",
    "redact_sensitive_info",
    "generate_caption_from_image",
    "ScreenshotPopup",
    "PopupManager",
    "DatabaseManager",
    "SnapTitleService",
]
