#!/usr/bin/env bash
# this_file: publish.sh
set -euo pipefail
cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec uv run --no-project --script scripts/release.py "$@"
