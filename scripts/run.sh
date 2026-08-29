#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
UV_ROOT="${ROOT_DIR}/.uv"
PY_ROOT="${UV_ROOT}/py"

PY_VERSION_FILE="${ROOT_DIR}/.python-version"
if [[ -f "${PY_VERSION_FILE}" ]]; then
  PY_VERSION="$(head -n 1 "${PY_VERSION_FILE}" | tr -d ' \t\r\n')"
  if [[ -z "${PY_VERSION}" ]]; then
    echo ".python-version is empty: ${PY_VERSION_FILE}" >&2
    exit 1
  fi
else
  echo ".python-version not found: ${PY_VERSION_FILE}" >&2
  exit 1
fi

mkdir -p "${PY_ROOT}"
mkdir -p "${PY_ROOT}/bin"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv command not found in PATH. Install uv and ensure it is available before running this script." >&2
  exit 1
fi
UV_BIN="$(command -v uv)"

UV_GLOBAL_ARGS=(--no-config --managed-python --no-cache)
if [[ ${UV_NATIVE_TLS:-} == "true" ]]; then
  UV_GLOBAL_ARGS+=(--native-tls)
fi

"${UV_BIN}" "${UV_GLOBAL_ARGS[@]}" sync --frozen --no-dev --python "${PY_VERSION}"

VENV_PY="${ROOT_DIR}/.venv/bin/python"
if [[ ! -x "${VENV_PY}" ]]; then
  echo "Python interpreter not found at ${VENV_PY}" >&2
  exit 1
fi

exec "${VENV_PY}" -m chappy "$@"
