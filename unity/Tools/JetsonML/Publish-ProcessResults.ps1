$ErrorActionPreference='Stop'
$toolDir=Split-Path -Parent $MyInvocation.MyCommand.Path
$socketDir=Join-Path (Split-Path -Parent $toolDir) 'FabSocket'
$basic=Get-Content -LiteralPath (Join-Path $toolDir 'latest-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$remoteFolder=$basic.remote_folder
if($basic.status -ne 'passed' -or $remoteFolder -notmatch '^VirtualFabML_[a-f0-9]{12}$'){throw 'Verified deployment missing'}
$options=@('-o','ConnectTimeout=15','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+(Join-Path $toolDir 'known_hosts')))
$ssh=Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scp=Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$state=@{status='waiting_for_copy_login'}
$statusFile=Join-Path $toolDir 'process-publish-status.json'
try {
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
    Write-Host 'STEP 1/2: Enter the Jetson password. Copy the publisher scripts.'
    & $scp @options (Join-Path $socketDir 'process_analysis.py') (Join-Path $socketDir 'publish_process_results.py') ('jetson@192.168.213.167:./'+$remoteFolder+'/')
    if($LASTEXITCODE -ne 0){throw 'Publisher upload failed'}
    $state.status='waiting_for_publish_login'
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
    Write-Host 'STEP 2/2: Enter the password again. An SSH tunnel will relay four labelled TEST results to Unity.'
    $remoteCommand='cd '+$remoteFolder+' && .venv-tabpfn-9.2/bin/python -m pip install --no-input --index-url https://pypi.org/simple websockets==15.0.1 && .venv-tabpfn-9.2/bin/python -u publish_process_results.py --config-stdin'
    $ErrorActionPreference='Continue'
    Get-Content -LiteralPath (Join-Path $toolDir 'process-ai.local.json') -Raw -Encoding UTF8 | & $ssh @options -o ExitOnForwardFailure=yes -R '127.0.0.1:18765:127.0.0.1:8765' 'jetson@192.168.213.167' $remoteCommand 2>&1 | Tee-Object -FilePath (Join-Path $toolDir 'process-publish.log')
    $code=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if($code -ne 0){throw 'Jetson publication failed; see process-publish.log'}
    $marker=Get-Content -LiteralPath (Join-Path $toolDir 'process-publish.log') -Encoding UTF8 | Where-Object {$_ -like 'JETSON_PROCESS_PUBLISH_RESULT *'} | Select-Object -Last 1
    if(-not $marker){throw 'Publisher did not return a result'}
    $report=$marker.Substring('JETSON_PROCESS_PUBLISH_RESULT '.Length) | ConvertFrom-Json
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $toolDir 'process-publish-result.json') -Encoding UTF8
    $state.status=$report.status
} catch {$state.status='failed';$state.error=$_.Exception.Message;Write-Host $state.error -ForegroundColor Red}
finally {$state | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8;Write-Host ('Result: '+$state.status);Read-Host 'Press Enter to close'}
