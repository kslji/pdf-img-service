import asyncio
import json
import logging
import base64
import os
from redis import Redis

from app.services.pdf_advanced_processor import convert_pdf_to_images

logger = logging.getLogger("pdf_worker")
QUEUE_NAME = "pdf_to_images_queue"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

def run_pdf_worker():
    logger.info("Starting PDF-to-Images background queue worker...")
    r = Redis.from_url(REDIS_URL, decode_responses=True)
    
    # Simple binary-safe connection for pub/sub raw bytes or hex strings
    r_binary = Redis.from_url(REDIS_URL)

    while True:
        try:
            task_data = r.blpop(QUEUE_NAME, timeout=5)
            if not task_data:
                continue

            _, payload_str = task_data
            payload = json.loads(payload_str)
            job_id = payload.get("job_id")
            file_base64 = payload.get("file_base64")
            fmt = payload.get("format", "png")
            dpi = payload.get("dpi", 150)

            logger.info(f"Processing PDF-to-Images job {job_id}")

            data = base64.b64decode(file_base64)
            zip_bytes = convert_pdf_to_images(data, fmt, dpi)

            # Publish result zip bytes as hex string to avoid encoding issues in pubsub
            r.publish(f"pdf_to_images_result:{job_id}", json.dumps({
                "status": "completed",
                "zip_hex": zip_bytes.hex()
            }))
            logger.info(f"PDF-to-Images job {job_id} completed successfully")

        except Exception as e:
            logger.exception("PDF background worker error")
            try:
                if 'job_id' in locals():
                    r.publish(f"pdf_to_images_result:{job_id}", json.dumps({
                        "status": "failed",
                        "error": str(e)
                    }))
            except Exception:
                pass
            import time
            time.sleep(1)
