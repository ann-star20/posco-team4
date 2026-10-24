$ErrorActionPreference = 'Stop'
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$statusPath = Join-Path $toolDir 'agent-launch-status.json'
$logPath = Join-Path $toolDir 'agent-jetson.log'
$basicResult = Get-Content -LiteralPath (Join-Path $toolDir 'latest-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$remoteFolder = $basicResult.remote_folder
if ($basicResult.status -ne 'passed' -or $remoteFolder -notmatch '^VirtualFabML_[a-f0-9]{12}$') { throw 'No verified basic-GP deployment found' }
$sshOptions = @('-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=yes', '-o', ('UserKnownHostsFile=' + (Join-Path $toolDir 'known_hosts')))
$sshPath = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scpPath = Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$state = @{status='waiting_for_copy_login'; remote_folder=$remoteFolder}
try {
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host 'STEP 1/2: Enter the Jetson password to upload diagnostic checks and PC references.'
    & $scpPath @sshOptions (Join-Path $toolDir 'agent_check.py') (Join-Path $toolDir 'agent_reference.json') ('jetson@192.168.213.167:./'+$remoteFolder+'/')
    if ($LASTEXITCODE -ne 0) {throw 'Diagnostic check upload failed'}
    $state.status='waiting_for_test_login'
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host 'STEP 2/2: Enter the Jetson password again. Four BASIC-GP diagnosis cases will run.'
    & $sshPath @sshOptions 'jetson@192.168.213.167' ('cd '+$remoteFolder+' && python3 -u agent_check.py') 2>&1 | Tee-Object -FilePath $logPath
    if ($LASTEXITCODE -ne 0) {throw 'Jetson diagnostic checks failed; see agent-jetson.log'}
    $marker = Get-Content -LiteralPath $logPath -Encoding UTF8 | Where-Object {$_ -like 'JETSON_AGENT_STATUS *'} | Select-Object -Last 1
    if (-not $marker) {throw 'No final diagnostic result received'}
    $report = $marker.Substring('JETSON_AGENT_STATUS '.Length) | ConvertFrom-Json
    if ($report.status -ne 'passed' -or $report.results.Count -ne 4) {throw 'Incomplete diagnostic result'}
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $toolDir 'agent-jetson-result.json') -Encoding UTF8
    $state.status='passed'
} catch {
    $state.status='failed'
    $state.error=$_.Exception.Message
    Write-Host $state.error -ForegroundColor Red
} finally {
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host ('Result: '+$state.status)
    Read-Host 'Press Enter to close'
}
