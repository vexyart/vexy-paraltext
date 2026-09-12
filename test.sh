#!/usr/bin/env bash
# this_file: test.sh
set -euo pipefail
cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
    uv sync --no-sources --group test --group lint
fi
uv pip install --python .venv/bin/python --no-deps --reinstall -e .
uv run --no-sync pytest
uv run --no-sync ruff check src tests
uv run --no-sync ty check src
