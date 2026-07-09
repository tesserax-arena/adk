#!/usr/bin/env bash
# Build and publish tesserax-adk to PyPI.
#
# Usage:
#   UV_PUBLISH_TOKEN=pypi-... ./scripts/publish.sh
#   # or export UV_PUBLISH_TOKEN first
#
# Creates a lean sdist+wheel and uploads with `uv publish`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ -z "${UV_PUBLISH_TOKEN:-}" ]]; then
  echo "Set UV_PUBLISH_TOKEN to a PyPI API token (pypi-...)." >&2
  echo "Create one at https://pypi.org/manage/account/token/" >&2
  exit 1
fi

echo "Building tesserax-adk..."
rm -rf dist
uv build

echo "Contents:"
ls -lh dist

echo "Publishing to PyPI..."
uv publish --token "$UV_PUBLISH_TOKEN"

echo
echo "Published. Install with:"
echo "  uv tool install tesserax-adk --force"
echo "  tesserax --help"
