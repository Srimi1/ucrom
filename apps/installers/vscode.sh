#!/bin/bash
# Visual Studio Code: newest arm64 .deb from Microsoft's official apt repo,
# SHA-256 verified, unpacked into the user's home (no root, no apt changes).
. "$(dirname "$0")/common.sh"
repo=https://packages.microsoft.com/repos/code
step "reading package index"
entry=$(curl -fsSL "$repo/dists/stable/main/binary-arm64/Packages.gz" | gunzip | python3 -c '
import sys, re
best = None
for block in sys.stdin.read().split("\n\n"):
    f = dict(re.findall(r"^(\S+): (.*)$", block, re.M))
    if f.get("Package") != "code":
        continue
    key = [int(x) for x in re.findall(r"\d+", f["Version"])]
    if best is None or key > best[0]:
        best = (key, f["Filename"], f["SHA256"], f["Version"])
print(best[1], best[2], best[3])')
read -r file sha version <<<"$entry"
step "downloading VS Code $version"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fL --retry 3 -o "$tmp/code.deb" "$repo/$file"
echo "$sha  $tmp/code.deb" | sha256sum -c -
rm -rf "$APPS_DIR/vscode"
dpkg-deb -x "$tmp/code.deb" "$APPS_DIR/vscode"
cat > "$BIN_DIR/code" <<EOT
#!/bin/sh
exec "$APPS_DIR/vscode/usr/share/code/code" --ozone-platform-hint=auto --enable-features=WaylandWindowDecorations "\$@"
EOT
chmod +x "$BIN_DIR/code"
echo "$version" > "$APPS_DIR/vscode/VERSION"
desktop_entry vscode "Visual Studio Code" "$BIN_DIR/code" accessories-text-editor-symbolic false
