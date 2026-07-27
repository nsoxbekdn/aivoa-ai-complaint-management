#!/usr/bin/env bash
# Pre-submission checks (macOS / Linux).
#
#   bash scripts/preflight.sh
#
# Convenience only — nothing in the project depends on this script.
# It never prints the contents of any .env file.

set -uo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failures=()

step() {
  local name="$1"; shift
  echo
  echo "==> $name"
  if ! "$@"; then
    failures+=("$name")
    echo "    FAILED: $name"
  fi
}

# --- backend ------------------------------------------------------------------
# venv layout differs: bin/ on macOS+Linux, Scripts/ on Windows (Git Bash).
python_bin="$root/backend/.venv/bin/python"
[ -x "$python_bin" ] || python_bin="$root/backend/.venv/Scripts/python.exe"
if [ ! -x "$python_bin" ]; then
  echo "No backend venv under $root/backend/.venv — create it with:"
  echo "  cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

cd "$root/backend"
step "backend tests" "$python_bin" -m pytest -q
step "alembic head" "$python_bin" -m alembic heads

# --- frontend -----------------------------------------------------------------
cd "$root/frontend"
step "frontend lint" npm run lint
step "frontend build" npm run build

# --- tracked-secret scan ------------------------------------------------------
echo
echo "==> secret scan"
cd "$root"
# File names only — values are never printed.
hits="$(grep -rlE 'gsk_[A-Za-z0-9]|sk-[A-Za-z0-9]{10,}|BEGIN (RSA|OPENSSH) PRIVATE KEY' . \
  --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=dist \
  --exclude-dir=__pycache__ --exclude-dir=.pytest_cache --exclude-dir=.git \
  --exclude='.env' 2>/dev/null || true)"

if [ -n "$hits" ]; then
  echo "    Possible secrets in:"
  echo "$hits" | sed 's/^/      /'
  failures+=("secret scan")
else
  echo "    No key-like strings found outside .env."
fi

# --- summary ------------------------------------------------------------------
echo
if [ ${#failures[@]} -eq 0 ]; then
  echo "All preflight checks passed."
  exit 0
fi
printf 'Failed: %s\n' "$(IFS=', '; echo "${failures[*]}")"
exit 1
