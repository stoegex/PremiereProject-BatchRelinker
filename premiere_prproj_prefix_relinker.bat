@echo off
setlocal
title Premiere Project Batch Relinker
chcp 65001 >nul

set "TOOL=%~dp0premiere_prproj_prefix_relinker.py"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%TOOL%" %*
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo.
    echo Python 3 was not found.
    echo Install Python from https://www.python.org/downloads/ and enable "Add Python to PATH".
    echo.
    pause
    exit /b 1
  )
  python "%TOOL%" %*
)

echo.
pause
