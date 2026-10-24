param([switch]$NoMockUnity)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$envFile = Join-Path $repo '.env'
if (-not (Test-Path -LiteralPath $envFile)) { throw '.env 파일이 없습니다.' }
foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
    if ($line -match '^\s*(#|$)') { continue }
    $pair = $line -split '=', 2
    if ($pair.Count -ne 2) { throw '.env 형식 오류' }
    [Environment]::SetEnvironmentVariable($pair[0].Trim(), $pair[1].Trim().Trim('"').Trim("'"), 'Process')
}
$env:PYTHONPATH = (Join-Path $repo 'services/event_gateway/src')
foreach ($required in @('DATABASE_URL', 'APPROVAL_OPERATOR', 'APPROVAL_TOKEN', 'ROS_COMMAND_KEY')) {
    if (-not [Environment]::GetEnvironmentVariable($required, 'Process')) {
        throw "$required 값을 .env에 설정해야 합니다."
    }
}
$python = (Get-Command python).Source
$owned = @()
try {
    if ($env:TCAD_MODE -eq 'mock') {
        $owned += Start-Process -FilePath $python -ArgumentList '-m mock_tcad.app' -WorkingDirectory $repo -WindowStyle Hidden -PassThru
    }
    $owned += Start-Process -FilePath $python -ArgumentList '-m event_gateway.verification_worker' -WorkingDirectory $repo -WindowStyle Hidden -PassThru
    $owned += Start-Process -FilePath $python -ArgumentList '-m event_gateway.app' -WorkingDirectory $repo -WindowStyle Hidden -PassThru
    Write-Host 'Gateway와 TCAD worker를 시작했습니다. ROS bridge는 WSL의 ROS 환경에서 별도 실행하세요.'
    if ($env:UNITY_MODE -eq 'mock' -and -not $NoMockUnity) {
        Write-Host 'Mock Unity는 FAB_RUN_ID를 지정한 뒤 python tools/mock_unity/client.py로 실행하세요.'
    }
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    foreach ($process in $owned) {
        if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id }
    }
}
