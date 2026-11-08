#!/usr/bin/env bash
# ./scripts/test.sh   both pipelines' tests, in the YouTube image: no network, no real data mounted
set -euo pipefail
cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/.."
docker compose --progress quiet build yt
exec docker run --rm --network none -u "$(id -u):$(id -g)" \
    -e PYTHONDONTWRITEBYTECODE=1 -e YT_LIBRARY=/tmp/library -e YT_RAW=/tmp/raw -e BOOKS_LIBRARY=/tmp/books \
    -v "$PWD/pipelines/video-pipeline/tests:/app/tests:ro" -v "$PWD/pipelines/book-pipeline:/book:ro" \
    --entrypoint sh my-ai-brain-yt -c \
    'python -m pytest -q -p no:cacheprovider tests && cd /book && python -m pytest -q -p no:cacheprovider tests'
