@echo off
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Startup'); Remove-Item ($d+'\JARVIS.lnk') -ErrorAction SilentlyContinue"
echo JARVIS ne se lancera plus automatiquement avec Windows.
pause
