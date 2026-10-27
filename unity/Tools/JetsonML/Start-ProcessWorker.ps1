$ErrorActionPreference='Stop'
$toolDir=Split-Path -Parent $MyInvocation.MyCommand.Path
$socketDir=Join-Path (Split-Path -Parent $toolDir) 'FabSocket'
$basic=Get-Content -LiteralPath (Join-Path $toolDir 'latest-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$remoteFolder=$basic.remote_folder
if($basic.status -ne 'passed' -or $remoteFolder -notmatch '^VirtualFabML_[a-f0-9]{12}$'){throw 'Verified deployment missing'}
$options=@('-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+(Join-Path $toolDir 'known_hosts')))
$ssh=Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scp=Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$statusFile=Join-Path $toolDir 'process-worker-status.json'
$state=@{status='waiting_for_copy_login'}
try {
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
    Write-Host 'STEP 1/2: Enter the Jetson password to copy the request listener.'
    & $scp @options (Join-Path $socketDir 'process_analysis.py') (Join-Path $socketDir 'process_worker.py') ('jetson@192.168.213.167:./'+$remoteFolder+'/')
    if($LASTEXITCODE -ne 0){throw 'Worker upload failed'}
    $state.status='waiting_for_worker_login'
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
    Write-Host 'STEP 2/2: Enter the password again. KEEP THIS WINDOW OPEN while Unity requests new analyses.'
    Write-Host 'Existing models and the verified high-precision environment will be used. No packages are installed.'
    $remoteCommand='cd '+$remoteFolder+' && .venv-tabpfn-9.2/bin/python -u process_worker.py --config-stdin'
    $ErrorActionPreference='Continue'
    Get-Content -LiteralPath (Join-Path $toolDir 'process-ai.local.json') -Raw -Encoding UTF8 | & $ssh @options -o ExitOnForwardFailure=yes -R '127.0.0.1:18765:127.0.0.1:8765' 'jetson@192.168.213.167' $remoteCommand 2>&1 | ForEach-Object { if ($_.ToString() -eq 'PROCESS_WORKER_CONNECTED') { $state.status='running'; $state | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8 }; $_ } | Tee-Object -FilePath (Join-Path $toolDir 'process-worker.log')
    $code=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if($code -ne 0){throw 'Worker stopped with an error; see process-worker.log'}
    $state.status='stopped'
} catch {$state.status='failed';$state.error=$_.Exception.Message;Write-Host $state.error -ForegroundColor Red}
finally {$state | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8;Write-Host ('Worker: '+$state.status);Read-Host 'Press Enter to close'}
