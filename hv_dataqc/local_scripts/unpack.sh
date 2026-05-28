#!/usr/bin/env bash
# Unpack one or more dataqc output tgz files (downloaded from SB) into local_output/.
#
# Usage:
#   ./unpack.sh                              # unpacks ALL ~/Downloads/dataqc_*_output.tgz
#   ./unpack.sh ~/Downloads/dataqc_chs_output.tgz ~/Downloads/dataqc_copdgene_output.tgz
set -euo pipefail
cd "$(dirname "$0")"

if [ "$#" -gt 0 ]; then
    FILES=("$@")
else
    mapfile -t FILES < <(ls -t ~/Downloads/dataqc_*_output.tgz 2>/dev/null || true)
fi

if [ "${#FILES[@]}" -eq 0 ]; then
    echo "ERROR: No tgz files found. Pass paths or download from SB first." >&2
    exit 1
fi

mkdir -p ../local_output

for TGZ in "${FILES[@]}"; do
    echo "Unpacking: $TGZ"
    tar xzf "$TGZ" -C ../local_output/
    echo "  -> done"
done

echo
echo "Unpacked ${#FILES[@]} file(s) to hv_dataqc/local_output/"
echo
echo "Contents:"
ls ../local_output/latest_source/ ../local_output/latest_harmonized/ 2>/dev/null || true
