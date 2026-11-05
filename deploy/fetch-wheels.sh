#!/usr/bin/env bash
# Downloads the Python wheels the image build needs into deploy/wheels/ (on the host),
# so the build itself never talks to PyPI. Exact versions and sha256 hashes are in
# deploy/requirements/*.txt and are checked again inside the build (--require-hashes).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p wheels
for req in requirements/*.txt; do
  # The image runs Python 3.14; all wheels here are pure Python (py3-none-any).
  pip download --quiet --no-deps --only-binary=:all: --python-version 3.14 \
    --require-hashes -r "$req" -d wheels
done
ls -1 wheels
