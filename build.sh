#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements.txt
FORCE_ICNS=1 python3 make_icon.py
pyinstaller pdf2epub.spec --clean --noconfirm
echo
echo "====== Done ======"
echo "Output: dist/pdf2epub/"
echo "  - pdf2epub        (CLI)"
echo "  - pdf2epub-gui    (GUI)"
