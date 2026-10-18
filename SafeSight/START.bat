@echo off
REM Double-click to start SafeSight in demo mode and open the dashboard.
REM Optional: START.bat file:C:\path\to\meta.jsonl   (live PipeGen output)
cd /d "%~dp0"
set "PY="
set "PYARGS="
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py" & set "PYARGS=-3")
if defined PY goto found
where python >nul 2>nul
if %errorlevel%==0 set "PY=python"
if defined PY goto found
if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
if defined PY goto found
echo Python 3 was not found. Install it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH", then double-click START.bat again.
pause
exit /b 1
:found
set "SRC=%~1"
if "%SRC%"=="" set "SRC=sim"
echo Using Python: %PY%
echo Starting SafeSight (source %SRC%). Keep this window open.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8080"
"%PY%" %PYARGS% -m safesight --source %SRC%
echo.
echo SafeSight stopped. If you saw an error above, send a screenshot to Claude.
pause
