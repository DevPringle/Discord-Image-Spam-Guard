@echo off
setlocal
cd /d "%~dp0"

echo.
echo === Discord Image Spam Guard rebuild ===
echo.

echo This will delete .venv and rebuild it from scratch.
echo .env will be left alone.
echo.
choice /M "Continue"
if errorlevel 2 exit /b 0

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

if exist ".venv" (
    echo Removing old virtual environment...
    rmdir /s /q ".venv"
)

echo Creating fresh virtual environment...
%PY_CMD% -m venv .venv
if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
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

echo.
echo Rebuild finished.
echo .env was left alone.
echo.
pause
