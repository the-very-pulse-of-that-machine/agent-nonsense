#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
if [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python doupi_gui.py
fi
python3 doupi_gui.py
result=$?
if [[ $result -ne 0 ]]; then
    echo '请安装 Python 3.10+，然后在此目录运行：python3 -m pip install ".[gui]"'
    read '?按回车关闭…'
fi
exit $result
