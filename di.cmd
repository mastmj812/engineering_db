@echo off
rem deal-intake launcher: .\di <command> [args]  e.g.  .\di evaluate rallycaps
"%~dp0.venv\Scripts\python.exe" -m dealintake %*
