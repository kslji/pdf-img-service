from typing import Optional
from io import BytesIO
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def compress_image(
    contents: bytes,
    quality: int = 80,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    output_format: str = "original",
) -> tuple[bytes, str]:
    image = Image.open(BytesIO(contents))
    original_format = image.format.lower() if image.format else "jpeg"

    # Resize if needed
    if max_width or max_height:
        image.thumbnail((max_width or 9999, max_height or 9999), Image.LANCZOS)

    # Determine output format
    fmt = output_format if output_format != "original" else original_format
    # Pillow expects "JPEG" not "jpeg"
    save_format = "JPEG" if fmt == "jpeg" else fmt.upper()

    # Convert to RGB if saving as JPEG and image has alpha
    if save_format == "JPEG" and image.mode in ("RGBA", "P"):
        image = image.convert("RGB")

    buffer = BytesIO()
    save_kwargs = {"format": save_format}
    if save_format == "JPEG":
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    elif save_format == "PNG":
        save_kwargs["optimize"] = True
    elif save_format == "WEBP":
        save_kwargs["quality"] = quality

    image.save(buffer, **save_kwargs)
    contents_compressed = buffer.getvalue()
    mime = f"image/{fmt}"
    return contents_compressed, mime
