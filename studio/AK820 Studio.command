#!/bin/zsh
cd "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
    print 'Önce studio/README.md içindeki Python ortamı kurulumunu tamamlayın.'
    exit 1
fi
exec .venv/bin/python start.py
