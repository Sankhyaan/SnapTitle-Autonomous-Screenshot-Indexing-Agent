"""Google Gemini Multimodal Vision & LLM Titling Engine for SnapTitle.

Provides ultra-fast, highly accurate screenshot understanding, OCR extraction,
and semantic titling using Google's Gemini multimodal models.
Current model cascade: gemini-3.7-flash -> 3.6 -> 3.5 -> 3.5-lite -> 2.5 -> 1.5
"""

import io
import re
import json
import base64
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from .llm import clean_llm_response, redact_sensitive_info

logger = logging.getLogger("snaptitle.gemini")

GEMINI_API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
LAST_GEMINI_ERROR = ""

DEFAULT_SYSTEM_INSTRUCTION = """You are an expert autonomous screenshot indexing and file naming engine.
Your job is to analyze the provided screenshot image and generate:
1. A concise, descriptive title with spaces between words (3 to 6 words max).
   - Must be specific to what is visible in the screenshot (e.g., "AWS Billing Invoice August", "Kubernetes Pod CrashLoop Exit137", "React UseEffect Memory Leak", "BGP Peers and Peering Overview", "Savannah Wildlife Giraffes Rhino").
   - NEVER use generic placeholders like "screenshot", "image", or "untitled".
   - Do NOT include file extensions (e.g. no .png, .jpg).
   - NEVER include sensitive passwords, secret API keys, or private credit card numbers.
2. A short summary description of the visible text and context for search indexing.

Output MUST be a valid JSON object matching this schema:
{
  "title": "Concise Title With Spaces",
  "content": "Description of text, error codes, and topics visible in the screenshot"
}
"""


def generate_title_and_caption_with_gemini(
    image_path: Optional[Path] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = "gemini-3.6-flash",
    timeout: float = 15.0,
    max_retries: int = 2,
    raw_base64: Optional[str] = None
) -> Optional[Tuple[str, str]]:
    """Analyze screenshot with Google Gemini Vision API and return clean title and caption.

    Supports multiple API keys (comma/semicolon separated in api_key or env vars) with
    automatic failover and rate-limit rotation.
    """
    global LAST_GEMINI_ERROR
    import os

    # Collect all available API keys into a pool
    key_pool = []
    if api_key:
        for k in re.split(r'[,;\s]+', api_key.strip()):
            if k and k not in key_pool:
                key_pool.append(k)

    for env_k in ["GEMINI_API_KEYS", "GEMINI_API_KEY", "SNAPTITLE_GEMINI_API_KEY"]:
        val = os.environ.get(env_k, "")
        if val:
            for k in re.split(r'[,;\s]+', val.strip()):
                if k and k not in key_pool:
                    key_pool.append(k)

    if not key_pool:
        logger.warning("No Gemini API key provided in arguments or environment.")
        return None

    # Detect MIME type and extract base64 data
    mime_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".gif": "image/gif"
    }

    image_b64 = None
    mime_type = "image/png"

    if raw_base64:
        if "," in raw_base64:
            raw_base64 = raw_base64.split(",")[1]
        image_b64 = raw_base64
        mime_type = "image/png"
    elif image_path and image_path.exists():
        ext = image_path.suffix.lower()
        mime_type = mime_type_map.get(ext, "image/png")
        try:
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception as read_err:
            logger.error(f"Failed to read image for Gemini inference: {read_err}")
            return None
    else:
        logger.warning(f"No valid image provided (path={image_path}, has_b64={bool(raw_base64)})")
        return None

    payload: Dict[str, Any] = {
        "contents": [
            {
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": image_b64
                        }
                    },
                    {
                        "text": DEFAULT_SYSTEM_INSTRUCTION
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    payload_bytes = json.dumps(payload).encode("utf-8")

    # Cascading model fallback list: tries fastest/most available models first
    candidate_models = [
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-3.5-flash",
        "gemini-flash-lite-latest",
        "gemini-2.5-flash-lite",
        "gemini-3.7-flash",
        "gemini-2.5-flash",
    ]
    if model and model not in candidate_models:
        candidate_models.insert(0, model)

    for current_key in key_pool:
        key_masked = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 10 else "***"
        image_label = image_path.name if image_path else "base64_frame"
        for current_model in candidate_models:
            url = GEMINI_API_ENDPOINT.format(model=current_model, key=current_key)
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"Querying Gemini Vision ({current_model}) [Key {key_masked}] for '{image_label}'...")
                    req = urllib.request.Request(
                        url,
                        data=payload_bytes,
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": current_key
                        },
                        method="POST"
                    )

                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))

                    candidates = resp_data.get("candidates", [])
                    if not candidates:
                        break

                    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                    if not raw_text:
                        break

                    # Parse JSON output
                    raw_title = ""
                    content_summary = ""
                    try:
                        parsed = json.loads(raw_text)
                        raw_title = parsed.get("title", "")
                        content_summary = parsed.get("content", "")
                    except json.JSONDecodeError:
                        raw_title = raw_text
                        content_summary = raw_text

                    # Clean and enforce title with spaces
                    cleaned = clean_llm_response(raw_title, max_words=6)
                    s1 = re.sub(r'[_]+', ' ', cleaned)
                    s2 = re.sub(r'(.)([A-Z][a-z]+)', r'\1 \2', s1)
                    s3 = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s2)
                    title = re.sub(r'[\s]+', ' ', s3).strip()
                    title = re.sub(r'[^\w\s\-_.]', '', title).strip(' -_.')
                    
LAST_GEMINI_ERROR = ""

                    if title:
                        logger.info(f"Gemini ({current_model}) successfully titled '{image_label}' -> '{title}'")
                        LAST_GEMINI_ERROR = ""
                        return title, content_summary

                except urllib.error.HTTPError as http_err:
                    error_body = ""
                    try:
                        error_body = http_err.read().decode("utf-8")
                    except Exception:
                        pass
                    LAST_GEMINI_ERROR = f"HTTP {http_err.code}: {http_err.reason} - {error_body[:150]}"
                    logger.warning(f"Gemini ({current_model}) [Key {key_masked}] {LAST_GEMINI_ERROR}")
                    if http_err.code == 429 or http_err.code == 404:
                        break
                except Exception as err:
                    LAST_GEMINI_ERROR = f"Error: {err}"
                    logger.warning(f"Gemini ({current_model}) [Key {key_masked}] attempt {attempt} error: {err}")

    return None
