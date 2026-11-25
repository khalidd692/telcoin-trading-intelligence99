# Cree un raccourci Bureau facultatif pour TEL99 Command Center (aucun demarrage automatique Windows).
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Launcher = Join-Path $Repo "launch-tel99.ps1"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "TEL99 Command Center.lnk"

$Wsh = New-Object -ComObject WScript.Shell
$Sc = $Wsh.CreateShortcut($ShortcutPath)
$Sc.TargetPath = (Get-Command pwsh -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
if (-not $Sc.TargetPath) { $Sc.TargetPath = (Get-Command powershell -ErrorAction Stop).Source }
$Sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`" -Mode CommandCenter -OpenBrowser"
$Sc.WorkingDirectory = $Repo
$Sc.Description = "Ouvrir TEL99 Command Center (12 agents IA personnels, 127.0.0.1:8765)"
$Sc.WindowStyle = 7
$Sc.Save()
Write-Host "Raccourci Bureau cree : $ShortcutPath"
