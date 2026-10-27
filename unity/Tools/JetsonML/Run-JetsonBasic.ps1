$ErrorActionPreference = 'Stop'
$toolDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$resultPath = Join-Path $toolDir 'latest-result.json'
$logPath = Join-Path $toolDir 'latest-run.log'
$runName = 'VirtualFabML_' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
$stagePath = Join-Path $toolDir $runName
$sshPath = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scpPath = Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$sshOptions = @('-o', 'ConnectTimeout=15', '-o', 'StrictHostKeyChecking=yes', '-o', ('UserKnownHostsFile=' + (Join-Path $toolDir 'known_hosts')))
$state = @{ status = 'preparing'; remote_folder = $runName }
try {
    New-Item -ItemType Directory -Path $stagePath | Out-Null
    $sourceRoot = Join-Path ([Environment]::GetFolderPath('Desktop')) '티캐드'
    foreach ($folder in @('최종ML', '진단에이전트')) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $folder) -Destination $stagePath -Recurse
    }
    Copy-Item -LiteralPath (Join-Path $toolDir 'basic_check.py') -Destination $stagePath
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $sourceHash = [Convert]::ToBase64String($hasher.ComputeHash([IO.File]::ReadAllBytes((Join-Path $sourceRoot '최종ML\모델\gp.npz'))))
        $copyHash = [Convert]::ToBase64String($hasher.ComputeHash([IO.File]::ReadAllBytes((Join-Path $stagePath '최종ML\모델\gp.npz'))))
    } finally { $hasher.Dispose() }
    if ($sourceHash -ne $copyHash) { throw 'Local model copy hash mismatch' }
    $state.status = 'waiting_for_copy_login'
    $state | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host 'STEP 1/2: Enter the Jetson password to copy the files. Password characters stay hidden.'
    & $scpPath @sshOptions -r $stagePath 'jetson@192.168.213.167:./'
    if ($LASTEXITCODE -ne 0) { throw 'SSH file transfer failed' }
    $state.status = 'waiting_for_test_login'
    $state | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host 'STEP 2/2: Enter the Jetson password again to run BASIC GP checks. No packages will be installed.'
    $remoteCommand = 'cd ' + $runName + ' && python3 -u basic_check.py'
    & $sshPath @sshOptions 'jetson@192.168.213.167' $remoteCommand 2>&1 | Tee-Object -FilePath $logPath
    if ($LASTEXITCODE -ne 0) { throw 'Jetson basic checks failed; see latest-run.log' }
    if (-not (Select-String -LiteralPath $logPath -SimpleMatch 'JETSON_BASIC_STATUS' -Quiet)) { throw 'No final test marker received' }
    $state.status = 'passed'
} catch {
    $state.status = 'failed'
    $state.error = $_.Exception.Message
    Write-Host $state.error -ForegroundColor Red
} finally {
    $state | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host ('Result: ' + $state.status)
    Write-Host ('Remote folder: ~/' + $runName)
    Read-Host 'Press Enter to close'
}
