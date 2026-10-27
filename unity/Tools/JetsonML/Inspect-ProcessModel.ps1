$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Jetson Process Model Location Check'
$ssh=Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'
$known=Join-Path $PSScriptRoot 'known_hosts'
Write-Host 'Target: existing ML Jetson 192.168.213.167'
Write-Host 'Read-only check of model paths and Python modules. No packages or settings are changed.'
Write-Host 'Enter the Jetson password only in this window. Do not send it in chat.'
$encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'probe_process_model.py')))
$remote="python3 -c 'import base64,sys;exec(base64.b64decode(sys.argv[1]))' $encoded"
$response=@(& $ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" jetson@192.168.213.167 $remote)
if($LASTEXITCODE -ne 0){throw 'Model location check failed. Keep the SSH error visible.'}
$json=$response -join [Environment]::NewLine
$report=$json|ConvertFrom-Json
if($report.schema_version -ne 1 -or -not $report.home){throw 'Invalid model inventory response'}
$report | Add-Member -NotePropertyName target -NotePropertyValue '192.168.213.167' -Force
$json=$report | ConvertTo-Json -Depth 12
$file=Join-Path $PSScriptRoot ('process-model-inventory-'+[Guid]::NewGuid().ToString('N')+'.json')
[IO.File]::WriteAllText($file,$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'process-model-inventory-latest.txt'),$file,[Text.UTF8Encoding]::new($false))
Write-Host 'MODEL_INVENTORY_SAVED. Tell Codex the check finished.'
