@echo off
set RUNTIME_ROOT=C:\lion\runtime\living-folders

if "%~1"=="" (
    python -m livingfolders --execroot "%RUNTIME_ROOT%"
) else (
    python -m livingfolders --execroot "%RUNTIME_ROOT%" --execpath.open-at "%~1"
)
