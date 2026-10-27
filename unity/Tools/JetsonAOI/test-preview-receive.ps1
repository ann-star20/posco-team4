$ErrorActionPreference='Stop'
$root=Join-Path $PSScriptRoot '../../Assets/MOSFETInspection'
Add-Type -Path @((Join-Path $root 'AoiDirectProtocol.cs'),(Join-Path $root 'AoiCameraProtocol.cs'),(Join-Path $root 'AoiPreviewProtocol.cs'),(Join-Path $PSScriptRoot 'PreviewReceiveChecks.cs'))
[PreviewReceiveChecks]::Run().GetAwaiter().GetResult()
Write-Output 'PREVIEW_RECEIVE_OK: subscribed, two metadata/binary pairs, fragmented 70001-byte images, single receiver, close handling'
