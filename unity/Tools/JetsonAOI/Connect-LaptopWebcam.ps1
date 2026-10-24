$ErrorActionPreference='Stop'
Write-Host 'Start AOI-Webcam.exe on the camera laptop first.'
Write-Host 'Copy its video URL or enter its IPv4 address below.'
$value=(Read-Host 'Laptop camera URL or IP').Trim()
if($value -match '^http://'){
    $uri=$null
    if(-not [Uri]::TryCreate($value,[UriKind]::Absolute,[ref]$uri) -or $uri.Scheme -ne 'http' -or $uri.Port -ne 8080 -or $uri.AbsolutePath -ne '/video' -or $uri.UserInfo -or $uri.Query -or $uri.Fragment){throw 'Expected http://LAPTOP_IP:8080/video'}
    $value=$uri.Host
}
$parsed=$null
if(-not [Net.IPAddress]::TryParse($value,[ref]$parsed) -or $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or [Net.IPAddress]::IsLoopback($parsed) -or $parsed.IPAddressToString -eq '0.0.0.0'){throw 'Use the laptop LAN IPv4 address, not localhost.'}
& (Join-Path $PSScriptRoot 'Start-Aoi8500And8400.ps1') -Restart -LaptopCameraHost $parsed.IPAddressToString
exit $LASTEXITCODE
