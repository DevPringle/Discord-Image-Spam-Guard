@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
set "WEB_URL=http://127.0.0.1:5000"
set "STATUS_URL=%WEB_URL%/api/status"
set "BOT_START_URL=%WEB_URL%/bot/local-start"

if not exist "%PYTHON_EXE%" (
  echo.
  echo Virtual environment not found.
  echo Run setup_windows.bat first.
  echo.
  pause
  exit /b 1
)

echo Starting dashboard...
start "Image Spam Guard Dashboard" "%PYTHON_EXE%" run_web.py

echo Waiting for dashboard to come online...

set /a WAIT_COUNT=0
:wait_for_web
powershell -NoProfile -Command ^
  "try { $r = Invoke-WebRequest -UseBasicParsing '%STATUS_URL%' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"

if %errorlevel%==0 goto web_ready

set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 60 (
  echo.
  echo Dashboard did not come up.
  echo Check the dashboard window.
  echo.
  pause
  exit /b 1
)

timeout /t 1 /nobreak >nul
goto wait_for_web

:web_ready
echo Dashboard online.
start "" "%WEB_URL%"

echo Waiting for setup to be complete...

set /a SETUP_WAIT=0
:wait_for_setup
powershell -NoProfile -Command ^
  "try { $r = Invoke-RestMethod '%STATUS_URL%' -TimeoutSec 2; if ($r.setup_complete -and $r.ready_for_bot) { exit 0 } else { exit 1 } } catch { exit 1 }"

if %errorlevel%==0 goto start_bot

set /a SETUP_WAIT+=1
if %SETUP_WAIT% GEQ 1800 (
  echo.
  echo Setup not completed in time.
  echo You can finish setup in browser.
  echo.
  exit /b 0
)

timeout /t 1 /nobreak >nul
goto wait_for_setup

:start_bot
echo Requesting bot start from dashboard...

powershell -NoProfile -Command ^
  "try { Invoke-WebRequest -UseBasicParsing -Method POST '%BOT_START_URL%' -TimeoutSec 5 | Out-Null; exit 0 } catch { exit 1 }"

if %errorlevel%==0 (
  echo Bot start requested.
) else (
  echo Failed to request bot start.
)

exit /b 0