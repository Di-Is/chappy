#!/usr/bin/env bash
# Linux: Install desktop entry for chappy
# Run this script once to add chappy to your application menu
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
DESKTOP_DIR="${HOME}/.local/share/applications"
DESKTOP_FILE="${DESKTOP_DIR}/chappy.desktop"

mkdir -p "${DESKTOP_DIR}"

cat > "${DESKTOP_FILE}" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=chappy
Comment=Astronomical spectroscopy analysis application
Exec="${SCRIPT_DIR}/run.sh"
Terminal=true
Categories=Science;Astronomy;
EOF

chmod +x "${DESKTOP_FILE}"

echo "Desktop entry installed: ${DESKTOP_FILE}"
echo "You can now find 'chappy' in your application menu."
