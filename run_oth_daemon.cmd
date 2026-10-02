@echo off
cd /d "C:\Users\Admin\Documents\Over-The-Horizon"
echo [%date% %time%] OTH daemon starting>> "logs\daemon.log"
".venv\Scripts\python.exe" -m oth.cli daemon --interval 5 >> "logs\daemon.log" 2>&1
echo [%date% %time%] OTH daemon exited>> "logs\daemon.log"
