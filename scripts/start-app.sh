#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting OpenNovel on http://127.0.0.1:3000"
echo "Frontend and backend are served from the same process."

cd "${ROOT_DIR}"
exec cargo run --manifest-path backend/Cargo.toml -p api
