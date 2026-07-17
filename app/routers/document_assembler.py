# app/routers/document_assembler.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from app.services.document_assembler import assemble_pdf
from app.routers.helpers import read_with_limit
import logging

router = APIRouter(prefix="/api/v1/assemble", tags=["Document Assembler"])
logger = logging.getLogger(__name__)


@router.post("/pdf")
async def assemble_pdf_endpoint(files: list[UploadFile] = File(...)):
    validated = []
    for f in files:
        if len(validated) >= 50:  # limit number of files
            raise HTTPException(400, "Too many files (max 50)")
        content = await read_with_limit(f, 50 * 1024 * 1024)
        validated.append((f.filename, content, f.content_type))
    try:
        result = await assemble_pdf(validated)
    except Exception as e:
        logger.error(f"Assembly failed: {e}")
        raise HTTPException(400, f"Assembly failed: {e}")
    return Response(result, media_type="application/pdf")
