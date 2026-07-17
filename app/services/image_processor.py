from io import BytesIO
from PIL import Image

def convert_image(
    contents: bytes, target_format: str, quality: int = 85
) -> tuple[bytes, str]:
    img = Image.open(BytesIO(contents))
    # Convert palette/transparency for JPEG
    if target_format == "jpeg" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    elif target_format == "gif" and img.mode != "P":
        img = img.convert("P", palette=Image.ADAPTIVE)
    buf = BytesIO()
    save_args = {"format": target_format.upper()}
    if target_format in ("jpeg", "webp"):
        save_args["quality"] = quality
        save_args["optimize"] = True
    elif target_format == "png":
        save_args["optimize"] = True
    img.save(buf, **save_args)
    mime = f"image/{target_format}"
    return buf.getvalue(), mime

