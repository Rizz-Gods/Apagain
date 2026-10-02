$startup = [Environment]::GetFolderPath("Startup")
Copy-Item "$PSScriptRoot\OTH-Daemon.vbs" (Join-Path $startup "OTH-Daemon.vbs") -Force
Write-Host "OTH daemon startup hook installed for the current Windows user."
