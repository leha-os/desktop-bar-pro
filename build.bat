@echo off
setlocal
cd /d "%~dp0"
echo === BUILD LEHA Desktop Bar PRO ===
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua tim thay Python. Can Python 3.10 tro len tren Windows 10/11.
  pause
  exit /b 1
)

echo [1/3] Cai dat thu vien...
python -m pip install --upgrade Pillow pyvda pyinstaller
if errorlevel 1 goto :fail

echo [2/3] Dong goi file .exe (PyInstaller, one-file, khong console)...
python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name "LEHA Desktop Bar PRO" ^
  --version-file version_info.txt ^
  --collect-all pyvda ^
  desktop_bar.py
if errorlevel 1 goto :fail

echo [3/3] Chep config.json mac dinh canh file .exe...
copy /y "config.json" "dist\config.json" >nul

echo.
echo HOAN TAT! File chay nam tai: dist\LEHA Desktop Bar PRO.exe
pause
exit /b 0

:fail
echo.
echo [LOI] Dong goi that bai, xem thong bao loi o tren.
pause
exit /b 1
