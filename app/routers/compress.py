# app/routers/compress.py
from typing import Optional
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from app.services.image_compressor import compress_image
import logging

router = APIRouter(prefix="/api/v1/compress", tags=["Compress"])
logger = logging.getLogger(__name__)
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 MB


@router.post("/image")
async def compress_image_endpoint(
    file: UploadFile = File(...),
    quality: int = Form(80),
    max_width: Optional[int] = Form(None),
    max_height: Optional[int] = Form(None),
    format: str = Form("original"),
):
    format = format.lower().strip().lstrip(".")
    if file.content_type not in (
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/tiff",
        "image/bmp",
    ):
        raise HTTPException(400, "Unsupported image format")
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large")
    try:
        compressed, mime = await asyncio.to_thread(
            compress_image, contents, quality, max_width, max_height, format
        )
    except Exception as e:
        logger.error(f"Image compression failed: {e}")
        raise HTTPException(500, "Compression failed")
    return Response(content=compressed, media_type=mime)
