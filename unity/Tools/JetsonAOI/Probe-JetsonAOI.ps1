param(
 [string]$SshPath=(Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'),
 [string]$OutputDirectory=$PSScriptRoot
)
$ErrorActionPreference='Stop'
$toolDir=$PSScriptRoot
$hostFile=Join-Path $toolDir '../JetsonML/known_hosts'
$probe=Join-Path $toolDir 'probe_aoi_jetson.py'
$encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes($probe))
$remote="python3 -c 'import base64,sys;exec(base64.b64decode(sys.argv[1]))' $encoded"
Write-Host 'Read-only Jetson AOI check. Enter the Jetson login password below.'
Write-Host 'No installation or configuration changes. Do not share your password in chat.'
$response=@(& $SshPath -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$hostFile" jetson@192.168.213.167 $remote)
if($LASTEXITCODE -ne 0){Write-Host 'Jetson check failed. See the connection error above.';exit 1}
$json=$response -join [Environment]::NewLine
$inventory=$json | ConvertFrom-Json
if(-not $inventory.hostname){throw 'Jetson did not return a valid inventory.'}
$resultPath=Join-Path $OutputDirectory ('jetson-aoi-inventory-'+[Guid]::NewGuid().ToString('N')+'.json')
[IO.File]::WriteAllText($resultPath,$json,(New-Object Text.UTF8Encoding($false)))
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'jetson-aoi-inventory-latest.txt'),$resultPath,(New-Object Text.UTF8Encoding($false)))
Write-Host 'Jetson AOI inventory saved. Tell Codex that the check finished.'
