#!/usr/bin/env bash
# Jalankan Ketikaketik dari source, di distro mana pun.
# Urutan pencarian interpreter: venv lokal -> python sistem -> python3 di PATH.
set -euo pipefail
SELF="$(readlink -f "${BASH_SOURCE[0]}")"
DIR="$(dirname "$SELF")"

DISTRO=""
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  DISTRO="$(. /etc/os-release && printf '%s' "${ID:-}")"
fi

candidates=(
  "$DIR/.venv-${DISTRO}/bin/python"   # venv khusus distro (dual boot)
  "$DIR/.venv/bin/python"
  "$DIR/venv/bin/python"
  /usr/bin/python3
  python3
)
for py in "${candidates[@]}"; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c "import PySide6" >/dev/null 2>&1; then
    exec "$py" "$DIR/main.py" "$@"
  fi
done

echo "Ketikaketik: PySide6 tidak ditemukan." >&2
echo "Pasang salah satu:" >&2
echo "  Arch     : sudo pacman -S pyside6" >&2
echo "  Fedora   : sudo dnf install python3-pyside6" >&2
echo "  Ubuntu   : sudo apt install python3-pyside6.qtwidgets" >&2
echo "  Semua    : python3 -m venv .venv && .venv/bin/pip install PySide6" >&2
exit 1