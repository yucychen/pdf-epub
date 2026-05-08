@echo off
setlocal
python -m pip install -r requirements.txt || exit /b 1
python make_icon.py || exit /b 1
pyinstaller pdf2epub.spec --clean --noconfirm || exit /b 1
echo.
echo ====== Done ======
echo Output: dist\pdf2epub\
echo   - pdf2epub.exe       (CLI)
echo   - pdf2epub-gui.exe   (GUI, double-click)
