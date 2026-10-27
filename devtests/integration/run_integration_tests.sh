#!/usr/bin/env bash
# Runs every integration test project (test_*) in this folder.
# Each project is run from its own folder with config/env.yaml and config/test.yaml.
# Uses the repository's .venv if it exists, otherwise the python3 on PATH.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/../../.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"

RESULT=0
for DIR in "$ROOT"/testset_*/; do
    NAME="$(basename "$DIR")"
    echo
    echo "===== $NAME ====="
    (cd "$DIR" && "$PYTHON" -m fixturerig --config config/env.yaml --config config/test.yaml)
    CODE=$?
    if [ "$CODE" -ne 0 ]; then
        echo "$NAME exited with code $CODE"
        RESULT=1
    fi
done

exit $RESULT
