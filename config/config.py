"""SnapTitle Configuration Management.

Provides configuration loading, OS-specific screenshot folder auto-detection,
and environment setup for Tesseract and Ollama.
"""

import os
import sys
import shutil
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, Union, Set
import yaml

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore

logger = logging.getLogger("snaptitle.config")


SUPPORTED_IMAGE_EXTENSIONS: Set[str] = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"
}


def is_supported_image_extension(path_or_ext: Union[str, Path]) -> bool:
    """Check if a path or file extension belongs to a supported screenshot image format.

    Args:
        path_or_ext: Path object or extension string (e.g. '.PNG', '.jpg', Path('shot.webp')).

    Returns:
        bool: True if supported image format, False otherwise.
    """
    if not path_or_ext:
        return False
    if isinstance(path_or_ext, Path):
        ext = path_or_ext.suffix
    else:
        ext = str(path_or_ext)
        if not ext.startswith("."):
            ext = f".{ext}"
    return ext.lower().strip() in SUPPORTED_IMAGE_EXTENSIONS


def get_default_screenshots_dir() -> Path:
    """Auto-detect the default screenshot folder for the current operating system.

    Returns:
        Path: Path to the detected screenshots directory (created if possible).
    """
    home = Path.home()

    if sys.platform.startswith("win"):
        # 1. Query Windows User Shell Folders registry for active Pictures location (handles OneDrive & localized folders)
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                for reg_name in ["My Pictures", "{0DDD015D-B06C-45D5-8C4C-F59713854639}", "{339719B5-8C47-4894-94C2-D8F77ADD44A6}"]:
                    try:
                        val, _ = winreg.QueryValueEx(key, reg_name)
                        if val:
                            expanded = Path(os.path.expandvars(val))
                            if (expanded / "Screenshots").exists():
                                return expanded / "Screenshots"
                            if expanded.exists():
                                return expanded
                    except (FileNotFoundError, OSError):
                        pass
        except Exception:
            pass

        # 2. Check OneDrive subfolders (Pictures, Gambar, Bilder, Images, Fotos, etc.)
        onedrive_roots = [
            home / "OneDrive",
            Path(os.environ["OneDrive"]) if "OneDrive" in os.environ else None,
            Path(os.environ["OneDriveConsumer"]) if "OneDriveConsumer" in os.environ else None,
        ]
        for od in onedrive_roots:
            if od and od.exists():
                for pic_name in ["Pictures", "Gambar", "Bilder", "Images", "Fotos", "Imágenes"]:
                    cand = od / pic_name / "Screenshots"
                    if cand.exists():
                        return cand
                # Direct check for any Screenshots subfolder in OneDrive
                for cand in od.glob("*/Screenshots"):
                    if cand.is_dir():
                        return cand

        # 3. Standard Windows Pictures\Screenshots
        win_screenshots = home / "Pictures" / "Screenshots"
        if win_screenshots.exists():
            return win_screenshots

        # 3. Standard Windows Pictures
        win_pictures = home / "Pictures"
        if win_pictures.exists():
            # If Screenshots subfolder doesn't exist yet, default to creating it or using Pictures
            try:
                win_screenshots.mkdir(parents=True, exist_ok=True)
                return win_screenshots
            except OSError:
                return win_pictures

        # Fallback to Desktop
        return home / "Desktop"

    elif sys.platform == "darwin":  # macOS
        # macOS defaults to saving screenshots on Desktop or configured location
        mac_screenshots = home / "Pictures" / "Screenshots"
        if mac_screenshots.exists():
            return mac_screenshots
        return home / "Desktop"

    else:  # Linux / other Unix
        # Common Linux screenshot destinations
        xdg_pictures = os.environ.get("XDG_PICTURES_DIR")
        if xdg_pictures and Path(xdg_pictures).exists():
            linux_screenshots = Path(xdg_pictures) / "Screenshots"
            if linux_screenshots.exists():
                return linux_screenshots
            return Path(xdg_pictures)

        linux_screenshots = home / "Pictures" / "Screenshots"
        if linux_screenshots.exists():
            return linux_screenshots

        linux_pictures = home / "Pictures"
        if linux_pictures.exists():
            return linux_pictures

        return home / "Desktop"


def find_tesseract_binary(custom_path: Optional[str] = None) -> Optional[str]:
    """Find the Tesseract OCR executable.

    Checks custom_path, system PATH, and well-known installation locations on Windows.

    Returns:
        Optional[str]: Absolute path to tesseract binary, or None if not found.
    """
    if custom_path and os.path.isfile(custom_path):
        return custom_path

    # Check system PATH
    in_path = shutil.which("tesseract")
    if in_path:
        return in_path

    # Check standard Windows paths
    if sys.platform.startswith("win"):
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
            os.path.expandvars(r"%PROGRAMDATA%\chocolatey\bin\tesseract.exe"),
            os.path.expandvars(r"%USERPROFILE%\scoop\shims\tesseract.exe"),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate

    return None


