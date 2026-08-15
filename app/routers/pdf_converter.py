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
    pdf_to_zip,
    convert_pdf_to_format_via_libreoffice,
    convert_docx_to_format_via_libreoffice,
    convert_office_to_format_via_libreoffice,
    build_pptx_from_docx_text,
    should_skip_translation,
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


async def safe_translate_pdf(pdf_bytes: bytes, target_lang: Optional[str]) -> bytes:
    """Translate a PDF to a target language via DOCX round-trip.
    Skips translation if target_lang is 'none', empty, or matches the detected source language."""
    if not target_lang or target_lang == "none":
        return pdf_bytes
    if should_skip_translation(pdf_bytes, target_lang):
        logger.info(f"safe_translate_pdf: skipping — source language matches target '{target_lang}'")
        return pdf_bytes
    try:
        docx_bytes = await pdf_to_docx(pdf_bytes, target_lang=target_lang)
        return await docx_to_pdf(docx_bytes)
    except Exception as e:
        logger.error(f"safe_translate_pdf failed: {e} — returning original PDF")
        return pdf_bytes


@router.post("/detect-language")
async def detect_language_endpoint(
    file: UploadFile = File(...),
):
    from io import BytesIO
    import pdfplumber
    from docx import Document
    import langdetect
    
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    filename = file.filename.lower()
    ext = "." + filename.split('.')[-1]
    
    text = ""
    try:
        if ext == ".pdf":
            with pdfplumber.open(BytesIO(contents)) as pdf:
                if pdf.pages:
                    text = pdf.pages[0].extract_text() or ""
        elif ext in (".docx", ".doc"):
            doc = Document(BytesIO(contents))
            text = "\n".join(p.text for p in doc.paragraphs[:15])
        elif ext in (".txt", ".csv"):
            text = contents[:3000].decode("utf-8", errors="ignore")
            
        if not text.strip():
            return {"language": "en"}
            
        detected = langdetect.detect(text.strip()[:1000])
        # langdetect returns 'zh-cn' or 'zh-tw' but our frontend SelectItem uses 'zh-CN'
        if detected == "zh-cn":
            detected = "zh-CN"
        return {"language": detected}
    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        return {"language": "en"}


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
        pdf_bytes = await docx_to_pdf(contents, target_lang=target_lang, filename=file.filename)
    except Exception as e:
        logger.error(f"DOCX to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={file.filename.rsplit('.', 1)[0]}.pdf"},
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
    from app.services.office_converter import should_skip_translation
    if should_skip_translation(contents, target_lang):
        logger.info("PDF Translate: target language matches source language. Returning original PDF directly.")
        return Response(
            contents,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={file.filename}"},
        )
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
    target_lang: Optional[str] = Form("none"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        if target_lang and target_lang != "none":
            # Translate DOCX content then build text-slide PPTX (avoids broken LibreOffice DOCX→PPTX)
            docx_bytes = await pdf_to_docx(contents, target_lang=target_lang)
            ppt_bytes = await asyncio.to_thread(build_pptx_from_docx_text, docx_bytes, target_lang)
        else:
            # No translation — render PDF pages as images for a faithful visual representation
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "pptx")
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "xlsx")
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "pages")
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await epub_to_pdf(contents)
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await zip_to_pdf(contents)
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "rtf")
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "odt")
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "odp")
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "ods")
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
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
    target_lang: Optional[str] = Form("none"),
):
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        pdf_bytes = await convert_via_libreoffice(contents, "hwp")
        pdf_bytes = await safe_translate_pdf(pdf_bytes, target_lang)
    except Exception as e:
        logger.error(f"HWP to PDF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=converted_hwp.pdf"},
    )


