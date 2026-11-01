@echo off
setlocal
chcp 866 >/dev/null
cd /d "%~dp0"

set "PY=pythonw"
set "PIP=python -m pip"
if exist ".venv\Scripts\pythonw.exe" (
    set "PY=.venv\Scripts\pythonw.exe"
    set "PIP=.venv\Scripts\python.exe -m pip"
)

"%PY%" -c "from importlib.metadata import version; exit(0 if int(version('customtkinter').split('.')[0]) >= 6 else 1)" >/dev/null 2>/dev/null
if not errorlevel 1 goto :run

echo Ставлю зависимости нужных версий, подожди пару минут...
%PIP% install -r requirements.txt || goto :fail

:run
if not exist "assets\icon.ico" %PY:.pythonw=.python% assets\make_icon.py >/dev/null 2>/dev/null
del "DownloadBro_ошибка.txt" >/dev/null 2>/dev/null
start "" %PY% main.py
timeout /t 2 /nobreak >/dev/null
if exist "DownloadBro_ошибка.txt" goto :crash
exit /b 0

:crash
echo.
echo Приложение не запустилось. Вот что записано в DownloadBro_ошибка.txt:
echo ----------------------------------------------------------------------
type "DownloadBro_ошибка.txt"
echo ----------------------------------------------------------------------
pause
exit /b 1

:fail
echo Не удалось поставить пакеты. Проверь интернет и запусти этот файл ещё раз.
pause
exit /b 1
