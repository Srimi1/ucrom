#!/bin/bash
# Run tests while the Halium bridge builder is paused, then resume it.
#
#   sudo tools/dev/run-tests-paused.sh report            full suite + docs/test-report/
#   sudo tools/dev/run-tests-paused.sh tests/test_30_touch_ux.py -k calculator
#
# Why: the emulator runs without KVM. If the arm64 package builds compete
# for the CPU, touch gestures arrive late (libinput logs "event processing
# lagging behind") and Phosh ignores them. The builder script itself is
# paused too, or it keeps starting new build processes.
# pgrep patterns are written as '[b]uild...' so they never match this shell.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p build/logs
pids=$(pgrep -f '[b]uild-bridges.sh|[a]arch64-binfmt')
[ -n "$pids" ] && kill -STOP $pids
if [ "${1:-}" = report ]; then
    python3 -m pytest -v tests --ucrom-report > build/logs/report.log 2>&1; rc=$?
    log=build/logs/report.log
else
    python3 -m pytest -v "$@" > build/logs/tests.log 2>&1; rc=$?
    log=build/logs/tests.log
fi
[ -n "$pids" ] && kill -CONT $pids
grep -E "PASSED|FAILED|SKIPPED|ERROR|passed|failed" "$log" | tail -60
exit $rc
