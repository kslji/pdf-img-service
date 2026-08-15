# app/routers/pdf_edit.py
import asyncio
import hashlib
import json
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from app.routers.helpers import validate_pdf, read_with_limit
from app.services.pdf_advanced_processor import (
    crop_pdf,
    crop_pdf_per_page,
    get_page_image,
    redact_pdf,
    add_page_numbers,
    sign_pdf,
    unlock_pdf,
    watermark_pdf,
    protect_pdf,
    flatten_pdf,
)
from app.utils.cache import get_cached_page_image, cache_page_image

router = APIRouter(prefix="/api/v1/pdf", tags=["PDF Editor"])
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024


@router.post("/crop")
async def crop_pdf_endpoint(
    file: UploadFile = File(...),
    x: float = Form(...),
    y: float = Form(...),
    width: float = Form(...),
    height: float = Form(...),
    unit: str = Form("points"),
    pages: str = Form("all"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    if unit not in ("points", "percentage"):
        raise HTTPException(400, "Unit must be either 'points' or 'percentage'")
    try:
        pdf_bytes = await asyncio.to_thread(
            crop_pdf, contents, x, y, width, height, unit, pages
        )
    except Exception as e:
        logger.error(f"Crop PDF error: {e}")
        raise HTTPException(500, f"Crop failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cropped_{file.filename}"},
    )


@router.post("/redact")
async def redact_pdf_endpoint(
    file: UploadFile = File(...),
    text_to_redact: str = Form(None),
    rects: str = Form(None),
    replacements_json: str = Form(None),
):
    validate_pdf(file)
    if not text_to_redact and not rects:
        raise HTTPException(400, "Either text_to_redact or rects must be provided")
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await asyncio.to_thread(
            redact_pdf, contents, text_to_redact, rects, (0, 0, 0), replacements_json
        )
    except Exception as e:
        logger.error(f"Redact PDF error: {e}")
        raise HTTPException(500, f"Redaction failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=redacted_{file.filename}"},
    )


@router.post("/page-number")
async def page_number_pdf_endpoint(
    file: UploadFile = File(...),
    pattern: str = Form("Page {page} of {total}"),
    position: str = Form("bottom-right"),
    margin: float = Form(36.0),
    font_size: float = Form(10.0),
    font_color: str = Form("000000"),
    start_number: int = Form(1),
    exclude_first_page: bool = Form(False),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    valid_positions = (
        "bottom-right",
        "bottom-center",
        "bottom-left",
        "top-right",
        "top-center",
        "top-left",
    )
    if position not in valid_positions:
        raise HTTPException(400, f"Position must be one of {valid_positions}")
    try:
        pdf_bytes = await asyncio.to_thread(
            add_page_numbers,
            contents,
            pattern,
            position,
            margin,
            font_size,
            font_color,
            start_number,
            exclude_first_page,
        )
    except Exception as e:
        logger.error(f"Add page numbers error: {e}")
        raise HTTPException(500, f"Page numbering failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=numbered_{file.filename}"
        },
    )


@router.post("/sign")
async def sign_pdf_endpoint(
    file: UploadFile = File(...),
    signature_image: UploadFile = File(None),
    signature_text: str = Form(None),
    page: int = Form(1),
    x: float = Form(...),
    y: float = Form(...),
    width: float = Form(150.0),
    height: float = Form(50.0),
    unit: str = Form("points"),
):
    validate_pdf(file)
    if not signature_image and not signature_text:
        raise HTTPException(
            400, "Either signature_image or signature_text must be provided"
        )
    contents = await read_with_limit(file, MAX_FILE_SIZE)

    sig_image_bytes = None
    if signature_image:
        sig_image_bytes = await signature_image.read()

    try:
        pdf_bytes = await asyncio.to_thread(
            sign_pdf,
            contents,
            sig_image_bytes,
            signature_text,
            page,
            x,
            y,
            width,
            height,
            unit,
        )
    except Exception as e:
        logger.error(f"Sign PDF error: {e}")
        raise HTTPException(500, f"Signing failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=signed_{file.filename}"},
    )


@router.post("/unlock")
async def unlock_pdf_endpoint(
    file: UploadFile = File(...),
    password: str = Form(...),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await asyncio.to_thread(unlock_pdf, contents, password)
    except Exception as e:
        logger.error(f"Unlock PDF error: {e}")
        raise HTTPException(500, f"Unlocking failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=unlocked_{file.filename}"},
    )


@router.post("/page-image")
async def get_page_image_endpoint(
    file: UploadFile = File(...),
    page: int = Form(1),
    dpi: int = Form(96),
):
    """Render a single PDF page to PNG for preview/thumbnail use. Cached in-memory."""
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        # Check cache first
        cached = await asyncio.to_thread(get_cached_page_image, contents, page, dpi)
        if cached is not None:
            logger.debug(f"Cache hit for page {page} @ {dpi}dpi")
            return Response(cached, media_type="image/png")

        # Render if not cached
        img_bytes = await asyncio.to_thread(get_page_image, contents, page, dpi)

        # Store in cache
        await asyncio.to_thread(cache_page_image, contents, page, dpi, img_bytes)

    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Page image error: {e}")
        raise HTTPException(500, f"Failed to render page: {e}")
    return Response(
        img_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=3600",
            "ETag": f'"{hashlib.md5(img_bytes).hexdigest()}"'
        }
    )


