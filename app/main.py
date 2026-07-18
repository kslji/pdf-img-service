from fastapi import FastAPI
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

app = FastAPI(
    title="File Optimizer & Document Toolkit Microservice",
    version="2.0.0",
    description="High-performance document and image manipulation microservice.",
)

app.add_middleware(GatewayAuthMiddleware)

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
