#!/bin/bash
# Antigravity (Google): installs the official Linux ARM64 build.
#
# Google publishes Antigravity from antigravity.google. ucrom does not
# hard-code a download URL (it changes per release). Instead:
#   1. With UCROM_ANTIGRAVITY_URL set, that official archive/.deb is used.
#   2. Otherwise the newest antigravity*.tar.gz / *.deb in ~/Downloads is used
#      (download it with the browser; the App Hub opens the page for you).
. "$(dirname "$0")/common.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
pkg=""
if [ -n "${UCROM_ANTIGRAVITY_URL:-}" ]; then
    step "downloading $UCROM_ANTIGRAVITY_URL"
    pkg="$tmp/$(basename "${UCROM_ANTIGRAVITY_URL%%\?*}")"
    curl -fL --retry 3 -o "$pkg" "$UCROM_ANTIGRAVITY_URL"
else
    pkg=$(ls -t "$HOME"/Downloads/[Aa]ntigravity*.{tar.gz,deb} 2>/dev/null | head -1 || true)
fi
if [ -z "$pkg" ] || [ ! -f "$pkg" ]; then
    echo "NEEDS_DOWNLOAD https://antigravity.google/download"
    echo "Download the Linux ARM64 build in the browser, then tap Install again."
    exit 3
fi
case "$pkg" in
    *.deb) file "$pkg" >/dev/null; dpkg-deb -f "$pkg" Architecture | grep -qx arm64 ||
               { echo "This package is not an ARM64 build."; exit 4; } ;;
esac
rm -rf "$APPS_DIR/antigravity"; mkdir -p "$APPS_DIR/antigravity"
case "$pkg" in
    *.deb)
        dpkg-deb -x "$pkg" "$tmp/x"
        bin=$(find "$tmp/x" -type f -name antigravity -perm -u+x | head -1)
        cp -a "$(dirname "$bin")"/. "$APPS_DIR/antigravity/" ;;
    *.tar.gz)
        tar -xzf "$pkg" -C "$APPS_DIR/antigravity" --strip-components=1 ;;
esac
[ -x "$APPS_DIR/antigravity/antigravity" ] || { echo "antigravity binary not found in package"; exit 5; }
file -L "$APPS_DIR/antigravity/antigravity" | grep -q aarch64 ||
    { echo "This build is not ARM64; ucrom phones need the ARM64 build."; exit 4; }
cat > "$BIN_DIR/antigravity" <<EOT
#!/bin/sh
exec "$APPS_DIR/antigravity/antigravity" --ozone-platform-hint=auto "\$@"
EOT
chmod +x "$BIN_DIR/antigravity"
desktop_entry antigravity "Antigravity" "$BIN_DIR/antigravity" applications-engineering-symbolic false
