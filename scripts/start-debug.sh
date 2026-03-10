#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting Novel GG in debug mode on http://127.0.0.1:3000"
echo "NOVEL_GG_DEBUG=1"

cd "${ROOT_DIR}"
exec env NOVEL_GG_DEBUG=1 cargo run --manifest-path backend/Cargo.toml -p api
