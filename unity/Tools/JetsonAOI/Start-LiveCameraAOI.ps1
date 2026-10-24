$ErrorActionPreference='Stop'
$toolDir=$PSScriptRoot
$source=Join-Path $toolDir 'unity_aoi_camera_server.py'
$hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant().Substring(0,12)
$remoteFile='unity_aoi_camera_'+$hash+'.py'
$known=Join-Path $toolDir '../JetsonML/known_hosts'
$options=@('-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$known")
$scp=Join-Path $env:WINDIR 'System32/OpenSSH/scp.exe'
$ssh=Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe'
$deployment=Get-Content -LiteralPath (Join-Path $toolDir '../JetsonML/latest-result.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if($deployment.status -ne 'passed' -or $deployment.remote_folder -notmatch '^VirtualFabML_[a-f0-9]{12}$'){throw 'Verified Jetson Python environment not found'}
$remotePython='./'+$deployment.remote_folder+'/.venv-tabpfn-9.2/bin/python'
Write-Host 'STEP 1/2: Enter Jetson login password to copy the camera adapter.'
Write-Host 'Original AOI files are not replaced. No packages will be installed.'
& $scp @options $source ('jetson@192.168.213.167:./'+$remoteFile)
if($LASTEXITCODE -ne 0){Write-Host 'Camera adapter copy failed.';exit 1}
$bytes=New-Object byte[] 32
$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
try{$rng.GetBytes($bytes)}finally{$rng.Dispose()}
$sessionToken=[Convert]::ToBase64String($bytes)
[Array]::Clear($bytes,0,$bytes.Length)
try {
 Set-Clipboard -Value $sessionToken
 Write-Host 'A new AOI session token was copied to your clipboard. It is not saved or printed.'
 Write-Host 'STEP 2/2: Enter Jetson login password to start the real camera inspection server.'
 Write-Host 'Keep this window open. Wait for UNITY_CAMERA_AOI_READY.'
 Write-Host 'Using the existing high-precision Python environment to avoid the NumPy 2 compatibility conflict.'
 Write-Host 'After Unity refresh: connect the phone camera, paste the clipboard into the AOI token field, then click Current frame inspection.'
 $payload=@{
  token=$sessionToken
  model_paths=@{
   AOI_PART_MODEL_FILE='/home/jetson/project/smart_factory/aoi/models/mosfet_part_v5-26/weights/best.pt'
   AOI_DEFECT_MODEL_FILE='/home/jetson/project/smart_factory/aoi/models/mosfet_defect_v5-26/weights/best.pt'
  }
 }|ConvertTo-Json -Compress
 # Windows PowerShell treats native stderr as errors, including harmless model warnings.
 $previousPreference=$ErrorActionPreference
 try {
  $ErrorActionPreference='Continue'
  $payload | & $ssh @options -o ServerAliveInterval=15 -o ServerAliveCountMax=3 jetson@192.168.213.167 ($remotePython+' -u ./'+$remoteFile+' --replace-existing 2>&1') 2>&1 | ForEach-Object {
   $line=$_.ToString()
   if($line.StartsWith('UNITY_CAMERA_AOI_READY ')){
    Set-Clipboard -Value $sessionToken
    Write-Host 'READY: Current server token copied again. Switch to Unity and paste it without copying this log.'
   }
   $line
  } | Tee-Object -FilePath (Join-Path $toolDir 'live-camera-aoi-server.log')
  $serverExitCode=$LASTEXITCODE
 } finally {$ErrorActionPreference=$previousPreference}
 if($serverExitCode -ne 0){Write-Host ('Camera AOI server stopped. Exit code: '+$serverExitCode+'. Keep the error message visible.');exit 1}
} finally {$sessionToken=$null;$payload=$null}
