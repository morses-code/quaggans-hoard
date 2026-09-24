#!/usr/bin/env bash
set -euo pipefail

version="${1:-0.0.0}"
arch="$(uname -m)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.][0-9]+)?$ ]] || { echo "Use a numeric version such as 1.0.0" >&2; exit 1; }

python3 -m pip install -r requirements-desktop.txt

iconset="build/QuaggansHoard.iconset"
rm -rf "$iconset" "dist/Quaggan's Hoard.app"
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" public/quaggan-512.png --out "$iconset/icon_${size}x${size}.png" >/dev/null
done
sips -z 32 32 public/quaggan-512.png --out "$iconset/icon_16x16@2x.png" >/dev/null
sips -z 64 64 public/quaggan-512.png --out "$iconset/icon_32x32@2x.png" >/dev/null
sips -z 256 256 public/quaggan-512.png --out "$iconset/icon_128x128@2x.png" >/dev/null
sips -z 512 512 public/quaggan-512.png --out "$iconset/icon_256x256@2x.png" >/dev/null
sips -z 1024 1024 public/quaggan-512.png --out "$iconset/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$iconset" -o public/quaggan.icns

APP_VERSION="$version" python3 -m PyInstaller --noconfirm --clean QuaggansHoard.spec
ditto -c -k --sequesterRsrc --keepParent "dist/Quaggan's Hoard.app" "dist/QuaggansHoard-macOS-${arch}.zip"
rm -f "dist/QuaggansHoard-macOS-${arch}.dmg"
hdiutil create -quiet -volname "Quaggan's Hoard" -srcfolder "dist/Quaggan's Hoard.app" -ov -format UDZO "dist/QuaggansHoard-macOS-${arch}.dmg"
echo "Ready: macOS ${arch} DMG and ZIP"
