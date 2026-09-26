#!/bin/bash
# Shared helpers for App Hub installers. Runs as the phone user.
set -euo pipefail
export PATH="/opt/node/bin:$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
export NPM_CONFIG_PREFIX="$HOME/.npm-global"
APPS_DIR="$HOME/.local/share/ucrom-apps"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$NPM_CONFIG_PREFIX" "$HOME/Projects"

step() { echo "==> $*"; }

npm_install() {
    step "installing $1 from npm"
    npm install -g --no-fund --no-audit "$1"
}

# desktop_entry <id> <name> <exec> <icon> <terminal:true|false>
desktop_entry() {
    local id=$1 name=$2 exec=$3 icon=$4 term=$5 line
    if [ "$term" = true ]; then
        line="Exec=/usr/lib/ucrom/apps/installers/run-in-terminal.sh $exec"
    else
        line="Exec=$exec"
    fi
    cat > "$DESKTOP_DIR/io.ucrom.app.$id.desktop" <<EOT
[Desktop Entry]
Type=Application
Name=$name
$line
Icon=$icon
Categories=Development;
X-Purism-FormFactor=Workstation;Mobile;
EOT
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    step "launcher added: $name"
}
