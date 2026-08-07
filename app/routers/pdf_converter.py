# app/routers/pdf_converter.py
import asyncio
from typing import Optional
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
    pdf_to_ppt,
    convert_via_libreoffice,
    epub_to_pdf,
    zip_to_pdf,
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
async def pdf_to_txt_endpoint(
    request: Request,
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form(None)
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)

    page_count = _count_pdf_pages(contents)
    check_and_deduct_credits(request, pages_to_process=page_count)

    try:
        text = await pdf_to_text(contents, target_lang=target_lang)
    except Exception as e:
        logger.error(f"PDF to TXT error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return PlainTextResponse(text, media_type="text/plain")


@router.post("/pdf-to-docx")
async def pdf_to_docx_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form(None)
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        docx_bytes = await pdf_to_docx(contents, target_lang=target_lang)
    except Exception as e:
        logger.error(f"PDF to DOCX error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=converted.docx"},
    )


@router.post("/pdf-to-csv")
async def pdf_to_csv_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form(None)
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        csv_bytes = await pdf_to_csv(contents, target_lang=target_lang)
    except Exception as e:
        logger.error(f"PDF to CSV error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=converted.csv"},
    )


@router.post("/pdf-to-excel")
async def pdf_to_excel_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form(None)
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        excel_bytes = await pdf_to_excel(contents, target_lang=target_lang)
    except Exception as e:
        logger.error(f"PDF to Excel error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=converted.xlsx"},
    )



@router.post("/docx-to-pdf")
async def docx_to_pdf_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form(None)
):
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(400, "Only DOCX files are accepted")
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await docx_to_pdf(contents, target_lang=target_lang)
    except Exception as e:
        logger.error(f"DOCX to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted.pdf"},
    )


@router.post("/txt-to-pdf")
async def txt_to_pdf_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form(None)
):
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(400, "Only TXT files are accepted")
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await txt_to_pdf(contents, target_lang=target_lang)
    except Exception as e:
        logger.error(f"TXT to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted.pdf"},
    )


@router.post("/csv-to-pdf")
async def csv_to_pdf_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form(None)
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are accepted")
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await csv_to_pdf(contents, target_lang=target_lang)
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

    import uuid
    import base64
    import json
    import redis.asyncio as aioredis
    import os

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    r_async = aioredis.from_url(redis_url, decode_responses=True)

    job_id = str(uuid.uuid4())
    file_base64 = base64.b64encode(contents).decode('utf-8')
    payload = {
        "job_id": job_id,
        "file_base64": file_base64,
        "format": format,
        "dpi": dpi
    }

    try:
        await r_async.rpush("pdf_to_images_queue", json.dumps(payload))
        
        pubsub = r_async.pubsub()
        await pubsub.subscribe(f"pdf_to_images_result:{job_id}")

        async def wait_for_msg():
            async for message in pubsub.listen():
                if message["type"] == "message":
                    return json.loads(message["data"])
                    
        result = await asyncio.wait_for(wait_for_msg(), timeout=120.0)
        await r_async.close()

        if result.get("status") == "completed":
            zip_bytes = bytes.fromhex(result["zip_hex"])
            return Response(
                zip_bytes,
                media_type="application/zip",
                headers={"Content-Disposition": "attachment; filename=pages.zip"},
            )
        else:
            raise HTTPException(500, detail=result.get("error", "Failed to convert PDF."))
    except asyncio.TimeoutError:
        await r_async.close()
        raise HTTPException(status_code=504, detail="PDF conversion timed out in queue")
    except Exception as e:
        await r_async.close()
        logger.error(f"PDF to images error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")



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


@router.post("/pdf-translate")
async def pdf_translate_endpoint(
    file: UploadFile = File(...),
    target_lang: str = Form("es"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        docx_bytes = await pdf_to_docx(contents, target_lang=target_lang)
        pdf_bytes = await docx_to_pdf(docx_bytes)
    except Exception as e:
        logger.error(f"PDF Translate error: {e}")
        raise HTTPException(500, f"Translation failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=translated_{file.filename}"},
    )


@router.post("/pdf-to-ppt")
async def pdf_to_ppt_endpoint(
    file: UploadFile = File(...),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        ppt_bytes = await pdf_to_ppt(contents)
    except Exception as e:
        logger.error(f"PDF to PPT error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        ppt_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename={file.filename.replace('.pdf', '.pptx')}"},
    )


@router.post("/ppt-to-pdf")
async def ppt_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "pptx")
    except Exception as e:
        logger.error(f"PPT to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_ppt.pdf"},
    )


@router.post("/excel-to-pdf")
async def excel_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "xlsx")
    except Exception as e:
        logger.error(f"Excel to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_excel.pdf"},
    )


@router.post("/pages-to-pdf")
async def pages_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "pages")
    except Exception as e:
        logger.error(f"Pages to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_pages.pdf"},
    )


@router.post("/epub-to-pdf")
async def epub_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await epub_to_pdf(contents)
    except Exception as e:
        logger.error(f"EPUB to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_epub.pdf"},
    )


@router.post("/zip-to-pdf")
async def zip_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await zip_to_pdf(contents)
    except Exception as e:
        logger.error(f"ZIP to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=compiled_zip.pdf"},
    )


@router.post("/rtf-to-pdf")
async def rtf_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "rtf")
    except Exception as e:
        logger.error(f"RTF to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_rtf.pdf"},
    )


@router.post("/odt-to-pdf")
async def odt_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "odt")
    except Exception as e:
        logger.error(f"ODT to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_odt.pdf"},
    )


@router.post("/odp-to-pdf")
async def odp_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "odp")
    except Exception as e:
        logger.error(f"ODP to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_odp.pdf"},
    )


@router.post("/ods-to-pdf")
async def ods_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "ods")
    except Exception as e:
        logger.error(f"ODS to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_ods.pdf"},
    )


@router.post("/hwp-to-pdf")
async def hwp_to_pdf_endpoint(
    file: UploadFile = File(...),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "hwp")
    except Exception as e:
        logger.error(f"HWP to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_hwp.pdf"},
    )


