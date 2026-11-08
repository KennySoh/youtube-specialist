#!/usr/bin/env bash
# ./scripts/test.sh   both pipelines' tests, in the YouTube image: no network, no real data mounted
set -euo pipefail
cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/.."
docker compose --progress quiet build yt
exec docker run --rm --network none -u "$(id -u):$(id -g)" \
    -e PYTHONDONTWRITEBYTECODE=1 -e YT_LIBRARY=/tmp/library -e YT_RAW=/tmp/raw -e YT_STATE=/tmp/state \
    -e BOOKS_LIBRARY=/tmp/books -e BOOKS_STATE=/tmp/books-state \
    -v "$PWD/knowledge-acquisition/pipelines/video-pipeline/tests:/app/tests:ro" -v "$PWD/knowledge-acquisition/pipelines/book-pipeline:/book:ro" \
    --entrypoint sh myaimentors-yt -c \
    'python -m pytest -q -p no:cacheprovider tests && cd /book && python -m pytest -q -p no:cacheprovider tests'
