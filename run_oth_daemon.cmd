@echo off
cd /d "C:\Users\Admin\Documents\Over-The-Horizon"
set "FFMPEG_BIN=C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
set "GIT_LFS_BIN=C:\Users\Admin\bin\git-lfs\git-lfs-3.8.0"
set "PATH=%FFMPEG_BIN%;%GIT_LFS_BIN%;%PATH%"
echo [%date% %time%] OTH daemon starting>> "logs\daemon.log"
".venv\Scripts\python.exe" -m oth.cli daemon --interval 5 >> "logs\daemon.log" 2>&1
echo [%date% %time%] OTH daemon exited>> "logs\daemon.log"
