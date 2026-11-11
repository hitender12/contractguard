#!/usr/bin/env bash
# Safe-change example: run from the repo root (or from this directory).
# Expected result: 4 SAFE findings, exit code 0 (check passes).
set -eu
cd "$(dirname "$0")/../.." || exit 1

echo '$ python3 -m contractguard check --base examples/safe-change/base.yaml --head examples/safe-change/head.yaml'
python3 -m contractguard check --base examples/safe-change/base.yaml --head examples/safe-change/head.yaml
echo
echo "OK: exit code 0 as expected — 4 SAFE findings, check passes."
