# app/routers/pdf_converter.py
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response, PlainTextResponse
from app.services.office_converter import (
    pdf_to_text,
    pdf_to_docx,
    pdf_to_csv,
    docx_to_pdf,
    txt_to_pdf,
    csv_to_pdf,
)
from app.routers.helpers import validate_pdf, read_with_limit
import logging

router = APIRouter(prefix="/api/v1/convert", tags=["Document Converter"])
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 30 * 1024 * 1024


@router.post("/pdf-to-txt")
async def pdf_to_txt_endpoint(file: UploadFile = File(...)):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        text = await pdf_to_text(contents)
    except Exception as e:
        logger.error(f"PDF to TXT error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return PlainTextResponse(text, media_type="text/plain")


@router.post("/pdf-to-docx")
async def pdf_to_docx_endpoint(file: UploadFile = File(...)):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        docx_bytes = await pdf_to_docx(contents)
    except Exception as e:
        logger.error(f"PDF to DOCX error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=converted.docx"},
    )


@router.post("/pdf-to-csv")
async def pdf_to_csv_endpoint(file: UploadFile = File(...)):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        csv_bytes = await pdf_to_csv(contents)
    except Exception as e:
        logger.error(f"PDF to CSV error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=converted.csv"},
    )


@router.post("/docx-to-pdf")
async def docx_to_pdf_endpoint(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Only DOCX files are accepted")
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await docx_to_pdf(contents)
    except Exception as e:
        logger.error(f"DOCX to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted.pdf"},
    )


@router.post("/txt-to-pdf")
async def txt_to_pdf_endpoint(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(400, "Only TXT files are accepted")
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await txt_to_pdf(contents)
    except Exception as e:
        logger.error(f"TXT to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted.pdf"},
    )


@router.post("/csv-to-pdf")
async def csv_to_pdf_endpoint(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are accepted")
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await csv_to_pdf(contents)
    except Exception as e:
        logger.error(f"CSV to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted.pdf"},
    )
