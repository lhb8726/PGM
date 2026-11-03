#!/bin/bash
set -e

trap 'status=$?; echo; echo "PGM 실행에 실패했습니다. 위 오류를 확인해 주세요."; read -r -p "Enter를 누르면 닫습니다. " _pgm_answer; exit "$status"' ERR
cd -- "$(cd -- "$(dirname -- "$0")" && pwd)"

if [ ! -x ".venv/bin/python" ]; then
    pgm_python=""
    for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
            pgm_python="$candidate"
            break
        fi
    done
    if [ -z "$pgm_python" ]; then
        echo "Python 3.10 이상을 설치한 후 다시 실행해 주세요."
        echo "권장 개발 환경: Python 3.12 / https://www.python.org/downloads/"
        false
    fi
    "$pgm_python" -m venv .venv
fi

if ! .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    echo "기존 .venv의 Python이 3.10 미만입니다. 해당 가상환경을 별도로 보관한 뒤 새로 생성해 주세요."
    false
fi

if ! .venv/bin/python -c 'import PySide6' >/dev/null 2>&1; then
    echo "PGM에 필요한 패키지를 설치합니다. 최초 설치에는 인터넷이 필요합니다."
    .venv/bin/python -m pip install -r requirements.txt
fi

.venv/bin/python -m pgm "$@"
