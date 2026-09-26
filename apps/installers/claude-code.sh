#!/bin/bash
# Claude Code: official npm package (ships a native linux-arm64 build, needs Node 22)
. "$(dirname "$0")/common.sh"
npm_install @anthropic-ai/claude-code
claude --version
desktop_entry claude-code "Claude Code" claude utilities-terminal-symbolic true
