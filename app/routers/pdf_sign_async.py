"""
Async PDF Signing API - For 10K+ users
Low latency, queue-based processing
"""

import os
import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from minio import Minio
from app.routers.helpers import validate_pdf, read_with_limit
from app.services.job_queue import JobQueue
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pdf", tags=["PDF Sign (Async)"])

# Initialize services
job_queue = JobQueue(
    os.getenv('REDIS_URL'),
    os.getenv('MONGO_URL')
)

minio = Minio(
    os.getenv('MINIO_ENDPOINT'),
    access_key=os.getenv('MINIO_ACCESS_KEY'),
    secret_key=os.getenv('MINIO_SECRET_KEY'),
    secure=os.getenv('MINIO_USE_SSL', 'false').lower() == 'true'
)

MAX_FILE_SIZE = 50 * 1024 * 1024


@router.post("/sign-async")
async def sign_pdf_async(
    file: UploadFile = File(...),
    signature_image: UploadFile = File(None),
    signature_text: str = Form(None),
    page: int = Form(1),
    x: float = Form(...),
    y: float = Form(...),
    width: float = Form(150.0),
    height: float = Form(50.0),
    unit: str = Form("points"),
    user_id: str = Form(None),  # Can be from auth
):
    """
    Async PDF signing - Returns immediately with job_id
    User polls /sign-async/{job_id}/status to check progress
    Downloads from /sign-async/{job_id}/download when complete

    Response: { "status": "queued", "job_id": "...", "check_url": "..." }
    """

    validate_pdf(file)
    contents = await read_with_limit(file, MAX_FILE_SIZE)

    try:
        # Save PDF to MinIO
        file_key = f"temp/{user_id or 'anon'}/{file.filename}"
        minio.put_object(
            'pdf-queue',
            file_key,
            contents,
            length=len(contents)
        )

        # Save signature image if provided
        sig_image_key = None
        if signature_image:
            sig_bytes = await signature_image.read()
            sig_image_key = f"signatures/{user_id or 'anon'}/{signature_image.filename}"
            minio.put_object(
                'signatures',
                sig_image_key,
                sig_bytes,
                length=len(sig_bytes)
            )

        # Submit job to queue
        params = {
            "signature_text": signature_text,
            "signature_image_key": sig_image_key,
            "page": page,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "unit": unit,
        }

        job_id = job_queue.submit_job(
            job_type='sign',
            user_id=user_id or 'anon',
            params=params,
            file_key=file_key,
            priority=0
        )

        logger.info(f"Sign job {job_id} queued for {file.filename}")

        return JSONResponse({
            "status": "queued",
            "job_id": job_id,
            "message": "Your PDF is queued for signing. Check status below.",
            "check_status_url": f"/api/v1/pdf/sign-async/{job_id}/status",
            "download_url": f"/api/v1/pdf/sign-async/{job_id}/download"
        }, status_code=202)

    except Exception as e:
        logger.error(f"Failed to queue sign job: {e}")
        raise HTTPException(500, f"Failed to queue job: {e}")


@router.get("/sign-async/{job_id}/status")
async def check_sign_status(job_id: str):
    """
    Check job status

    Response:
    - { "status": "queued", "queue_position": 5 }
    - { "status": "processing", "progress": 45 }
    - { "status": "completed", "download_url": "..." }
    - { "status": "failed", "error": "..." }
    """

    status = job_queue.get_job_status(job_id)
    if not status:
        raise HTTPException(404, f"Job {job_id} not found")

    if status["status"] == "queued":
        # Get queue position
        queue_stats = job_queue.get_queue_stats('sign')
        return {
            "status": "queued",
            "job_id": job_id,
            "queue_position": queue_stats['queued'],
            "total_in_queue": queue_stats['queued'] + queue_stats['processing']
        }

    elif status["status"] == "processing":
        return {
            "status": "processing",
            "job_id": job_id,
            "progress": status.get('progress', 0),
            "message": f"Signing your PDF... {status.get('progress', 0)}%"
        }

    elif status["status"] == "completed":
        return {
            "status": "completed",
            "job_id": job_id,
            "download_url": f"/api/v1/pdf/sign-async/{job_id}/download",
            "expires_in_hours": 24,
            "message": "Your PDF is ready to download!"
        }

    elif status["status"] == "failed":
        return {
            "status": "failed",
            "job_id": job_id,
            "error": status.get('error', 'Unknown error'),
            "message": "Failed to sign PDF. Please try again."
        }


@router.get("/sign-async/{job_id}/download")
async def download_signed_pdf(job_id: str):
    """Download completed signed PDF"""

    status = job_queue.get_job_status(job_id)
    if not status:
        raise HTTPException(404, f"Job {job_id} not found")

    if status["status"] != "completed":
        raise HTTPException(
            400,
            f"Job not ready. Status: {status['status']}"
        )

    try:
        output_key = status.get('output_file_key')
        response = minio.get_object('pdf-results', output_key)

        return StreamingResponse(
            response,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=signed_document.pdf"
            }
        )

    except Exception as e:
        logger.error(f"Failed to download job {job_id}: {e}")
        raise HTTPException(500, f"Failed to download file: {e}")


@router.get("/sign-async/stats")
async def queue_stats():
    """Get queue statistics"""

    stats = job_queue.get_queue_stats('sign')
    return {
        "queued": stats['queued'],
        "processing": stats['processing'],
        "completed_today": stats['completed_today'],
        "average_wait_seconds": 2 if stats['queued'] < 10 else 5 + (stats['queued'] * 0.3)
    }
