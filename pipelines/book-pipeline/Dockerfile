FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr ghostscript \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "pymupdf4llm==0.3.4" "ocrmypdf>=16,<17"
ENV HOME=/tmp
WORKDIR /repo
ENV PYTHONPATH=/repo/pipelines/book-pipeline
ENTRYPOINT ["python", "-m", "book_ingestion"]
