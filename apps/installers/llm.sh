#!/bin/bash
# LLM (Python): installed in its own venv with pipx
. "$(dirname "$0")/common.sh"
step "installing llm with pipx"
pipx install --force llm
llm --version
desktop_entry llm "LLM" llm utilities-terminal-symbolic true
