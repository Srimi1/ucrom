#!/bin/bash
# Codex CLI: official npm package (includes the linux-arm64 binary)
. "$(dirname "$0")/common.sh"
npm_install @openai/codex
codex --version
desktop_entry codex "Codex CLI" codex utilities-terminal-symbolic true
