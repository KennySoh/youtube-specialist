#!/usr/bin/env bash
# ./yt <command>      YouTube pipeline, run in Docker (./yt --help lists the commands)
# ./yt setup          build the image (also rebuilt automatically when the code changes)
set -euo pipefail
cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")/.."  # repo root, also via the ./yt symlink
mkdir -p knowledge-library/youtube raw/youtube "$HOME/Downloads"  # else Docker creates them as root
if [[ "${1:-}" == setup ]]; then
    exec docker compose build yt
fi
docker compose --progress quiet build yt
tty=(); [[ -t 0 && -t 1 ]] || tty=(-T)  # no terminal (cron): don't ask Docker for one
exec docker compose --progress quiet run --rm "${tty[@]}" yt "$@"
