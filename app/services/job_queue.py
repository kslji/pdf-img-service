"""
Job Queue Service - Using Redis for async PDF operations
Handles: PDF signing, cropping, compression
Cost: FREE (uses existing Redis)
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from redis import Redis, ConnectionPool
from pymongo import MongoClient
import logging

logger = logging.getLogger(__name__)

class JobQueue:
    """Async job queue for expensive PDF operations - OPTIMIZED FOR SHARED VMs"""

    def __init__(self, redis_url: str, mongo_url: str):
        # Redis with connection pooling (critical for shared VM)
        pool = ConnectionPool.from_url(
            redis_url,
            max_connections=10,
            socket_keepalive=True,
            decode_responses=True
        )
        self.redis = Redis(connection_pool=pool)

        # MongoDB with connection pooling (critical for shared VM)
        self.mongo = MongoClient(
            mongo_url,
            maxPoolSize=10,
            minPoolSize=2,
            retryWrites=False,
            serverSelectionTimeoutMS=5000
        )
        self.db = self.mongo['pdf_tools']

        # Create indexes (prevents full table scans on shared VM)
        logger.info("Creating database indexes...")
        self._create_indexes()

        # Create TTL index on jobs collection
        self.db.jobs.create_index(
            'expires_at',
            expireAfterSeconds=0
        )

    def _create_indexes(self):
        """Create MongoDB indexes for optimal performance on shared VM"""
        try:
            # User lookup index
            self.db.jobs.create_index([("user_id", 1)])
            # Status query index
            self.db.jobs.create_index([("status", 1)])
            # Timestamp query index
            self.db.jobs.create_index([("created_at", 1)])
            # Combined index for common queries
            self.db.jobs.create_index([("user_id", 1), ("status", 1)])
            logger.info("Indexes created successfully")
        except Exception as e:
            logger.warning(f"Index creation error (may already exist): {e}")

    def submit_job(
        self,
        job_type: str,  # 'sign', 'crop', 'compress'
        user_id: str,
        params: Dict[str, Any],
        file_key: str,  # MinIO file key
        priority: int = 0
    ) -> str:
        """
        Submit a job to the queue
        Returns: job_id
        """
        job_id = str(uuid.uuid4())

        # Store in MongoDB
        job_doc = {
            "_id": job_id,
            "type": job_type,
            "user_id": user_id,
            "status": "queued",
            "priority": priority,
            "file_key": file_key,
            "params": params,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(hours=24),  # Auto-delete after 24h
            "progress": 0,
            "error": None
        }
        self.db.jobs.insert_one(job_doc)

        # Push to Redis queue
        queue_name = f"pdf-queue:{job_type}"
        self.redis.lpush(queue_name, job_id)

        # Track queue length
        self.redis.incr(f"queue_length:{job_type}")

        logger.info(f"Job {job_id} submitted ({job_type})")
        return job_id

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status - checks Redis cache first, then MongoDB"""

        # Check Redis cache (instant)
        cached = self.redis.get(f"job_status:{job_id}")
        if cached:
            return json.loads(cached)

        # Check MongoDB
        job = self.db.jobs.find_one({"_id": job_id})
        if not job:
            return None

        # Convert MongoDB document to JSON-serializable
        status = {
            "job_id": job["_id"],
            "status": job["status"],
            "type": job["type"],
            "progress": job.get("progress", 0),
            "error": job.get("error"),
            "created_at": job["created_at"].isoformat(),
        }

        if job["status"] == "completed":
            status["output_file_key"] = job.get("output_file_key")

        return status

    def update_job_progress(self, job_id: str, progress: int, status: str = None):
        """Update job progress (0-100)"""

        update_data = {"progress": min(100, max(0, progress))}
        if status:
            update_data["status"] = status

        self.db.jobs.update_one(
            {"_id": job_id},
            {"$set": update_data}
        )

    def mark_job_complete(self, job_id: str, output_file_key: str):
        """Mark job as completed"""

        self.db.jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed",
                "output_file_key": output_file_key,
                "completed_at": datetime.utcnow()
            }}
        )

        # Cache result for 24 hours
        status_data = {
            "job_id": job_id,
            "status": "completed",
            "output_file_key": output_file_key
        }
        self.redis.setex(
            f"job_status:{job_id}",
            86400,  # 24 hours
            json.dumps(status_data)
        )

        logger.info(f"Job {job_id} completed")

    def mark_job_failed(self, job_id: str, error: str):
        """Mark job as failed"""

        self.db.jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "failed",
                "error": error,
                "failed_at": datetime.utcnow()
            }}
        )

        logger.error(f"Job {job_id} failed: {error}")

    def get_next_job(self, job_type: str) -> Optional[str]:
        """Get next job from queue (FIFO)"""

        queue_name = f"pdf-queue:{job_type}"
        job_id = self.redis.rpop(queue_name)

        if job_id:
            # Update status
            self.db.jobs.update_one(
                {"_id": job_id},
                {"$set": {"status": "processing"}}
            )
            self.redis.decr(f"queue_length:{job_type}")

        return job_id

    def get_queue_stats(self, job_type: str) -> Dict[str, Any]:
        """Get queue statistics"""

        queue_length = self.redis.get(f"queue_length:{job_type}") or 0
        processing = self.db.jobs.count_documents({
            "type": job_type,
            "status": "processing"
        })
        completed = self.db.jobs.count_documents({
            "type": job_type,
            "status": "completed",
            "created_at": {"$gte": datetime.utcnow() - timedelta(hours=24)}
        })

        return {
            "queued": int(queue_length),
            "processing": processing,
            "completed_today": completed,
            "total_jobs": queue_length + processing + completed
        }

    def clear_old_jobs(self, days: int = 7):
        """Clear jobs older than N days"""

        cutoff = datetime.utcnow() - timedelta(days=days)
        result = self.db.jobs.delete_many({
            "created_at": {"$lt": cutoff}
        })

        logger.info(f"Cleared {result.deleted_count} old jobs")
