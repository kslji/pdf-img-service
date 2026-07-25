# app/routers/pdf_converter.py
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response, PlainTextResponse
from app.services.office_converter import (
    pdf_to_text,
    pdf_to_docx,
    pdf_to_csv,
    pdf_to_excel,
    docx_to_pdf,
    txt_to_pdf,
    csv_to_pdf,
)
from app.services.pdf_advanced_processor import (
    convert_pdf_to_images,
    convert_images_to_pdf,
)
from app.routers.helpers import validate_pdf, read_with_limit
from app.utils.credit_meter import check_and_deduct_credits
from fastapi import Request
import fitz  # PyMuPDF
import logging

router = APIRouter(prefix="/api/v1/convert", tags=["Document Converter"])
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 30 * 1024 * 1024


def _count_pdf_pages(contents: bytes) -> int:
    try:
        doc = fitz.open(stream=contents, filetype="pdf")
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 1


@router.post("/pdf-to-txt")
async def pdf_to_txt_endpoint(request: Request, file: UploadFile = File(...)):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)

    page_count = _count_pdf_pages(contents)
    check_and_deduct_credits(request, pages_to_process=page_count)

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


@router.post("/pdf-to-excel")
async def pdf_to_excel_endpoint(file: UploadFile = File(...)):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        excel_bytes = await pdf_to_excel(contents)
    except Exception as e:
        logger.error(f"PDF to Excel error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=converted.xlsx"},
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


@router.post("/pdf-to-images")
async def pdf_to_images_endpoint(
    file: UploadFile = File(...),
    format: str = Form("png"),
    dpi: int = Form(150),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    format = format.lower().strip()
    if format not in ("png", "jpeg", "jpg"):
        raise HTTPException(400, "Supported formats are png, jpeg, or jpg")
    if format == "jpg":
        format = "jpeg"
    try:
        zip_bytes = await asyncio.to_thread(
            convert_pdf_to_images, contents, format, dpi
        )
    except Exception as e:
        logger.error(f"PDF to images error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=pages.zip"},
    )


@router.post("/images-to-pdf")
async def images_to_pdf_endpoint(
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(400, "No image files provided")
    
    images_data = []
    for file in files:
        if not file.content_type.startswith("image/"):
            raise HTTPException(400, f"File {file.filename} is not a valid image")
        contents = await read_with_limit(file, 15 * 1024 * 1024)
        images_data.append(contents)
        
    try:
        pdf_bytes = await asyncio.to_thread(convert_images_to_pdf, images_data)
    except Exception as e:
        logger.error(f"Images to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=images_stitched.pdf"},
    )

