# app/routers/pdf_edit.py
import asyncio
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from app.routers.helpers import validate_pdf, read_with_limit
from app.services.pdf_advanced_processor import (
    crop_pdf,
    redact_pdf,
    add_page_numbers,
    sign_pdf,
    unlock_pdf,
)

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
):
    validate_pdf(file)
    if not text_to_redact and not rects:
        raise HTTPException(400, "Either text_to_redact or rects must be provided")
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await asyncio.to_thread(
            redact_pdf, contents, text_to_redact, rects
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


@router.post("/analyze")
async def analyze_pdf_endpoint(
    file: UploadFile = File(...),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
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
    except Exception as e:
        logger.error(f"Analyze PDF error: {e}")
        raise HTTPException(500, f"Analysis failed: {e}")
