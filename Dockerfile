FROM python:3.11-slim

# Install system dependencies for Pillow, LibreOffice, pdf2docx
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    libreoffice-core \
    libreoffice-writer \
    libreoffice-impress \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app ./app

EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--backlog", "2048", "--keep-alive", "5"]