@dataclass
class Config:
    """SnapTitle application configuration settings."""
    screenshots_dir: Path = field(default_factory=get_default_screenshots_dir)
    show_popup: bool = True
    popup_duration_seconds: int = 5
    ai_provider: str = "gemini"  # 'gemini' or 'ollama'
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.6-flash"
    llm_model: str = "llama3.2:3b"
    vlm_model: str = "llava:7b"
    ollama_host: str = "http://127.0.0.1:11434"
    tesseract_cmd: Optional[str] = None
    database_path: Path = field(default_factory=lambda: Path("data/snaptitle.db"))
    llm_timeout: float = 60.0
    vlm_timeout: float = 60.0
    llm_max_retries: int = 1

    def __post_init__(self):
        # Convert path strings to Path objects if necessary
        if isinstance(self.screenshots_dir, str):
            self.screenshots_dir = Path(self.screenshots_dir) if self.screenshots_dir else get_default_screenshots_dir()
        if isinstance(self.database_path, str):
            self.database_path = Path(self.database_path)

        # Resolve Tesseract path
        detected_tesseract = find_tesseract_binary(self.tesseract_cmd)
        if detected_tesseract:
            self.tesseract_cmd = detected_tesseract
            if pytesseract is not None:
                try:
                    pytesseract.pytesseract.tesseract_cmd = detected_tesseract
                except Exception:
                    pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization and debugging.

        Returns:
            Dict[str, Any]: Configuration values as primitive types.
        """
        return {
            "screenshots_dir": str(self.screenshots_dir),
            "show_popup": self.show_popup,
            "popup_duration_seconds": self.popup_duration_seconds,
            "ai_provider": self.ai_provider,
            "gemini_model": self.gemini_model,
            "llm_model": self.llm_model,
            "vlm_model": self.vlm_model,
            "ollama_host": self.ollama_host,
            "tesseract_cmd": self.tesseract_cmd,
            "database_path": str(self.database_path),
            "llm_timeout": self.llm_timeout,
            "vlm_timeout": self.vlm_timeout,
            "llm_max_retries": self.llm_max_retries,
        }


def _parse_bool_env(env_val: Optional[str], default: bool) -> bool:
    """Safely parse boolean environment variable string."""
    if env_val is None:
        return default
    return env_val.strip().lower() in {"1", "true", "yes", "on", "t"}


def load_config(config_path: Optional[Union[str, Path]] = None) -> Config:
    """Load configuration from YAML file and environment variables, falling back to defaults.

    Precedence order:
    1. Environment variables (SNAPTITLE_*)
    2. YAML configuration file
    3. Default values

    Args:
        config_path: Optional path to config YAML file.
                     Defaults to searching `config/default_config.yaml`.

    Returns:
        Config: Populated configuration object.
    """
    # Auto-load .env file if present in project root
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as ef:
                for line in ef:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

    default_file = Path(__file__).parent / "default_config.yaml"
    target_file = Path(config_path) if config_path else default_file

    data: Dict[str, Any] = {}
    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception as e:
            logger.warning(f"Failed to read config file {target_file}: {e}. Using defaults.")

    # Screenshot directory: Env var > YAML > OS Auto-detection
    env_screenshots = os.environ.get("SNAPTITLE_SCREENSHOTS_DIR")
    screenshots_dir_raw = env_screenshots or data.get("screenshots_dir")
    screenshots_dir = Path(screenshots_dir_raw) if screenshots_dir_raw else get_default_screenshots_dir()

    # Database path: Env var > YAML > Default
    env_db = os.environ.get("SNAPTITLE_DATABASE_PATH")
    database_path_raw = env_db or data.get("database_path", "data/snaptitle.db")
    database_path = Path(database_path_raw)

    # Popup settings
    env_popup = os.environ.get("SNAPTITLE_SHOW_POPUP")
    show_popup = _parse_bool_env(env_popup, bool(data.get("show_popup", True)))

    env_popup_dur = os.environ.get("SNAPTITLE_POPUP_DURATION")
    popup_duration = int(env_popup_dur) if env_popup_dur and env_popup_dur.isdigit() else int(data.get("popup_duration_seconds", 5))

    # AI Provider & Models
    ai_provider = os.environ.get("SNAPTITLE_AI_PROVIDER", str(data.get("ai_provider", "gemini")))
    gemini_api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("SNAPTITLE_GEMINI_API_KEY") or data.get("gemini_api_key")
    gemini_model = os.environ.get("SNAPTITLE_GEMINI_MODEL", str(data.get("gemini_model", "gemini-3.6-flash")))

    llm_model = os.environ.get("SNAPTITLE_LLM_MODEL", str(data.get("llm_model", "llama3.2:3b")))
    vlm_model = os.environ.get("SNAPTITLE_VLM_MODEL", str(data.get("vlm_model", "llava:7b")))
    ollama_host = os.environ.get("SNAPTITLE_OLLAMA_HOST", str(data.get("ollama_host", "http://127.0.0.1:11434")))

    # Tesseract
    tesseract_cmd = os.environ.get("SNAPTITLE_TESSERACT_CMD") or data.get("tesseract_cmd") or None

    return Config(
        screenshots_dir=screenshots_dir,
        show_popup=show_popup,
        popup_duration_seconds=popup_duration,
        ai_provider=ai_provider,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        llm_model=llm_model,
        vlm_model=vlm_model,
        ollama_host=ollama_host,
        tesseract_cmd=tesseract_cmd,
        database_path=database_path,
    )

