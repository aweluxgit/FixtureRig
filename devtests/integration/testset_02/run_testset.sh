#!/usr/bin/env bash
# Checks the --interactive option. Called by ../run_integration_tests.sh with
# the python interpreter as $1, from this folder.
#
# 1. Without --interactive the exception in test 2 is reported as ERROR, test 3
#    still runs and the program exits with 0.
# 2. With --interactive the exception ends the program: it exits non-zero with
#    an InteractiveProbeError traceback, test 3 never runs, and the dut_shutdown
#    step still runs.

PYTHON="${1:-python3}"
ARGS=(--config config/env.yaml --config config/test.yaml)
FAILED=0

check() {
    # check <description> <command...>
    local what="$1"; shift
    if "$@"; then
        echo "  ok:   $what"
    else
        echo "  FAIL: $what"
        FAILED=1
    fi
}

echo "--- run without --interactive"
OUT="$("$PYTHON" -m fixturerig "${ARGS[@]}" 2>&1)"
CODE=$?
echo "$OUT"
check "exit code is 0" test "$CODE" -eq 0
check "test 3 ran" grep -q "MARKER: test 3 ran" <<<"$OUT"
check "dut_shutdown ran" grep -q "MARKER: dut_shutdown ran" <<<"$OUT"

echo "--- run with --interactive"
OUT="$("$PYTHON" -m fixturerig "${ARGS[@]}" --interactive 2>&1)"
CODE=$?
echo "$OUT"
check "exit code is not 0" test "$CODE" -ne 0
check "traceback ends with InteractiveProbeError" grep -q "^tests.interactive.InteractiveProbeError: raised on purpose" <<<"$OUT"
check "test 1 ran" grep -q "MARKER: test 1 ran" <<<"$OUT"
check "test 3 did not run" bash -c '! grep -q "MARKER: test 3 ran" <<<"$0"' "$OUT"
check "dut_shutdown ran" grep -q "MARKER: dut_shutdown ran" <<<"$OUT"

exit $FAILED
