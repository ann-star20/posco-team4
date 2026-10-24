$ErrorActionPreference='Stop'
$toolDir=Split-Path -Parent $MyInvocation.MyCommand.Path
$basicResult=Get-Content -LiteralPath (Join-Path $toolDir 'latest-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$remoteFolder=$basicResult.remote_folder
if($basicResult.status -ne 'passed' -or $remoteFolder -notmatch '^VirtualFabML_[a-f0-9]{12}$'){throw 'No verified deployment found'}
$sshOptions=@('-o','ConnectTimeout=15','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+(Join-Path $toolDir 'known_hosts')))
$sshPath=Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scpPath=Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$statusPath=Join-Path $toolDir 'high-precision-install-status.json'
$state=@{status='waiting_for_copy_login';remote_folder=$remoteFolder}
try {
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host 'STEP 1/2: Enter the Jetson password to upload the installer and check.'
    & $scpPath @sshOptions (Join-Path $toolDir 'install_high_precision.py') (Join-Path $toolDir 'high_precision_check.py') ('jetson@192.168.213.167:./'+$remoteFolder+'/')
    if($LASTEXITCODE -ne 0){throw 'Upload failed'}
    $state.status='waiting_for_install_login'
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host 'STEP 2/2: Enter the password again. Install TabPFN 9.2.0 into a separate venv and test it.'
    $ErrorActionPreference='Continue'
    & $sshPath @sshOptions 'jetson@192.168.213.167' ('cd '+$remoteFolder+' && python3 -u install_high_precision.py') 2>&1 | Tee-Object -FilePath (Join-Path $toolDir 'high-precision-install.log')
    $remoteExit=$LASTEXITCODE
    $ErrorActionPreference='Stop'
    if($remoteExit -ne 0){throw 'Remote installer failed'}
    $marker=Get-Content -LiteralPath (Join-Path $toolDir 'high-precision-install.log') -Encoding UTF8 | Where-Object {$_ -like 'JETSON_HP_INSTALL_STATUS *'} | Select-Object -Last 1
    if(-not $marker){throw 'No final installation result received'}
    $report=$marker.Substring('JETSON_HP_INSTALL_STATUS '.Length) | ConvertFrom-Json
    $report | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $toolDir 'high-precision-install-result.json') -Encoding UTF8
    $state.status=$report.status
    Write-Host ('Result: '+$state.status)
} catch {
    $state.status='failed'
    $state.error=$_.Exception.Message
    Write-Host $state.error -ForegroundColor Red
} finally {
    $state | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Read-Host 'Press Enter to close'
}
