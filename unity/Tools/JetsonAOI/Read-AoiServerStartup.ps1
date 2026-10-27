$ErrorActionPreference='Stop'
$toolDir=$PSScriptRoot
$destination=Join-Path $toolDir 'CurrentServerStartup'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$known=Join-Path $toolDir '../JetsonML/known_hosts'
$scp=Join-Path $env:WINDIR 'System32/OpenSSH/scp.exe'
$options=@('-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$known")
Write-Host 'Read existing AOI 8500/8400 startup source from Jetson 192.168.213.167.'
Write-Host 'No server changes, package installation or token output.'
Write-Host 'Enter the Jetson password. Do not send the password to chat.'
& $scp @options 'jetson@192.168.213.167:/home/jetson/project/smart_factory/jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_unity.py' $destination
if($LASTEXITCODE -ne 0){throw 'Source read failed. Keep this window open to inspect the error.'}
Write-Host 'SOURCE_RECEIVED. Current inspection handler copied; tell Codex the copy completed.'
