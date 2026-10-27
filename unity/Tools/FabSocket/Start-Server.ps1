param([switch]$Demo)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonRuntime = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $pythonRuntime)) { throw 'Python runtime not found. Run server.py with Python 3.9 or later.' }
if ($Demo) { & $pythonRuntime (Join-Path $PSScriptRoot 'demo.py') }
else { & $pythonRuntime -u (Join-Path $PSScriptRoot 'server.py') }
exit $LASTEXITCODE
