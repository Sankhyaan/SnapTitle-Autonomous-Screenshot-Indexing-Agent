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
    image_path: Path,
    api_key: str,
    model: str = "gemini-3.7-flash",
    timeout: float = 20.0,
    max_retries: int = 2
) -> Optional[Tuple[str, str]]:
    """Analyze screenshot using Gemini Multimodal Vision and return (title, extracted_content).

    Args:
        image_path: Path to screenshot image.
        api_key: Google Gemini API key.
        model: Gemini model identifier (e.g. 'gemini-2.5-flash', 'gemini-flash-lite-latest').
        timeout: Network timeout in seconds.
        max_retries: Maximum retry attempts on transient network errors.

    Returns:
        Optional[Tuple[str, str]]: (Cleaned title, Searchable content summary) or None on error.
    """
    if not image_path.exists():
        logger.warning(f"Image path does not exist: {image_path}")
        return None

    if not api_key:
        logger.warning("No Gemini API key provided.")
        return None

    # Detect MIME type
    ext = image_path.suffix.lower()
    mime_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".gif": "image/gif"
    }
    mime_type = mime_type_map.get(ext, "image/png")

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    except Exception as read_err:
        logger.error(f"Failed to read image for Gemini inference: {read_err}")
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

    # Cascading model fallback list: tries fastest/most responsive first, falls back on 429/404/timeout.
    candidate_models = [model]
    for m in [
        "gemini-3.6-flash",       # ultra fast sub-2s multimodal response
        "gemini-3.5-flash-lite",  # lightest 3.x model
        "gemini-3.5-flash",       # May 2026 flagship
        "gemini-3.7-flash",       # 3.7 flash
        "gemini-1.5-flash",       # 15 RPM stable fallback
        "gemini-1.5-flash-8b",    # 15 RPM lightweight fallback
        "gemini-flash-lite-latest",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]:
        if m not in candidate_models:
            candidate_models.append(m)

    for current_model in candidate_models:
        url = GEMINI_API_ENDPOINT.format(model=current_model, key=api_key)
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Querying Gemini Multimodal Vision ({current_model}) for '{image_path.name}' [attempt {attempt}/{max_retries}]...")
                req = urllib.request.Request(
                    url,
                    data=payload_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )

                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))

                candidates = resp_data.get("candidates", [])
                if not candidates:
                    logger.warning(f"Gemini ({current_model}) returned no candidates.")
                    break

                raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                if not raw_text:
                    logger.warning(f"Gemini ({current_model}) candidate text was empty.")
                    break

                # Parse JSON output
                raw_title = ""
                content_summary = ""
                try:
                    parsed = json.loads(raw_text)
                    raw_title = parsed.get("title", "")
                    content_summary = parsed.get("content", "")
                except json.JSONDecodeError:
                    # Fallback if raw text returned instead of JSON
                    raw_title = raw_text
                    content_summary = raw_text

                # Clean and enforce title with spaces
                cleaned = clean_llm_response(raw_title, max_words=6)
                s1 = re.sub(r'[_]+', ' ', cleaned)
                s2 = re.sub(r'(.)([A-Z][a-z]+)', r'\1 \2', s1)
                s3 = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s2)
                title = re.sub(r'[\s]+', ' ', s3).strip()
                title = re.sub(r'[^\w\s\-_.]', '', title).strip(' -_.')
                
                if title:
                    logger.info(f"Gemini ({current_model}) successfully titled '{image_path.name}' -> '{title}'")
                    return title, content_summary

            except urllib.error.HTTPError as http_err:
                error_body = ""
                try:
                    error_body = http_err.read().decode("utf-8")
                except Exception:
                    pass
                logger.warning(f"Gemini ({current_model}) HTTP {http_err.code}: {http_err.reason} - {error_body[:200]}")
                # If rate limited (429) or model not found (404), break and try next fallback model
                if http_err.code in (429, 404):
                    break
            except Exception as err:
                logger.warning(f"Gemini ({current_model}) failed on attempt {attempt}: {err}")

    return None
