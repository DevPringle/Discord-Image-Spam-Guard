@echo off
setlocal
cd /d "%~dp0"

echo.
echo === Discord Image Spam Guard setup ===
echo.

if not exist requirements.txt (
    echo requirements.txt was not found.
    echo Run this from the project folder.
    pause
    exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY_CMD=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PY_CMD=python"
    ) else (
        echo Python was not found in PATH.
        echo Install Python 3.11+ first, then run this again.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

echo.
echo Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed while upgrading pip.
    pause
    exit /b 1
)

echo.
echo Installing packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Failed while installing packages.
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        echo.
        echo Creating .env from .env.example...
        copy /Y ".env.example" ".env" >nul
    ) else (
        echo.
        echo .env.example was not found, so .env was not created.
    )
) else (
    echo.
    echo .env already exists. Leaving it alone.
)

echo.
echo Setup finished.
echo If this is your first run, open the dashboard or the .env file and fill in your token, guild ID, and dashboard password.
echo.
pause
