#!/bin/bash
# Open ucrom's touch terminal in ~/Projects running a CLI agent. When the
# agent exits the shell stays open, so nothing ever needs a hardware keyboard
# to recover.
cmd="$*"
exec kgx --working-directory="$HOME/Projects" -- bash -lc "$cmd; exec bash -l"
