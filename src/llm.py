"""Local LLM title generation using Ollama with strict parsing and privacy guardrails."""

import re
import logging
from typing import Optional
import ollama

logger = logging.getLogger("snaptitle.llm")

# System prompt enforcing strict format, length, safety, and privacy
SYSTEM_PROMPT = """You are a desktop screenshot title generator. Your task is to generate a concise, descriptive title for a screenshot based on its extracted text.

Strict Rules:
1. Output ONLY the title text itself. No explanations, no conversational filler, no quotes, no markdown.
2. The title must be at most 6 words (maximum 6 words).
3. Be specific and descriptive (e.g., "PostgreSQL Connection Error", "Team Release Discussion Chat", "Python 3.13 Release Notes").
4. NEVER include sensitive or private information in the title, such as passwords, API keys, credit card numbers, personal identifiers, phone numbers, or email addresses.
5. Do NOT include special filesystem characters like < > : " / \\ | ? *
"""

# Regex patterns for common conversational prefixes to strip from LLM output
PREFIX_PATTERNS = [
    r"^(here is (a|the) (suggested )?title:?\s*)",
    r"^(title:?\s*)",
    r"^(screenshot title:?\s*)",
    r"^(suggested title:?\s*)",
    r"^(file(name)?:?\s*)",
    r"^(generated title:?\s*)",
    r"^(new title:?\s*)",
    r"^(title idea:?\s*)",
    r"^(?:[\d]+[\.\)]|\*|-|•)\s*",  # List numbering / bullet items e.g. "1. ", "• "
]

# Sensitive data detection regexes (for redacting raw text before sending or validating title)
SENSITIVE_PATTERNS = [
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),  # Credit card numbers
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),  # JWT Tokens
    re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"),  # Base64 tokens / API keys
    re.compile(r"\b(?:password|passwd|secret|api[_-]?key|bearer|auth[_-]?token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9_+.-]+:\/\/[^:\s]+:[^@\s]+@[^\s]+"),  # URLs with basic auth credentials
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),  # Private keys
]


def clean_llm_response(raw_response: str, max_words: int = 6) -> str:
    """Parse, clean, and format raw LLM text into a safe, concise title string.

    Args:
        raw_response: Raw output string from LLM.
        max_words: Maximum word count (default: 6).

    Returns:
        str: Cleaned title string.
    """
    if not raw_response:
        return ""

    # 1. Take the first non-empty line
    lines = [line.strip() for line in raw_response.strip().splitlines() if line.strip()]
    text = lines[0] if lines else ""

    # 2. Strip markdown backticks, asterisks, formatting
    text = re.sub(r"[`*_~]+", "", text)

    # 3. Strip surrounding quotation marks of all styles
    text = text.strip("'\"“”«»` ")

    # 4. Strip conversational prefixes and bullet points iteratively
    for _ in range(3):
        prev_text = text
        for pattern in PREFIX_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
        text = text.strip("'\"“”«»` ")
        if text == prev_text:
            break

    # 5. Remove problematic filesystem characters
    text = re.sub(r'[<>:"/\\|?*]', " ", text)

    # 6. Normalize internal whitespace
    words = text.split()
    if not words:
        return ""

    # 7. Enforce max word limit
    if len(words) > max_words:
        words = words[:max_words]

    cleaned_title = " ".join(words).strip()

    # 8. Strip trailing punctuation marks (e.g. trailing '.', ':', '-', ',')
    cleaned_title = re.sub(r"[\s\.\,\:\;\-\_]+$", "", cleaned_title).strip()

    return cleaned_title


