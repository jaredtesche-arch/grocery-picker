@echo off
cd /d "%~dp0"
echo Grocery Picker setup
echo.
where py >nul 2>nul
if errorlevel 1 (
  echo Python isn't installed. Installing it now. Say Yes if Windows asks.
  winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python is installed. Close this window and double-click Setup again.
  pause
  exit /b
)
if not exist .venv (
  echo Making a private Python folder for the picker...
  py -3 -m venv .venv || goto fail
)
echo Installing what the picker needs. This takes a minute...
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto fail
.venv\Scripts\python.exe first_time_setup.py || goto fail
echo.
echo All set. Double-click "Grocery Picker" to start.
pause
exit /b

:fail
echo.
echo Setup stopped on an error. Take a photo of this window and send it to Jared.
pause
