#!/usr/bin/env bash
# ./scripts/yt.sh <command>      YouTube pipeline, run in Docker (./scripts/yt.sh --help lists the commands)
# ./scripts/yt.sh setup          build the image (also rebuilt automatically when the code changes)
set -euo pipefail
cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/.."  # repo root, wherever it's run from
mkdir -p knowledge-library/youtube raw/youtube "$HOME/Downloads"  # else Docker creates them as root
if [[ "${1:-}" == setup ]]; then
    exec docker compose build yt
fi
docker compose --progress quiet build yt
tty=(); [[ -t 0 && -t 1 ]] || tty=(-T)  # no terminal (cron): don't ask Docker for one
exec docker compose --progress quiet run --rm "${tty[@]}" yt "$@"
