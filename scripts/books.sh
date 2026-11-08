#!/usr/bin/env bash
# ./scripts/books.sh [slug ...] [--force]   PDFs in knowledge-library/books/books.txt → knowledge-library/books/<slug>/chapters/
# PDFs are read from $BOOKS_DIR (default raw/books), mounted read-only. Code: pipelines/book-pipeline/
set -euo pipefail
cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/.."  # repo root, wherever it's run from
if [[ -f .env ]]; then set -a; source .env; set +a; fi
BOOKS_DIR="$(realpath "${BOOKS_DIR:-raw/books}")"
[[ -d "$BOOKS_DIR" ]] || { echo "No PDF folder at $BOOKS_DIR (set BOOKS_DIR in .env)" >&2; exit 1; }
docker build -q -t book-ingestion pipelines/book-pipeline >/dev/null
exec docker run --rm -t -u "$(id -u):$(id -g)" -v "$PWD:/repo" -v "$BOOKS_DIR:/books:ro" book-ingestion "$@"
