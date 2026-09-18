#!/usr/bin/env bash
# 运行全部测试（纯标准库，无需 pytest）
set -e
cd "$(dirname "$0")"
export PYTHONPATH="src:tests"
python3 -m unittest discover -s tests/unit -t tests -p "test_*.py" -v
python3 -m unittest discover -s tests/golden -t tests -p "test_*.py" -v
python3 -m unittest discover -s tests/replay -t tests -p "test_*.py" -v
