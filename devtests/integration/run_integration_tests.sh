#!/usr/bin/env bash
# Runs every integration test project (test_*) in this folder.
# Each project is run from its own folder with config/env.yaml and config/test.yaml,
# unless it has its own run_testset.sh, which is then run from that folder with
# the python interpreter as its argument (e.g. testset_02, which checks --interactive).
# Uses the repository's .venv if it exists, otherwise the python3 on PATH.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/../../.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"

RESULT=0
for DIR in "$ROOT"/testset_*/; do
    NAME="$(basename "$DIR")"
    echo
    echo "===== $NAME ====="
    if [ -f "$DIR/run_testset.sh" ]; then
        (cd "$DIR" && bash ./run_testset.sh "$PYTHON")
    else
        (cd "$DIR" && "$PYTHON" -m fixturerig --config config/env.yaml --config config/test.yaml --config config/test2.yaml)
    fi
    CODE=$?
    if [ "$CODE" -ne 0 ]; then
        echo "$NAME exited with code $CODE"
        RESULT=1
    fi
done

exit $RESULT
