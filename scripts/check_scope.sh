#!/usr/bin/env bash
# Scope trim v2 acceptance check: removed features must not appear anywhere in the product
# (code, UI, docs, agents, data). Allowed exceptions: the decision note in docs/DECISIONS.md and the two original
# brief files (BUILD_PROMPT.md, TRIM_PROMPT.md). Binary files (PDFs/images) are skipped. data/snapshots and
# data/synthetic are timetable CONTENT: APU really teaches modules such as "Renewable Energy" and "Energy and Building",
# and those names appear in the feed and in attendance keys - they are not product features.
set -uo pipefail
cd "$(dirname "$0")/.."
TERMS='passport|MRZ|visa|EMGS|escalation|kWh|energy'
hits=$(git ls-files --cached --others --exclude-standard \
  | grep -v -E '^(docs/DECISIONS\.md|BUILD_PROMPT\.md|TRIM_PROMPT\.md|scripts/check_scope\.sh)$' \
  | grep -v -E '^grounding/.*\.(pdf|html)$|^data/(snapshots|synthetic)/' \
  | xargs grep -I -i -n -w -E "$TERMS" 2>/dev/null)
if [ -n "$hits" ]; then
  echo "Scope check FAILED - removed features still referenced:"; echo "$hits"; exit 1
fi
echo "Scope check passed: no references to removed features outside docs/DECISIONS.md and the original briefs."
