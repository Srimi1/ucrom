# Node.js 22 (for AI CLI agents like Claude Code and Codex) and user npm prefix
if [ -d /opt/node/bin ]; then
    PATH="/opt/node/bin:$PATH"
fi
if [ -n "$HOME" ]; then
    PATH="$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
    export NPM_CONFIG_PREFIX="$HOME/.npm-global"
fi
export PATH
