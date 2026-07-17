# app/routers/pdf_merge.py
import io
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from app.services.pdf_processor import merge_pdfs
import logging

router = APIRouter(prefix="/api/v1/merge", tags=["PDF Merge"])
logger = logging.getLogger(__name__)


@router.post("/pdfs")
async def merge_pdfs_endpoint(files: list[UploadFile] = File(...)):
    streams = []
    for f in files:
        if not f.filename.lower().endswith(".pdf") and not f.content_type == "application/pdf":
            raise HTTPException(400, "All files must be PDFs")
        contents = await f.read()
        if len(contents) > 30 * 1024 * 1024:
            raise HTTPException(413, f"File {f.filename} is too large")
        streams.append(io.BytesIO(contents))
    try:
        merged = await asyncio.to_thread(merge_pdfs, streams)
    except Exception as e:
        logger.error(f"PDF Merge failed: {e}")
        raise HTTPException(500, "Failed to merge PDFs")
    return Response(
        merged,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=merged.pdf"},
    )
