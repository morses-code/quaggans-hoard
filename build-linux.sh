#!/usr/bin/env bash
set -euo pipefail
trap 'echo "::error title=Linux package failure::Command failed at line ${LINENO}: ${BASH_COMMAND}"' ERR

version="${1:-0.0.0}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.][0-9]+)?$ ]] || { echo "Use a numeric version such as 1.0.0" >&2; exit 1; }

python3 -m pip install -r requirements-desktop.txt
APP_VERSION="$version" python3 -m PyInstaller --noconfirm --clean QuaggansHoard.spec

appdir="build/AppDir"
rm -rf "$appdir"
mkdir -p "$appdir/usr/lib" "$appdir/usr/bin" "$appdir/usr/share/applications" "$appdir/usr/share/icons/hicolor/512x512/apps"
cp -a dist/QuaggansHoard "$appdir/usr/lib/quaggans-hoard"
ln -s ../lib/quaggans-hoard/QuaggansHoard "$appdir/usr/bin/quaggans-hoard"
cp public/quaggan-512.png "$appdir/usr/share/icons/hicolor/512x512/apps/quaggans-hoard.png"
cat > "$appdir/quaggans-hoard.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Quaggan's Hoard
Comment=Guild Wars 2 inventory companion
Exec=quaggans-hoard
Icon=quaggans-hoard
Categories=Game;Utility;
Terminal=false
EOF
cp "$appdir/quaggans-hoard.desktop" "$appdir/usr/share/applications/"
cp public/quaggan-512.png "$appdir/quaggans-hoard.png"
cat > "$appdir/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/quaggans-hoard/QuaggansHoard" "$@"
EOF
chmod +x "$appdir/AppRun"

appimagetool="build/appimagetool.AppImage"
if [[ ! -x "$appimagetool" ]]; then
  curl --fail --location --retry 3 -o "$appimagetool" https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$appimagetool"
fi
ARCH=x86_64 "$appimagetool" --appimage-extract-and-run "$appdir" dist/QuaggansHoard-Linux-x86_64.AppImage

debroot="build/deb"
rm -rf "$debroot"
mkdir -p "$debroot/DEBIAN" "$debroot/opt" "$debroot/usr/bin" "$debroot/usr/share/applications" "$debroot/usr/share/icons/hicolor/512x512/apps"
cp -a dist/QuaggansHoard "$debroot/opt/quaggans-hoard"
ln -s /opt/quaggans-hoard/QuaggansHoard "$debroot/usr/bin/quaggans-hoard"
cp "$appdir/quaggans-hoard.desktop" "$debroot/usr/share/applications/"
cp public/quaggan-512.png "$debroot/usr/share/icons/hicolor/512x512/apps/quaggans-hoard.png"
cat > "$debroot/DEBIAN/control" <<EOF
Package: quaggans-hoard
Version: $version
Section: games
Priority: optional
Architecture: amd64
Maintainer: Quaggan's Hoard contributors
Depends: libsecret-1-0
Description: Local Guild Wars 2 inventory companion
EOF
dpkg-deb --build --root-owner-group "$debroot" dist/QuaggansHoard-Linux-amd64.deb
echo "Ready: Linux AppImage and DEB"
