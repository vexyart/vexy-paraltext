#!/usr/bin/env bash
# this_file: build.sh
set -euo pipefail
cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec uv build --no-sources --out-dir "${1:-dist}"
