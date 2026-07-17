from typing import Optional
import io
import zipfile
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from app.services.pdf_processor import split_pdf_to_pages, split_pdf_by_ranges
import logging

router = APIRouter(prefix="/api/v1/split", tags=["PDF Split"])
logger = logging.getLogger(__name__)


def parse_range_string(ranges_str: str) -> list[tuple[int, int]]:
    result = []
    parts = ranges_str.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-")
            result.append((int(start.strip()), int(end.strip())))
        else:
            val = int(part.strip())
            result.append((val, val))
    return result


@router.post("/pdf")
async def split_pdf(
    file: UploadFile = File(...),
    mode: str = Form("pages"),
    ranges: Optional[str] = Form(None),
):
    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    
    try:
        if mode == "pages":
            pages = await asyncio.to_thread(split_pdf_to_pages, contents)
        elif mode == "ranges" and ranges:
            range_tuples = parse_range_string(ranges)
            pages = await asyncio.to_thread(split_pdf_by_ranges, contents, range_tuples)
        else:
            raise HTTPException(400, "Invalid split parameters")
    except Exception as e:
        logger.error(f"PDF split failed: {e}")
        raise HTTPException(500, f"Split failed: {e}")

    # Return ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in pages.items():
            zf.writestr(filename, data)
    return Response(
        zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=split_pdfs.zip"},
    )
