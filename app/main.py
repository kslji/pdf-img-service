from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.routers import (
    compress,
    pdf_merge,
    pdf_split,
    pdf_optimize,
    pdf_remove_pages,
    pdf_converter,
    document_assembler,
    image_converter,
    image_compressor,
    pdf_edit,
)

from app.middleware.gateway_auth import GatewayAuthMiddleware
from app.utils.log_helper import CentralLoggerMiddleware

import asyncio
from concurrent.futures import ThreadPoolExecutor

app = FastAPI(
    title="File Optimizer & Document Toolkit Microservice",
    version="2.0.0",
    description="High-performance document and image manipulation microservice.",
)

@app.on_event("startup")
async def startup_event():
    # Set default executor to handle high concurrent sync tasks (like PDF processing)
    loop = asyncio.get_event_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=250))

app.add_middleware(GatewayAuthMiddleware)
app.add_middleware(CentralLoggerMiddleware, service_name="pdf-image")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(compress.router)  # /api/v1/compress/image
app.include_router(pdf_merge.router)  # /api/v1/merge/pdfs
app.include_router(pdf_split.router)  # /api/v1/split/pdf
app.include_router(pdf_optimize.router)  # /api/v1/optimize/pdf
app.include_router(pdf_remove_pages.router)  # /api/v1/pdf/remove-pages
app.include_router(pdf_converter.router)  # /api/v1/convert/pdf-to-*, docx-to-pdf, etc.
app.include_router(document_assembler.router)  # /api/v1/assemble/pdf
app.include_router(image_converter.router)  # /api/v1/convert/image
app.include_router(image_compressor.router)  # /api/v1/image/compress (alternative)
app.include_router(pdf_edit.router)  # /api/v1/pdf/*


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/v1/credits")
async def get_user_credits(request: Request):
    from app.utils.credit_meter import _get_mongo_col, FREE_TRIAL_LIMIT
    user_id = getattr(request.state, "user_id", None) or request.headers.get("x-user-id")
    client_ip = request.client.host if request.client else "anonymous"
    user_key = user_id or f"ip_{client_ip}"

    col = _get_mongo_col()
    record = col.find_one({"user_key": user_key}) or {}
    trials_used = record.get("trials_used", 0)

    return {
        "user_key": user_key,
        "free_trials_total": FREE_TRIAL_LIMIT,
        "free_trials_remaining": max(0, FREE_TRIAL_LIMIT - trials_used),
        "credits": record.get("credits", 0),
        "is_trial_active": trials_used < FREE_TRIAL_LIMIT,
    }
