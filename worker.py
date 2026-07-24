"""
PDF Worker - Processes async jobs from queue
Runs continuously on GCP VM
Cost: FREE (runs on same VM as main service)

Usage:
  python worker.py --type sign --workers 2
  python worker.py --type crop --workers 1
"""

import asyncio
import json
import os
import logging
import argparse
import resource
import psutil
from datetime import datetime
from minio import Minio
from dotenv import load_dotenv

from app.services.job_queue import JobQueue
from app.services.pdf_advanced_processor import (
    sign_pdf, crop_pdf_per_page
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFWorker:
    """Worker process for async PDF operations - OPTIMIZED FOR SHARED VMs"""

    def __init__(self, job_type: str):
        self.job_type = job_type
        self.job_queue = JobQueue(
            os.getenv('REDIS_URL'),
            os.getenv('MONGO_URL')
        )
        self.minio = Minio(
            os.getenv('MINIO_ENDPOINT'),
            access_key=os.getenv('MINIO_ACCESS_KEY'),
            secret_key=os.getenv('MINIO_SECRET_KEY'),
            secure=os.getenv('MINIO_USE_SSL', 'false').lower() == 'true'
        )

        # Set memory limit for shared VM (500MB per worker)
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            max_memory = 500 * 1024 * 1024  # 500MB
            resource.setrlimit(resource.RLIMIT_AS, (max_memory, hard))
            logger.info(f"Memory limit set to 500MB")
        except Exception as e:
            logger.warning(f"Could not set memory limit: {e}")

        # Track memory usage
        self.memory_threshold = 400 * 1024 * 1024  # 400MB warning level

    async def process_jobs(self):
        """Continuously process jobs from queue"""

        logger.info(f"Worker started for {self.job_type} jobs")

        while True:
            try:
                # Monitor memory usage (critical for shared VM)
                process = psutil.Process()
                memory_usage = process.memory_info().rss
                memory_percent = process.memory_percent()

                if memory_usage > self.memory_threshold:
                    logger.warning(
                        f"Memory usage high: {memory_usage / 1024 / 1024:.0f}MB "
                        f"({memory_percent:.1f}%), cooldown"
                    )
                    await asyncio.sleep(5)
                    continue

                # Get next job
                job_id = self.job_queue.get_next_job(self.job_type)
                if not job_id:
                    await asyncio.sleep(1)  # Sleep if no jobs
                    continue

                logger.info(f"Processing job {job_id}")

                # Get job details
                job = self.job_queue.db.jobs.find_one({"_id": job_id})
                if not job:
                    logger.error(f"Job {job_id} not found")
                    continue

                # Download PDF from MinIO
                file_key = job['file_key']
                try:
                    response = self.minio.get_object(
                        'pdf-queue',
                        file_key
                    )
                    pdf_bytes = response.read()
                    logger.info(f"Downloaded {len(pdf_bytes)} bytes for {job_id}")
                except Exception as e:
                    logger.error(f"Failed to download file: {e}")
                    self.job_queue.mark_job_failed(job_id, f"Download failed: {e}")
                    continue

                # Process based on job type
                try:
                    if self.job_type == 'sign':
                        output = await self._process_sign_job(job_id, pdf_bytes, job)
                    elif self.job_type == 'crop':
                        output = await self._process_crop_job(job_id, pdf_bytes, job)
                    else:
                        raise ValueError(f"Unknown job type: {self.job_type}")

                    # Upload result to MinIO
                    output_key = f"completed/{self.job_type}/{job_id}.pdf"
                    self.minio.put_object(
                        'pdf-results',
                        output_key,
                        output,
                        length=len(output)
                    )

                    # Mark as completed
                    self.job_queue.mark_job_complete(job_id, output_key)
                    logger.info(f"Job {job_id} completed successfully")

                except Exception as e:
                    logger.error(f"Job {job_id} processing failed: {e}")
                    self.job_queue.mark_job_failed(job_id, str(e))

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(5)

    async def _process_sign_job(self, job_id: str, pdf_bytes: bytes, job: dict) -> bytes:
        """Process PDF signing job"""

        params = job['params']
        self.job_queue.update_job_progress(job_id, 20, "processing")

        # Extract signature image if provided
        sig_image_bytes = None
        if 'signature_image_key' in params:
            try:
                response = self.minio.get_object(
                    'signatures',
                    params['signature_image_key']
                )
                sig_image_bytes = response.read()
            except:
                pass

        # Apply signature
        self.job_queue.update_job_progress(job_id, 50)
        result = sign_pdf(
            pdf_bytes,
            sig_image_bytes,
            params.get('signature_text'),
            params.get('page', 1),
            params.get('x', 15),
            params.get('y', 75),
            params.get('width', 150),
            params.get('height', 50),
            params.get('unit', 'points')
        )

        self.job_queue.update_job_progress(job_id, 90)
        return result

    async def _process_crop_job(self, job_id: str, pdf_bytes: bytes, job: dict) -> bytes:
        """Process PDF cropping job"""

        params = job['params']
        self.job_queue.update_job_progress(job_id, 20)

        # Apply crops
        result = crop_pdf_per_page(pdf_bytes, params['crops'])

        self.job_queue.update_job_progress(job_id, 90)
        return result


async def main():
    parser = argparse.ArgumentParser(description='PDF Worker Process')
    parser.add_argument(
        '--type',
        choices=['sign', 'crop', 'compress'],
        default='sign',
        help='Type of jobs to process'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Number of concurrent workers'
    )

    args = parser.parse_args()

    # Create workers
    workers = [
        PDFWorker(args.type).process_jobs()
        for _ in range(args.workers)
    ]

    logger.info(f"Starting {args.workers} worker(s) for {args.type} jobs")

    # Run all workers concurrently
    await asyncio.gather(*workers)


if __name__ == '__main__':
    asyncio.run(main())
