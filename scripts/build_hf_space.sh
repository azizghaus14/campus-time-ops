#!/usr/bin/env bash
# Stage a Hugging Face Space (Docker SDK) holding the website + backend in one container.
#   bash scripts/build_hf_space.sh            -> build/hf-space/
# Upload with:  .venv/bin/hf upload <user>/campus-time-ops build/hf-space . --repo-type space
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=build/hf-space
rm -rf "$OUT" && mkdir -p "$OUT/data/snapshots" "$OUT/grounding" "$OUT/backend"
cp deploy/hf/Dockerfile deploy/hf/start.sh deploy/hf/README.md "$OUT/"
rsync -a --exclude node_modules --exclude .next --exclude .dockerignore frontend/ "$OUT/frontend/"
rsync -a --exclude __pycache__ backend/app "$OUT/backend/"
cp grounding/campus_ops_policy.md "$OUT/grounding/"
cp data/holidays_2026.json data/shuttle.json data/rooms.json data/group_sizes.json "$OUT/data/"
cp -r data/synthetic "$OUT/data/"
LATEST=$(cat data/snapshots/LATEST)
cp data/snapshots/LATEST data/snapshots/intakes_"$LATEST".json "$OUT/data/snapshots/"
gzip -9 -c data/snapshots/timetable_"$LATEST".json > "$OUT/data/snapshots/timetable_$LATEST.json.gz"  # HF limit: 10 MB per plain file
find "$OUT" -type f -size +9M -print | sed 's/^/WARNING large file: /'
du -sh "$OUT"
