$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Jetson Phone Camera Connection Check'
Write-Host 'Target Jetson: 192.168.213.167'
Write-Host 'Phone source to test: http://192.168.10.123:8080/video'
Write-Host 'Read-only check. No services will be restarted and no settings changed.'
Write-Host 'Enter the Jetson Linux account name. Ask your teammate if it is unknown.'
$account=Read-Host 'Jetson account (Enter = jetson)'
if([string]::IsNullOrWhiteSpace($account)){$account='jetson'}
if($account -notmatch '^[a-z_][a-z0-9_-]*[$]?$'){throw 'Invalid account name.'}
$ssh=Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'
$knownHosts=Join-Path $PSScriptRoot 'known_hosts-team'
. (Join-Path $PSScriptRoot 'Verify-TeamJetsonHostKey.ps1')
Write-Host 'Checking the host fingerprint already confirmed by your teammate...'
$previousErrorAction=$ErrorActionPreference
try{$ErrorActionPreference='Continue';$keys=@(& (Join-Path $env:WINDIR 'System32/OpenSSH/ssh-keyscan.exe') -T 5 -t ed25519 192.168.213.167 2>$null)}finally{$ErrorActionPreference=$previousErrorAction}
$verified=Select-TeamJetsonHostKey $keys
$existing=if(Test-Path -LiteralPath $knownHosts){[IO.File]::ReadAllLines($knownHosts)}else{@()}
foreach($entry in $existing){if($entry -match '^192\.168\.10\.253\s+ssh-ed25519\s+' -and $entry.Trim() -cne $verified){throw 'A conflicting saved host key exists. Keep this message visible for Codex.'}}
if($existing -cnotcontains $verified){[IO.File]::AppendAllText($knownHosts,$verified+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))}
Write-Host 'Verified Jetson fingerprint. No yes/no input is needed.'
Write-Host 'Enter the Jetson login password only in this window. Do not send it in chat.'
$encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'probe_team_camera.py')))
$remote="python3 -c 'import base64,sys;exec(base64.b64decode(sys.argv[1]))' $encoded"
$response=@(& $ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" "$account@192.168.213.167" $remote)
if($LASTEXITCODE -ne 0){Write-Host 'Connection check failed. Keep the SSH error visible.';exit 1}
$json=$response -join [Environment]::NewLine
$data=$json|ConvertFrom-Json
if(-not $data.phone_url){throw 'No valid camera inventory returned.'}
$file=Join-Path $PSScriptRoot ('team-camera-inventory-'+[Guid]::NewGuid().ToString('N')+'.json')
[IO.File]::WriteAllText($file,$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'team-camera-inventory-latest.txt'),$file,[Text.UTF8Encoding]::new($false))
Write-Host 'Camera inventory saved. Tell Codex the check finished.'