def redact_sensitive_info(text: str) -> str:
    """Redact identifiable sensitive information (passwords, tokens, cards, keys) from text.

    Args:
        text: Raw input text.

    Returns:
        str: Text with sensitive patterns sanitized.
    """
    sanitized = text
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def generate_title_from_text(
    ocr_text: str,
    model: str = "llama3.2:3b",
    host: str = "http://127.0.0.1:11434",
    timeout: float = 60.0,
    max_retries: int = 1
) -> Optional[str]:
    """Send OCR text to local LLM via Ollama and return a clean, concise title.

    Args:
        ocr_text: Extracted OCR text from the screenshot.
        model: Local LLM model identifier (e.g. 'llama3.2:3b').
        host: Ollama API host URL.
        timeout: Request timeout in seconds.
        max_retries: Retry count for transient network failures (default: 1).

    Returns:
        Optional[str]: Generated and cleaned title, or None if inference failed.
    """
    if not ocr_text or not ocr_text.strip():
        return None

    # Pre-redact any obvious sensitive credentials before prompting
    safe_ocr_text = redact_sensitive_info(ocr_text.strip())

    # Limit raw input length sent to LLM to prevent excessive context
    if len(safe_ocr_text) > 1500:
        safe_ocr_text = safe_ocr_text[:1500] + "..."

    prompt = (
        f"Screenshot Text:\n\"\"\"\n{safe_ocr_text}\n\"\"\"\n\n"
        f"Generate a short descriptive title (max 6 words) for this screenshot:"
    )

    for attempt in range(1, max(1, max_retries) + 1):
        try:
            client = ollama.Client(host=host, timeout=timeout)
            response = client.generate(
                model=model,
                system=SYSTEM_PROMPT,
                prompt=prompt,
                options={
                    "temperature": 0.2,  # Low temperature for deterministic, focused titles
                    "top_p": 0.9,
                    "num_predict": 30,    # Cap token generation for speed
                }
            )

            raw_output = response.get("response", "")
            cleaned_title = clean_llm_response(raw_output)
            logger.debug(f"Raw LLM output: '{raw_output}' -> Cleaned: '{cleaned_title}'")
            return cleaned_title if cleaned_title else None

        except Exception as err:
            logger.error(f"Ollama LLM call attempt {attempt}/{max_retries} failed for model '{model}': {err}")

    return None


def generate_disambiguated_title(
    colliding_title: str,
    context_text: str,
    model: str = "llama3.2:3b",
    host: str = "http://127.0.0.1:11434",
    timeout: float = 60.0,
    max_retries: int = 1
) -> Optional[str]:
    """Ask local LLM for a more specific alternative title when a filename collision occurs.

    Args:
        colliding_title: The title that collided with an existing file in the folder.
        context_text: OCR text or VLM image caption from the screenshot.
        model: Local LLM model identifier.
        host: Ollama API host URL.
        timeout: Request timeout in seconds.
        max_retries: Retry count for transient failures.

    Returns:
        Optional[str]: More specific alternative title, or None.
    """
    if not context_text or not context_text.strip():
        return None

    safe_context = redact_sensitive_info(context_text.strip())
    if len(safe_context) > 1500:
        safe_context = safe_context[:1500] + "..."

    prompt = (
        f"Screenshot Content:\n\"\"\"\n{safe_context}\n\"\"\"\n\n"
        f"A screenshot was originally titled: \"{colliding_title}\", but that filename already exists.\n"
        f"Generate a more SPECIFIC, distinct alternative title for this screenshot that is different from \"{colliding_title}\" "
        f"by including specific details (such as error codes, specific section name, person, or unique action).\n"
        f"Generate alternative title (max 6 words):"
    )

    for attempt in range(1, max(1, max_retries) + 1):
        try:
            client = ollama.Client(host=host, timeout=timeout)
            response = client.generate(
                model=model,
                system=SYSTEM_PROMPT,
                prompt=prompt,
                options={
                    "temperature": 0.4,
                    "top_p": 0.9,
                    "num_predict": 30,
                }
            )

            raw_output = response.get("response", "")
            cleaned = clean_llm_response(raw_output)
            if cleaned and cleaned.lower() != colliding_title.lower():
                logger.info(f"Disambiguated title generated: '{colliding_title}' -> '{cleaned}'")
                return cleaned
            return None

        except Exception as err:
            logger.error(f"LLM title disambiguation attempt {attempt}/{max_retries} failed: {err}")

    return None
