@echo off
setlocal EnableDelayedExpansion
rem One block on purpose: cmd reads a .cmd file as it runs, and update.py may rewrite this file.
rem GROCERY_PYTHON (optional) points at a Python kept outside this folder, e.g. when the folder is in OneDrive.
(
  set "PY=%~dp0.venv\Scripts\python.exe"
  if defined GROCERY_PYTHON set "PY=!GROCERY_PYTHON!"
  if not exist "!PY!" echo Run Setup first.& pause& exit /b
  "!PY!" "%~dp0update.py"
  "!PY!" "%~dp0groceries.py"
  if errorlevel 1 (echo.& echo The picker stopped on an error. If it mentions a token or login, run Setup again.& pause)
  exit /b
)
