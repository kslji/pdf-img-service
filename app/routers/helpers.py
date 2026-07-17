# app/routers/helpers.py
from fastapi import HTTPException, UploadFile
import re

MAX_IMAGE_SIZE = 15 * 1024 * 1024
MAX_PDF_SIZE = 50 * 1024 * 1024


async def read_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(413, f"File exceeds {max_bytes // 1024 // 1024}MB limit")
    return content


def validate_pdf(file: UploadFile):
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF files are accepted")


def validate_image(file: UploadFile):
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "Only image files are accepted")


def parse_page_ranges(ranges_str: str) -> list[int]:
    pages = set()
    parts = re.split(r"[,\s]+", ranges_str)
    for part in parts:
        if "-" in part:
            a, b = part.split("-")
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return sorted(pages)