@router.post("/pdf-to-rtf")
async def pdf_to_rtf_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form("none"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        # RTF is text-based – go through DOCX for best fidelity
        docx_bytes = await pdf_to_docx(contents, target_lang=target_lang if target_lang and target_lang != "none" else None)
        rtf_bytes = await convert_docx_to_format_via_libreoffice(docx_bytes, "rtf")
    except Exception as e:
        logger.error(f"PDF to RTF error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        rtf_bytes,
        media_type="application/rtf",
        headers={"Content-Disposition": "attachment; filename=converted.rtf"},
    )


@router.post("/pdf-to-odt")
async def pdf_to_odt_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form("none"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        # ODT is text-based – always route through DOCX intermediate
        docx_bytes = await pdf_to_docx(contents, target_lang=target_lang if target_lang and target_lang != "none" else None)
        odt_bytes = await convert_docx_to_format_via_libreoffice(docx_bytes, "odt")
    except Exception as e:
        logger.error(f"PDF to ODT error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        odt_bytes,
        media_type="application/vnd.oasis.opendocument.text",
        headers={"Content-Disposition": "attachment; filename=converted.odt"},
    )


@router.post("/pdf-to-odp")
async def pdf_to_odp_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form("none"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        # ODP is presentation-based – route: PDF → PPTX (image slides) → ODP
        # Translation is not feasible on image-based slides; for translated content,
        # we produce a document-style ODP via DOCX → ODT → ODP
        if target_lang and target_lang != "none":
            docx_bytes = await pdf_to_docx(contents, target_lang=target_lang)
            pptx_bytes = await asyncio.to_thread(build_pptx_from_docx_text, docx_bytes, target_lang)
            odp_bytes = await convert_office_to_format_via_libreoffice(pptx_bytes, "pptx", "odp")
        else:
            pptx_bytes = await pdf_to_ppt(contents)
            odp_bytes = await convert_office_to_format_via_libreoffice(pptx_bytes, "pptx", "odp")
    except Exception as e:
        logger.error(f"PDF to ODP error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        odp_bytes,
        media_type="application/vnd.oasis.opendocument.presentation",
        headers={"Content-Disposition": "attachment; filename=converted.odp"},
    )


@router.post("/pdf-to-ods")
async def pdf_to_ods_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form("none"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        # ODS is spreadsheet-based – route: PDF → XLSX (with optional translation) → ODS
        eff_lang = target_lang if target_lang and target_lang != "none" else None
        xlsx_bytes = await pdf_to_excel(contents, target_lang=eff_lang)
        ods_bytes = await convert_office_to_format_via_libreoffice(xlsx_bytes, "xlsx", "ods")
    except Exception as e:
        logger.error(f"PDF to ODS error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        ods_bytes,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": "attachment; filename=converted.ods"},
    )


@router.post("/pdf-to-pages")
async def pdf_to_pages_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form("none"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        # Pages is text-based – always route through DOCX intermediate
        docx_bytes = await pdf_to_docx(contents, target_lang=target_lang if target_lang and target_lang != "none" else None)
        pages_bytes = await convert_docx_to_format_via_libreoffice(docx_bytes, "docx")
    except Exception as e:
        logger.error(f"PDF to Pages error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        pages_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=converted.pages"},
    )


@router.post("/pdf-to-hwp")
async def pdf_to_hwp_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form("none"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        # HWP – always route through DOCX for consistent formatting
        eff_lang = target_lang if target_lang and target_lang != "none" else None
        docx_bytes = await pdf_to_docx(contents, target_lang=eff_lang)
        hwp_bytes = await convert_docx_to_format_via_libreoffice(docx_bytes, "hwp")
    except Exception as e:
        logger.error(f"PDF to HWP error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        hwp_bytes,
        media_type="application/x-hwp",
        headers={"Content-Disposition": "attachment; filename=converted.hwp"},
    )


@router.post("/pdf-to-epub")
async def pdf_to_epub_endpoint(
    file: UploadFile = File(...),
    target_lang: Optional[str] = Form("none"),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        # EPUB – always route through DOCX for consistent formatting
        eff_lang = target_lang if target_lang and target_lang != "none" else None
        docx_bytes = await pdf_to_docx(contents, target_lang=eff_lang)
        epub_bytes = await convert_docx_to_format_via_libreoffice(docx_bytes, "epub")
    except Exception as e:
        logger.error(f"PDF to EPUB error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        epub_bytes,
        media_type="application/epub+zip",
        headers={"Content-Disposition": "attachment; filename=converted.epub"},
    )


@router.post("/pdf-to-zip")
async def pdf_to_zip_endpoint(
    file: UploadFile = File(...),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        zip_bytes = await pdf_to_zip(contents)
    except Exception as e:
        logger.error(f"PDF to ZIP error: {e}")
        raise HTTPException(500, f"Conversion failed: {e}")
    return Response(
        zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=converted.zip"},
    )


@router.post("/pdf-page-to-image")
async def pdf_page_to_image_endpoint(
    file: UploadFile = File(...),
    page: int = Form(1),
    dpi: int = Form(150),
):
    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)
    try:
        doc = fitz.open(stream=contents, filetype="pdf")
        if page < 1 or page > len(doc):
            raise HTTPException(400, f"Page number {page} is out of range")
        
        pdf_page = doc.load_page(page - 1)
        pix = pdf_page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        doc.close()
        return Response(img_bytes, media_type="image/png")
    except Exception as e:
        logger.error(f"Failed to render page {page}: {e}")
        raise HTTPException(500, f"Failed to render page: {e}")



