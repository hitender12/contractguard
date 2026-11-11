#!/usr/bin/env bash
# PR-summary example: run from the repo root (or from this directory).
# Regenerates examples/pr-summary/pr-summary.md in Markdown format.
# Expected result: file written, exit code 1 (5 BREAKING findings fail CI
# even though the report itself was produced successfully).
set -u
cd "$(dirname "$0")/../.." || exit 1

echo '$ python3 -m contractguard check --base examples/pr-summary/base.yaml --head examples/pr-summary/head.yaml --format markdown --output examples/pr-summary/pr-summary.md'
python3 -m contractguard check --base examples/pr-summary/base.yaml --head examples/pr-summary/head.yaml --format markdown --output examples/pr-summary/pr-summary.md
code=$?
echo
if [ "$code" -ne 1 ]; then
  echo "FAIL: expected exit code 1 (BREAKING), got $code." >&2
  exit 1
fi
if [ ! -s examples/pr-summary/pr-summary.md ]; then
  echo "FAIL: examples/pr-summary/pr-summary.md was not written." >&2
  exit 1
fi
grep -q '| BREAKING | 5 |' examples/pr-summary/pr-summary.md || {
  echo "FAIL: pr-summary.md does not contain the expected 'BREAKING | 5' count." >&2
  exit 1
}
echo "OK: exit code 1 as expected and pr-summary.md written with 5 BREAKING findings."