@router.post("/crop-per-page")
async def crop_pdf_per_page_endpoint(
    file: UploadFile = File(...),
    crops_json: str = Form(...),
):
    """Apply independent crop regions to individual pages.
    
    crops_json: JSON array of objects:
      [{ "page": 1, "x": 10, "y": 10, "width": 80, "height": 80, "unit": "percentage" }]
    Pages not mentioned keep their original dimensions.
    """
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        crops = json.loads(crops_json)
        pdf_bytes = await asyncio.to_thread(crop_pdf_per_page, contents, crops)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid crops_json: {e}")
    except Exception as e:
        logger.error(f"Per-page crop error: {e}")
        raise HTTPException(500, f"Crop failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=cropped_{file.filename}"},
    )


def _analyze_pdf_sync(contents: bytes) -> dict:
    import fitz
    doc = fitz.open(stream=contents, filetype="pdf")
    page_count = len(doc)
    suggested_pages = []
    for idx in range(page_count):
        page = doc.load_page(idx)
        text = page.get_text().lower()
        if "signature" in text or "sign" in text:
            suggested_pages.append(idx + 1)
    return {
        "page_count": page_count,
        "suggested_pages": suggested_pages
    }


@router.post("/analyze")
async def analyze_pdf_endpoint(
    file: UploadFile = File(...),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        return await asyncio.to_thread(_analyze_pdf_sync, contents)
    except Exception as e:
        logger.error(f"Analyze PDF error: {e}")
        raise HTTPException(500, f"Analysis failed: {e}")


@router.post("/watermark")
async def watermark_pdf_endpoint(
    file: UploadFile = File(...),
    text: str = Form(None),
    image: UploadFile = File(None),
    opacity: float = Form(0.5),
    rotation: float = Form(45.0),
    size: float = Form(36.0),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    
    image_bytes = None
    if image:
        image_bytes = await image.read()
        
    try:
        pdf_bytes = await asyncio.to_thread(
            watermark_pdf, contents, text, image_bytes, opacity, rotation, size
        )
    except Exception as e:
        logger.error(f"Watermark PDF error: {e}")
        raise HTTPException(500, f"Watermarking failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=watermarked_{file.filename}"},
    )


@router.post("/protect")
async def protect_pdf_endpoint(
    file: UploadFile = File(...),
    password: str = Form(...),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await asyncio.to_thread(protect_pdf, contents, password)
    except Exception as e:
        logger.error(f"Protect PDF error: {e}")
        raise HTTPException(500, f"Password lock failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=locked_{file.filename}"},
    )


@router.post("/flatten")
async def flatten_pdf_endpoint(
    file: UploadFile = File(...),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await asyncio.to_thread(flatten_pdf, contents)
    except Exception as e:
        logger.error(f"Flatten PDF error: {e}")
        raise HTTPException(500, f"Flattening failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=flattened_{file.filename}"},
    )


@router.post("/edit")
async def edit_pdf_endpoint(
    file: UploadFile = File(...),
    annotations: str = Form(None)
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        import fitz
        doc = fitz.open(stream=contents, filetype="pdf")
        if annotations:
            ann_list = json.loads(annotations)
            for ann in ann_list:
                page_num = ann.get("page", 1) - 1
                if 0 <= page_num < len(doc):
                    page = doc.load_page(page_num)
                    ann_type = ann.get("type")
                    if ann_type == "text":
                        text = ann.get("text", "")
                        x = float(ann.get("x", 50))
                        y = float(ann.get("y", 50))
                        size = float(ann.get("size", 12))
                        color_hex = ann.get("color", "000000").lstrip("#")
                        rgb = tuple(int(color_hex[i:i+2], 16) / 255.0 for i in (0, 2, 4)) if len(color_hex) == 6 else (0,0,0)
                        page.insert_text(fitz.Point(x, y), text, fontsize=size, color=rgb)
                    elif ann_type == "draw":
                        points_list = ann.get("points", [])
                        if len(points_list) > 1:
                            for idx in range(len(points_list) - 1):
                                p1 = fitz.Point(points_list[idx][0], points_list[idx][1])
                                p2 = fitz.Point(points_list[idx+1][0], points_list[idx+1][1])
                                page.draw_line(p1, p2, color=(0,0,0), width=2)
        pdf_bytes = doc.write()
        doc.close()
    except Exception as e:
        logger.error(f"Edit PDF error: {e}")
        raise HTTPException(500, f"Edit failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=edited_{file.filename}"},
    )

