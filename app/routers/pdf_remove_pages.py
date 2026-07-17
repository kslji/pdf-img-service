# app/routers/pdf_remove_pages.py
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from app.services.pdf_processor import remove_pages
from app.routers.helpers import parse_page_ranges
import logging

router = APIRouter(prefix="/api/v1/pdf", tags=["PDF Remove Pages"])
logger = logging.getLogger(__name__)


@router.post("/remove-pages")
async def remove_pages_endpoint(
    file: UploadFile = File(...),
    pages_to_remove: str = Form(...),
):
    if not file.filename.lower().endswith(".pdf") and not file.content_type == "application/pdf":
        raise HTTPException(400, "Only PDF files are accepted")
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    try:
        pages = parse_page_ranges(pages_to_remove)  # returns list of ints
    except Exception as e:
        raise HTTPException(400, f"Invalid page specification: {e}")
    
    try:
        result = await asyncio.to_thread(remove_pages, contents, pages)
    except Exception as e:
        logger.error(f"Remove pages failed: {e}")
        raise HTTPException(500, "Failed to remove pages from PDF")
    
    return Response(result, media_type="application/pdf")
