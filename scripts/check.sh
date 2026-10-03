#!/bin/sh
# 커밋 전 빠른 검증. git pre-commit 훅과 Claude Code 훅이 같은 스크립트를 사용한다.
# 사람이 커밋하든, 어떤 에이전트가 커밋하든 같은 기준을 통과해야 한다.
set -e
cd "$(git rev-parse --show-toplevel)"

PY=.venv/bin/python
[ -x "$PY" ] || PY=python3

"$PY" -m ruff check devfolio/ tests/
"$PY" -m ruff format --check devfolio/ tests/
"$PY" -m pytest -x -q --no-cov -p no:cacheprovider
