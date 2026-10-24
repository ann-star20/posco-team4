param([switch]$Restart,[string]$LaptopCameraHost='')
$ErrorActionPreference='Stop'
$toolDir=$PSScriptRoot
$ssh=Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'
$known=Join-Path $toolDir '../JetsonML/known_hosts'
$script=Join-Path $toolDir 'start_aoi_existing.sh'
Write-Host 'Jetson 192.168.213.167: preview 8500 + inspection 8400'
Write-Host 'Uses existing server, models and environment files. No package installation.'
Write-Host 'Enter the Jetson password. Keep this window open while using AOI.'
Write-Host 'Wait for AOI_8500_8400_READY. Ctrl+C stops this server session.'
$body=[IO.File]::ReadAllText($script).Replace("`r`n","`n").Replace("`r","")
if($LaptopCameraHost){
    $parsed=$null
    if(-not [Net.IPAddress]::TryParse($LaptopCameraHost,[ref]$parsed) -or $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork){throw 'Enter a valid laptop IPv4 address.'}
    $body="export AOI_LAPTOP_CAMERA_HOST=$($parsed.IPAddressToString)`n"+$body
    Write-Host "Laptop camera: http://$($parsed.IPAddressToString):8080/video (this session only)"
}
if($Restart){$body="export AOI_RESTART_EXISTING=1`n"+$body;Write-Host 'Restart mode: only the verified current-user AOI process on these ports may be stopped.'}
$encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($body))
# Send source as an argument, not a Windows text pipeline that appends CRLF.
$remote="python3 -c 'import base64,subprocess,sys;sys.exit(subprocess.run(sys.argv[2:],input=base64.b64decode(sys.argv[1])).returncode)' $encoded bash -s"
& $ssh -tt -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known" jetson@192.168.213.167 $remote
if($LASTEXITCODE -ne 0){Write-Host 'AOI startup stopped. Read the error above.';exit 1}
