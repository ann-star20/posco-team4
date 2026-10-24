$ErrorActionPreference='Stop'
$folder=Join-Path $PSScriptRoot ('../../Temp/AoiProbeCheck-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $folder | Out-Null
$fake=Join-Path $folder 'fake-ssh.cmd'
$python='C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$argumentsCheck=Join-Path $PSScriptRoot 'test_probe_native_args.py'
Set-Content -LiteralPath $fake -Encoding ASCII -Value "@echo off`r`n`"$python`" `"$argumentsCheck`" %*`r`nexit /b %errorlevel%"
$locked=Join-Path $folder 'jetson-aoi-inventory.json'
$handle=[IO.File]::Open($locked,[IO.FileMode]::Create,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
 for($i=0;$i -lt 2;$i++){
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'Probe-JetsonAOI.ps1') -SshPath $fake -OutputDirectory $folder
  if($LASTEXITCODE -ne 0){throw 'Launcher failed while old inventory was locked'}
 }
 $files=@(Get-ChildItem $folder -Filter 'jetson-aoi-inventory-*.json')
 if($files.Count -ne 2){throw 'Each invocation must create its own inventory'}
 foreach($file in $files){if((Get-Content -Raw $file.FullName|ConvertFrom-Json).hostname -ne 'offline-test'){throw 'Invalid inventory'}}
 'PASS: Windows native argument quoting and payload execution; two runs with old inventory locked'
} finally {$handle.Dispose()}
