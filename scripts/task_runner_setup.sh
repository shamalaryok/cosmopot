#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_INSTALL_TARGET="${PYTHON_INSTALL_TARGET:-.[dev]}"
FRONTEND_DIR="$ROOT_DIR/frontend/spa"

printf 'Repository root: %s\n' "$ROOT_DIR"

cd "$ROOT_DIR"

if ! command -v python >/dev/null 2>&1; then
  echo "Python executable not found in PATH." >&2
  exit 1
fi

echo "::group::Install Python dependencies"
python -m pip install --upgrade pip
pip install -e "$PYTHON_INSTALL_TARGET"
echo "::endgroup::"

if command -v pnpm >/dev/null 2>&1; then
  if [ -d "$FRONTEND_DIR" ]; then
    echo "::group::Install frontend dependencies"
    pushd "$FRONTEND_DIR" >/dev/null
    pnpm install --frozen-lockfile
    popd >/dev/null
    echo "::endgroup::"
  else
    echo "Frontend directory '$FRONTEND_DIR' not found; skipping pnpm install." >&2
  fi
else
  echo "pnpm not found in PATH; skipping frontend dependency installation." >&2
fi
