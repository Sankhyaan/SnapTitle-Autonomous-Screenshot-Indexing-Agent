"""Vision-Language Model (VLM) image captioning fallback using Ollama."""

import logging
from pathlib import Path
from typing import Optional
import ollama

logger = logging.getLogger("snaptitle.vlm")

# Default prompt for the vision model
VLM_PROMPT = "What is shown in this image?"


def generate_caption_from_image(
    image_path: Path,
    model: str = "moondream:latest",
    host: str = "http://127.0.0.1:11434",
    timeout: float = 60.0
) -> Optional[str]:
    """Generate a visual caption describing an image using a local Vision-Language Model (VLM).

    Args:
        image_path: Path to the image file.
        model: VLM model tag in Ollama (e.g. 'moondream:latest', 'moondream', 'llava:7b').
        host: Ollama API host URL.
        timeout: Request timeout in seconds.

    Returns:
        Optional[str]: Generated caption string, or None if inference failed.
    """
    if not image_path.exists():
        logger.warning(f"Image path does not exist for VLM captioning: {image_path}")
        return None

    try:
        client = ollama.Client(host=host, timeout=timeout)
        
        # Verify local models and resolve exact tag (e.g. 'moondream' vs 'moondream:latest' vs 'llava:7b')
        target_model = model
        try:
            available_models = [m.model for m in client.list().models]
            if target_model not in available_models:
                # Find matching prefix or alternative vision model
                matching = [m for m in available_models if model.split(":")[0] in m or "moondream" in m or "llava" in m]
                if matching:
                    target_model = matching[0]
                    logger.debug(f"Resolved VLM model '{model}' to '{target_model}'")
        except Exception:
            pass

        logger.info(f"Sending image '{image_path.name}' to VLM ({target_model})...")
        response = client.generate(
            model=target_model,
            prompt=VLM_PROMPT,
            images=[str(image_path.resolve())],
            options={
                "temperature": 0.2,
                "top_p": 0.9,
                "num_predict": 60,
            }
        )

        caption = response.get("response", "").strip()
        if caption:
            logger.info(f"VLM Caption for '{image_path.name}': {caption}")
            return caption
        else:
            logger.warning(f"VLM returned an empty response for '{image_path.name}'.")
            return None

    except Exception as err:
        logger.warning(f"VLM captioning failed for '{image_path.name}' using model '{model}': {err}")
        return None
