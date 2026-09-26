#!/bin/bash
# Gemini CLI: official npm package
. "$(dirname "$0")/common.sh"
npm_install @google/gemini-cli
gemini --version
desktop_entry gemini-cli "Gemini CLI" gemini utilities-terminal-symbolic true
