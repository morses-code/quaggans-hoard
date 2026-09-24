#!/usr/bin/env bash
set -euo pipefail
trap 'echo "::error title=macOS package failure::Command failed at line ${LINENO}: ${BASH_COMMAND}"' ERR

version="${1:-0.0.0}"
arch="$(uname -m)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.][0-9]+)?$ ]] || { echo "Use a numeric version such as 1.0.0" >&2; exit 1; }

python3 -m pip install -r requirements-desktop.txt

rm -rf "dist/Quaggan's Hoard.app"

APP_VERSION="$version" python3 -m PyInstaller --noconfirm --clean QuaggansHoard.spec
ditto -c -k --sequesterRsrc --keepParent "dist/Quaggan's Hoard.app" "dist/QuaggansHoard-macOS-${arch}.zip"
rm -f "dist/QuaggansHoard-macOS-${arch}.dmg"
for attempt in 1 2 3; do
  if hdiutil create -quiet -volname "Quaggan's Hoard" -srcfolder "dist/Quaggan's Hoard.app" -ov -format UDZO "dist/QuaggansHoard-macOS-${arch}.dmg"; then
    break
  fi
  rm -f "dist/QuaggansHoard-macOS-${arch}.dmg"
  if [[ "$attempt" == 3 ]]; then
    echo "Could not create the DMG after ${attempt} attempts." >&2
    exit 1
  fi
  echo "DMG creation attempt ${attempt} failed; retrying..." >&2
  sleep 3
done
echo "Ready: macOS ${arch} DMG and ZIP"
