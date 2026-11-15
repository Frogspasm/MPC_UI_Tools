@echo off
rem Starts the MPC UI tools server (tools\ui_server.py) and opens the layout editor and element designer.
rem Leave this window open while you work; close it to stop the server.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python tools\ui_server.py %*
) else (
  py -3 tools\ui_server.py %*
)
if errorlevel 1 pause
