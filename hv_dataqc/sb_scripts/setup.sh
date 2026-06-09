#!/usr/bin/env bash
# Run once per SB session to install uv and project dependencies.
pip install uv
# Derive repo root from this script's location (sb_scripts/ -> hv_dataqc/ -> repo root)
HV="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$HV"
export UV_LINK_MODE=copy
uv sync
git config core.fileMode false  # because SB changes file permissions and then git status says every file has changed