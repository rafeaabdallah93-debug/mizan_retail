#!/usr/bin/env bash
# Downloads the Python wheels the image build needs into deploy/wheels/, so the
# image build itself never talks to PyPI. Exact versions and sha256 hashes are in
# deploy/requirements/*.txt; they are checked here and again inside the build.
#
# pip runs inside a pinned Python 3.14 container (the same Python as the image),
# so the host needs only Docker, not Python or pip. If your network re-signs
# HTTPS with its own certificate authority, point PIP_CERT (or SSL_CERT_FILE) at
# that CA file and it is shared with the container.
# Works with bash 3.2 (macOS) and later.
set -eu
cd "$(dirname "$0")"
DEPLOY="$(pwd)"
PYTHON_IMAGE="${PYTHON_IMAGE:-python:3.14.10-slim@sha256:930e1abba7c4e8f96ed93e8012c35d174d7732752731bbd5e8e757d7ec6f3966}"

mkdir -p wheels
ca_args=()
for v in PIP_CERT SSL_CERT_FILE REQUESTS_CA_BUNDLE; do
  f="${!v:-}"
  if [ -n "$f" ] && [ -f "$f" ]; then
    ca_args=(-v "$f:/etc/mizan-ca.crt:ro" -e PIP_CERT=/etc/mizan-ca.crt)
    break
  fi
done

for req in requirements/*.txt; do
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ${ca_args[@]+"${ca_args[@]}"} \
    -v "$DEPLOY/requirements:/req:ro" -v "$DEPLOY/wheels:/wheels" \
    "$PYTHON_IMAGE" \
    pip download --quiet --no-deps --only-binary=:all: --require-hashes \
      -r "/req/$(basename "$req")" -d /wheels
done
ls -1 wheels
