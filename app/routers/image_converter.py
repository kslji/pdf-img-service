# app/routers/image_converter.py
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from app.services.image_processor import convert_image
from app.routers.helpers import read_with_limit
import logging

router = APIRouter(prefix="/api/v1/convert", tags=["Image Converter"])
logger = logging.getLogger(__name__)


@router.post("/image")
async def convert_image_endpoint(
    file: UploadFile = File(...),
    format: str = Form(...),
    quality: int = Form(85),
):
    format = format.lower().strip().lstrip(".")
    if format not in ("jpeg", "png", "webp", "gif", "bmp", "tiff"):
        raise HTTPException(400, "Unsupported output format")
    contents = await read_with_limit(file, 15 * 1024 * 1024)
    try:
        # Wrap CPU-bound image conversion in thread pool
        result_bytes, mime = await asyncio.to_thread(convert_image, contents, format, quality)
    except Exception as e:
        logger.error(f"Image conversion failed: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(result_bytes, media_type=mime)
