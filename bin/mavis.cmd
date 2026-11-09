@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "_MAVIS_CODEPAGE="
for /f "tokens=2 delims=:" %%C in ('chcp') do set "_MAVIS_CODEPAGE=%%C"
if not defined _MAVIS_CODEPAGE exit /b 1
chcp 65001 >nul
if errorlevel 1 exit /b 1
set "ELECTRON_RUN_AS_NODE=1"
"<HOME>\.minimax-code\runtime\node-v22.19.0-win-x64\node.exe" "%~dp0mavis.js" %*
set "_MAVIS_EXIT_CODE=%ERRORLEVEL%"
chcp %_MAVIS_CODEPAGE% >nul
exit /b %_MAVIS_EXIT_CODE%
