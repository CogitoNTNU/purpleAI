#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec uv run streamlit run dashboard.py --server.address 0.0.0.0 "$@"
