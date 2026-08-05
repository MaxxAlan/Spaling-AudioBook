@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Spaling Audiobook Installer

set "PYTHON_EXE=%CD%\.runtime\python\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [BOOTSTRAP] Dang tai Python 3.11 portable de chay install.py...
    if not exist "%CD%\.data\downloads" mkdir "%CD%\.data\downloads"
    curl.exe -fL -sS -o "%CD%\.data\downloads\python.zip" "https://www.nuget.org/api/v2/package/python/3.11.9"
    if errorlevel 1 goto :FAIL
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; New-Item -ItemType Directory -Force -Path '%CD%\.runtime\python' | Out-Null; Expand-Archive -LiteralPath '%CD%\.data\downloads\python.zip' -DestinationPath '%CD%\.data\downloads\python-nuget' -Force; Copy-Item -Recurse -Force '%CD%\.data\downloads\python-nuget\tools\*' '%CD%\.runtime\python'"
    if errorlevel 1 goto :FAIL
)

"%PYTHON_EXE%" "%CD%\install.py" %*
if errorlevel 1 goto :FAIL

start "" /b "%CD%\audiobook.bat" web
exit /b 0

:FAIL
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" set "EXIT_CODE=1"
echo.
echo ================================================================
echo [FAILED] CAI DAT THAT BAI
echo ================================================================
echo Ma loi: %EXIT_CODE%
echo.
pause
endlocal
exit /b %EXIT_CODE%
