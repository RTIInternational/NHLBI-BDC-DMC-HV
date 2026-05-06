#!/usr/bin/env bash
# Unpack a dataqc output tgz (downloaded from SB) into local_output/.
#
# Usage:
#   ./unpack.sh                              # finds most recent ~/Downloads/dataqc_*_output.tgz
#   ./unpack.sh ~/Downloads/dataqc_copdgene_output.tgz
set -euo pipefail
cd "$(dirname "$0")"

TGZ="${1:-$(ls -t ~/Downloads/dataqc_*_output.tgz 2>/dev/null | head -1 || true)}"
if [ -z "$TGZ" ]; then
    echo "ERROR: No tgz file found. Pass a path or download from SB first." >&2
    exit 1
fi

mkdir -p ../local_output
echo "Unpacking: $TGZ"
tar xzf "$TGZ" -C ../local_output/
echo "Unpacked to hv-dataqc/local_output/"
echo
echo "Contents:"
ls ../local_output/latest_source/ ../local_output/latest_harmonized/ 2>/dev/null || true
