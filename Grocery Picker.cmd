@echo off
rem One block on purpose: cmd reads a .cmd file as it runs, and update.py may rewrite this file.
(
  if not exist "%~dp0.venv\Scripts\python.exe" echo Run Setup first.& pause& exit /b
  "%~dp0.venv\Scripts\python.exe" "%~dp0update.py"
  "%~dp0.venv\Scripts\python.exe" "%~dp0groceries.py"
  if errorlevel 1 (echo.& echo The picker stopped on an error. If it mentions a token or login, run Setup again.& pause)
  exit /b
)
