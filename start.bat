@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto setup_failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto setup_failed
.venv\Scripts\python.exe -m tester %*
if errorlevel 1 goto start_failed
exit /b 0
:setup_failed
echo Python setup failed. Check Python 3.11+, pip, the py launcher and the error above.
pause
exit /b 1
:start_failed
echo App start failed. See the specific error above. For a blocked web port, try start.bat --http-port 8767.
pause
exit /b 1
