#!/usr/bin/env bash
# Run once per SB session to install uv and project dependencies.
pip install uv
cd /sbgenomics/workspace/NHLBI-BDC-DMC-HV
uv sync
