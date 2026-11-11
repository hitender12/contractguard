#!/usr/bin/env bash
# Breaking-change example: run from the repo root (or from this directory).
# Expected result: 5 BREAKING findings, exit code 1 (BREAKING fails CI).
set -u
cd "$(dirname "$0")/../.." || exit 1

echo '$ python3 -m contractguard check --base examples/breaking-change/base.yaml --head examples/breaking-change/head.yaml'
python3 -m contractguard check --base examples/breaking-change/base.yaml --head examples/breaking-change/head.yaml
code=$?
echo
if [ "$code" -eq 1 ]; then
  echo "OK: exit code 1 as expected — 5 BREAKING findings fail the check."
  exit 0
else
  echo "FAIL: expected exit code 1 (BREAKING), got $code." >&2
  exit 1
fi
