$ErrorActionPreference='Stop'
$Host.UI.RawUI.WindowTitle='Jetson CSV Test Data'
$target='192.168.213.167'
Write-Host ('Target Jetson: '+$target)
Write-Host 'Copies the test CSV and a read-only service. Existing AOI services are not changed.'
Write-Host 'No packages are installed. Local port 8601 uses an authenticated SSH tunnel.'
$account=Read-Host 'Jetson account (Enter = jetson)'
if([string]::IsNullOrWhiteSpace($account)){$account='jetson'}
if($account -notmatch '^[a-z_][a-z0-9_-]*[$]?$'){throw 'Enter the account name only, for example jetson.'}
$ssh=Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'
$scp=Join-Path $env:WINDIR 'System32/OpenSSH/scp.exe'
$keyscan=Join-Path $env:WINDIR 'System32/OpenSSH/ssh-keyscan.exe'
. (Join-Path $PSScriptRoot '../JetsonAOI/Verify-TeamJetsonHostKey.ps1')
$priorPreference=$ErrorActionPreference
try{$ErrorActionPreference='Continue';$keys=@(& $keyscan -T 5 -t ed25519 $target 2>$null)}finally{$ErrorActionPreference=$priorPreference}
$verified=Select-TeamJetsonHostKey -Lines $keys -TargetHost $target
$known=Join-Path $PSScriptRoot 'known_hosts'
$existing=if(Test-Path -LiteralPath $known){[IO.File]::ReadAllLines($known)}else{@()}
foreach($line in $existing){if($line -match ('^'+[regex]::Escape($target)+'\s+ssh-ed25519\s+') -and $line.Trim() -cne $verified){throw 'Saved Jetson host key conflict. Connection stopped.'}}
if($existing -cnotcontains $verified){[IO.File]::AppendAllText($known,$verified+[Environment]::NewLine,[Text.UTF8Encoding]::new($false))}
$options=@('-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$known")
$csvFiles=@(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.csv' -File)
if($csvFiles.Count -ne 1){throw 'Exactly one test CSV is required beside this launcher.'}
$csv=$csvFiles[0].FullName
$source=Join-Path $PSScriptRoot 'server.py'
$csvHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $csv).Hash.ToLowerInvariant()
$serverHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
$staging=Join-Path $PSScriptRoot 'Deployment'
New-Item -ItemType Directory -Force -Path $staging|Out-Null
$remoteCsv='unity_testdata_samples_'+$csvHash.Substring(0,12)+'.csv'
$remoteServer='unity_testdata_server_'+$serverHash.Substring(0,12)+'.py'
Copy-Item -LiteralPath $csv -Destination (Join-Path $staging $remoteCsv)
Copy-Item -LiteralPath $source -Destination (Join-Path $staging $remoteServer)
Write-Host 'STEP 1/2: Enter Jetson password to copy CSV and service.'
& $scp @options (Join-Path $staging $remoteCsv) (Join-Path $staging $remoteServer) ($account+'@'+$target+':./')
if($LASTEXITCODE -ne 0){throw 'Jetson copy failed.'}
Write-Host 'STEP 2/2: Enter Jetson password to start CSV service and tunnel.'
Write-Host 'Wait for UNITY_TEST_DATA_READY. Keep this window open while using Unity.'
Write-Host 'In Unity click Jetson CSV test data, receive data, select ID/source, then apply.'
Write-Host ('CSV SHA256: '+$csvHash)
& $ssh @options -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -tt -L '127.0.0.1:8601:127.0.0.1:8601' ($account+'@'+$target) ('python3 -u ./'+$remoteServer+' --csv ./'+$remoteCsv)
if($LASTEXITCODE -ne 0){Write-Host 'CSV service stopped or connection failed. Keep this error visible.';exit 1}
