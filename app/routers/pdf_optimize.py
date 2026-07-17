# app/routers/pdf_optimize.py
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from app.services.pdf_processor import compress_pdf
import logging

router = APIRouter(prefix="/api/v1/optimize", tags=["PDF Optimize"])
logger = logging.getLogger(__name__)


@router.post("/pdf")
async def optimize_pdf_endpoint(
    file: UploadFile = File(...),
    level: str = Form("default"),
):
    if not file.filename.lower().endswith(".pdf") and not file.content_type == "application/pdf":
        raise HTTPException(400, "Only PDF files are accepted")
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    try:
        optimized = await asyncio.to_thread(compress_pdf, contents, level)
    except Exception as e:
        logger.error(f"PDF Optimize failed: {e}")
        raise HTTPException(500, "Failed to optimize PDF")
    return Response(
        optimized,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=optimized.pdf"},
    )
