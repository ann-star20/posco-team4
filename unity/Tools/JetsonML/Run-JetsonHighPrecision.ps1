param([switch]$Agent)
$ErrorActionPreference = 'Stop'
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$prefix = if($Agent){'agent-high-precision'}else{'high-precision'}
$scriptName = if($Agent){'agent_high_precision_check.py'}else{'high_precision_check.py'}
$markerPrefix = if($Agent){'JETSON_HP_AGENT_STATUS '}else{'JETSON_HP_STATUS '}
$statusPath = Join-Path $toolDir ($prefix+'-launch-status.json')
$logPath = Join-Path $toolDir ($prefix+'-jetson.log')
$basicResult = Get-Content -LiteralPath (Join-Path $toolDir 'latest-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$remoteFolder = $basicResult.remote_folder
if ($basicResult.status -ne 'passed' -or $remoteFolder -notmatch '^VirtualFabML_[a-f0-9]{12}$') {throw 'No verified basic-GP deployment found'}
$sshOptions = @('-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=yes', '-o', ('UserKnownHostsFile='+(Join-Path $toolDir 'known_hosts')))
$sshPath = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scpPath = Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$state = @{status='waiting_for_copy_login';remote_folder=$remoteFolder}
try {
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host 'STEP 1/2: Enter the Jetson password to upload the high-precision check.'
    & $scpPath @sshOptions (Join-Path $toolDir $scriptName) ('jetson@192.168.213.167:./'+$remoteFolder+'/')
    if($LASTEXITCODE -ne 0){throw 'Check upload failed'}
    $state.status='waiting_for_test_login'
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host 'STEP 2/2: Enter the password again. Existing high-precision venv; no installation. Allow up to five minutes.'
    $ErrorActionPreference='Continue'
    & $sshPath @sshOptions 'jetson@192.168.213.167' ('cd '+$remoteFolder+' && .venv-tabpfn-9.2/bin/python -u '+$scriptName) 2>&1 | Tee-Object -FilePath $logPath
    $remoteExit=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if($remoteExit -ne 0){throw ('Remote check failed; see '+$logPath)}
    $marker=Get-Content -LiteralPath $logPath -Encoding UTF8 | Where-Object {$_.StartsWith($markerPrefix)} | Select-Object -Last 1
    if(-not $marker){throw 'No high-precision result received'}
    $report=$marker.Substring($markerPrefix.Length) | ConvertFrom-Json
    if($Agent -and $report.status -eq 'passed' -and $report.results.Count -ne 4){throw 'Incomplete full-flow result'}
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $toolDir ($prefix+'-jetson-result.json')) -Encoding UTF8
    $state.status=$report.status
    Write-Host ('High precision result: '+$report.status)
} catch {
    $state.status='failed'
    $state.error=$_.Exception.Message
    Write-Host $state.error -ForegroundColor Red
} finally {
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Read-Host 'Press Enter to close'
}
