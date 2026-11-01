@echo off
setlocal
chcp 866 >/dev/null
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

"%PY%" -c "import customtkinter, yt_dlp, PIL, PyInstaller" >/dev/null 2>/dev/null && goto :build
echo Ставлю зависимости...
"%PY%" -m pip install -r requirements.txt || (echo Не удалось поставить пакеты. & pause & exit /b 1)

:build
if not exist "assets\icon.ico" "%PY%" assets\make_icon.py >/dev/null 2>/dev/null
echo Собираю единый .exe, не закрывай это окно (1-3 минуты)...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed --name "DownloadBro" --icon "assets\icon.ico" --collect-all customtkinter --collect-data certifi --hidden-import PIL._tkinter_finder main.py
if errorlevel 1 (
    echo.
    echo Сборка не удалась, текст ошибки выше.
    pause
    exit /b 1
)
echo.
echo Готово: %cd%\dist\DownloadBro.exe
start "" explorer "dist"
pause
exit /b 0
