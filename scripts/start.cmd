@echo off
rem Q-CONSENSUS launcher: runs start.ps1 without touching the PowerShell
rem execution policy. Usage: scripts\start.cmd [command] [options]
rem Run "scripts\start.cmd help" for the list of commands.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
exit /b %ERRORLEVEL%
