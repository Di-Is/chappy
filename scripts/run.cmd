@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Determine repository root based on this script location
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"

set "PY_VERSION_FILE=%ROOT_DIR%\.python-version"
set "PY_VERSION="
if exist "%PY_VERSION_FILE%" (
  for /f "usebackq tokens=* delims=" %%V in ("%PY_VERSION_FILE%") do (
    if not defined PY_VERSION set "PY_VERSION=%%V"
  )
)
if not defined PY_VERSION (
  echo [ERROR] .python-version file not found or empty: %PY_VERSION_FILE%
  goto :fail
)

set "UV_ROOT=%ROOT_DIR%\.uv"
set "PY_ROOT=%UV_ROOT%\py"
if not exist "%UV_ROOT%" mkdir "%UV_ROOT%" >NUL 2>&1
if not exist "%PY_ROOT%" mkdir "%PY_ROOT%" >NUL 2>&1
if not exist "%PY_ROOT%\bin" mkdir "%PY_ROOT%\bin" >NUL 2>&1

set "UV_COMMAND="
for /f "usebackq tokens=* delims=" %%I in (`where uv 2^>NUL`) do (
  if not defined UV_COMMAND set "UV_COMMAND=%%I"
)
if not defined UV_COMMAND (
  echo [ERROR] uv command not found in PATH. Install uv or add it to PATH before running this script.
  set "UV_COMMAND=(not found)"
  goto :fail
)

rem Optional TLS switch passthrough
set "UV_TLS_SWITCH="
if /I "%UV_NATIVE_TLS%"=="true" set "UV_TLS_SWITCH=--native-tls"

set "VENV_DIR=%ROOT_DIR%\.venv"
set "ROOT_DIR_PUSHED="
rem Ensure uv runs relative to repository root so pyproject is discoverable
pushd "%ROOT_DIR%" >NUL 2>&1
if errorlevel 1 (
  echo [ERROR] Failed to change directory to %ROOT_DIR%
  goto :fail
)
set "ROOT_DIR_PUSHED=1"

call "%UV_COMMAND%" --no-config --managed-python --no-cache %UV_TLS_SWITCH% sync --frozen --no-dev --python %PY_VERSION%
if errorlevel 1 goto :fail

set "VENVBIN=%ROOT_DIR%\.venv\Scripts"
set "PYW=%VENVBIN%\pythonw.exe"
if not exist "%PYW%" set "PYW=%VENVBIN%\python.exe"
if not exist "%PYW%" (
  echo Python interpreter not found under %VENVBIN%
  goto :fail
)

rem Launch GUI (no console if pythonw.exe exists)
start "" /wait "%PYW%" -m chappy %*
if errorlevel 1 goto :fail
goto :success

:fail
set "RUN_FAIL_CODE=%ERRORLEVEL%"
if "%RUN_FAIL_CODE%"=="0" set "RUN_FAIL_CODE=1"
if defined ROOT_DIR_PUSHED popd >NUL
echo [ERROR] Setup or launch failed. Check the messages above.
call :wait_for_close "Press any key to close this window once you finish reading the errors."
exit /b %RUN_FAIL_CODE%

:success
if defined ROOT_DIR_PUSHED popd >NUL
call :wait_for_close
exit /b 0

:wait_for_close
if "%~1"=="" (
  echo.
  echo Press any key to close this window.
) else (
  echo.
  echo %~1
)
pause >NUL
goto :eof
