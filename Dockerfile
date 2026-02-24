FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libpoppler-cpp-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY src/ /app/src/
COPY pyproject.toml /app/

RUN pip install --no-cache-dir --timeout 120 \
    mcp pdfplumber python-docx pytesseract Pillow \
    aiosqlite fastapi "uvicorn[standard]" \
    openpyxl python-pptx beautifulsoup4 pdf2image \
    && pip install --no-cache-dir --no-deps -e .

RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/health', timeout=2).read()"

CMD ["python", "-m", "document_index_mcp", "--http"]
