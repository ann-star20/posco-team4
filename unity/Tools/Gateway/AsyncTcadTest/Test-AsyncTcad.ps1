param([string]$DotnetPath='C:/Program Files/Unity/Hub/Editor/6000.6.4f1/Editor/Data/DotNetSdk/dotnet.exe')
$ErrorActionPreference='Stop'
$env:DOTNET_CLI_HOME=Join-Path $PSScriptRoot '../../../Temp/DotnetHome'
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
$project=Join-Path $PSScriptRoot 'Checks.csproj'
& $DotnetPath restore $project --ignore-failed-sources
if($LASTEXITCODE -ne 0){throw 'Test project restore failed.'}
$report=& $DotnetPath run --project $project --no-restore -- --socket
$code=$LASTEXITCODE
$report | Set-Content -Encoding UTF8 (Join-Path $PSScriptRoot 'offline-result.txt')
$report
if($code -ne 0){throw 'Async TCAD test failed. See offline-result.txt.'}
