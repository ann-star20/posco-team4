$ErrorActionPreference='Stop'
$toolDir=$PSScriptRoot
$known=Join-Path $toolDir '../JetsonML/known_hosts'
$destination=Join-Path $toolDir ('JetsonSource-'+(Get-Date -Format yyyyMMdd-HHmmss))
New-Item -ItemType Directory -Path $destination | Out-Null
$scp=Join-Path $env:WINDIR 'System32/OpenSSH/scp.exe'
Write-Host 'Read AOI Python source from Jetson. No installation or remote changes.'
Write-Host 'Enter the Jetson login password. Source files stay on this PC.'
& $scp -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" 'jetson@192.168.213.167:/home/jetson/project/smart_factory/jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_*.py' $destination
if($LASTEXITCODE -ne 0){Write-Host 'Source copy failed. Keep this window open to read the error.';exit 1}
Set-Content -Encoding UTF8 -LiteralPath (Join-Path $toolDir 'jetson-aoi-source-latest.txt') -Value $destination
Write-Host 'AOI source received. Tell Codex that the copy finished.'
