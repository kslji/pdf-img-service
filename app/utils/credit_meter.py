import os
import logging
from typing import Optional
from fastapi import Request, HTTPException
import pymongo
import redis

logger = logging.getLogger("credit-meter")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://synap:nvoirenveouUBIUFEIW3U324ni%403$@136.119.153.127:27017/?authSource=admin")
REDIS_URL = os.getenv("REDIS_URL", "redis://:DNIOwrewnvierDNEIW@011@34.69.34.122:6379")

FREE_TRIAL_LIMIT = 2

def _get_mongo_col():
    client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    return client["pdf_service_db"]["user_credits"]

def check_and_deduct_credits(request: Request, pages_to_process: int = 1):
    """
    Checks user credit status and trial count.
    - First 2 trials are completely free (0 credit deduction).
    - After 2 free trials, each page requires 1 credit.
    """
    user_id = getattr(request.state, "user_id", None) or request.headers.get("x-user-id")
    if user_id == "anonymous":
        user_id = None
    client_ip = request.client.host if request.client else "anonymous"
    user_key = user_id or f"ip_{client_ip}"

    col = _get_mongo_col()
    record = col.find_one({"user_key": user_key})

    if not record:
        record = {
            "user_key": user_key,
            "trials_used": 0,
            "credits": 0,
        }
        col.insert_one(record)

    trials_used = record.get("trials_used", 0)

    if trials_used < FREE_TRIAL_LIMIT:
        # Increment free trial count
        col.update_one({"user_key": user_key}, {"$inc": {"trials_used": 1}})
        logger.info("Free trial %s/%s used for user %s", trials_used + 1, FREE_TRIAL_LIMIT, user_key)
        return

    # Free trials exhausted -> Calculate credit cost (1 credit per page)
    required_credits = max(1, pages_to_process)
    available_credits = record.get("credits", 0)

    if available_credits < required_credits:
        raise HTTPException(
            status_code=402,
            detail=f"Free trials exhausted ({FREE_TRIAL_LIMIT}/{FREE_TRIAL_LIMIT} used). "
                   f"This operation requires {required_credits} credit(s), but you have {available_credits} credit(s). "
                   f"Please purchase additional credits to continue."
        )

    # Deduct credits
    col.update_one({"user_key": user_key}, {"$inc": {"credits": -required_credits}})
    logger.info("Deducted %s credit(s) for user %s (remaining: %s)", required_credits, user_key, available_credits - required_credits)
