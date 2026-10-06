#!/bin/bash
# Publish the public demo to Hugging Face Spaces (needs: hf auth login).
#   scripts/deploy_hf.sh [user/space]
set -euo pipefail
SPACE=${1:-Muktadii/churnpulse-customer-churn-prediction}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# Only tracked files that the image needs - nothing local or secret.
git -C "$ROOT" archive HEAD pyproject.toml src api streaming models data/processed \
    infra/postgres/init.sql requirements frontend deploy/huggingface | tar -x -C "$STAGE"
cp "$ROOT/deploy/huggingface/Dockerfile" "$STAGE/Dockerfile"
cp "$ROOT/deploy/huggingface/SPACE_README.md" "$STAGE/README.md"

HF=$(command -v hf || echo ~/.local/bin/hf)
"$HF" repos create "$SPACE" --repo-type space --space-sdk docker --public --exist-ok >/dev/null
"$HF" upload "$SPACE" "$STAGE" . --repo-type space --delete "*" --commit-message "Deploy ChurnPulse $(git -C "$ROOT" rev-parse --short HEAD)"
echo "https://huggingface.co/spaces/$SPACE"
