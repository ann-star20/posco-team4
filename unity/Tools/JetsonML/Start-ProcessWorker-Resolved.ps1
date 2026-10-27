param([switch]$PrepareOnly,[ValidateRange(1024,65535)][int]$RemotePort=(Get-Random -Minimum 20000 -Maximum 60000))
$ErrorActionPreference='Stop'
$toolDir=$PSScriptRoot
$socketDir=Join-Path (Split-Path -Parent $toolDir) 'FabSocket'
$statusFile=Join-Path $toolDir 'process-worker-status.json'
$state=@{status='preparing';target='192.168.213.167'}
try {
    $pointer=Join-Path $toolDir 'process-model-inventory-latest.txt'
    if(-not(Test-Path -LiteralPath $pointer)){& (Join-Path $toolDir 'Inspect-ProcessModel.ps1')}
    $inventoryPath=[IO.Path]::GetFullPath(([IO.File]::ReadAllText($pointer)).Trim())
    if([IO.Path]::GetDirectoryName($inventoryPath) -ine $toolDir -or [IO.Path]::GetFileName($inventoryPath) -notmatch '^process-model-inventory-[a-f0-9]{32}\.json$'){throw 'Invalid inventory location.'}
    $inventory=Get-Content -Raw -Encoding UTF8 -LiteralPath $inventoryPath|ConvertFrom-Json
    $reference=Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $toolDir 'agent_reference.json')|ConvertFrom-Json
    $gpHash=@($reference.hashes.PSObject.Properties|Where-Object Name -like '*/gp.npz')
    if($inventory.target -ne '192.168.213.167'){
        Write-Host 'Jetson address changed. Checking the model location on 192.168.213.167 before starting.'
        & (Join-Path $toolDir 'Inspect-ProcessModel.ps1')
        $inventoryPath=[IO.Path]::GetFullPath(([IO.File]::ReadAllText($pointer)).Trim())
        if([IO.Path]::GetDirectoryName($inventoryPath) -ine $toolDir -or [IO.Path]::GetFileName($inventoryPath) -notmatch '^process-model-inventory-[a-f0-9]{32}\.json$'){throw 'Invalid refreshed inventory location.'}
        $inventory=Get-Content -Raw -Encoding UTF8 -LiteralPath $inventoryPath|ConvertFrom-Json
        if($inventory.target -ne '192.168.213.167'){throw 'New Jetson model location check did not complete.'}
    }
    if($inventory.schema_version -ne 1 -or $inventory.home -ne '/home/jetson' -or $reference.status -ne 'passed' -or $gpHash.Count -ne 1){throw 'Verified model reference/inventory missing.'}
    $models=@($inventory.model_roots|Where-Object {$_.has_agent -and $_.gp_sha256 -ceq $gpHash[0].Value}|Sort-Object @{Expression={$_.path -match 'bak|backup'}},path)
    $runtimes=@($inventory.python_runtimes|Where-Object {$_.numpy -and $_.websockets -and $_.tabpfn}|Sort-Object path)
    if($models.Count -eq 0 -or $runtimes.Count -eq 0){throw 'Matching model and high-precision Python not found. Run check-process-model.cmd again.'}
    $modelRoot=[string]$models[0].path;$python=[string]$runtimes[0].path
    foreach($value in @($modelRoot,$python)){
        if($value -notmatch '^/home/jetson/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+$' -or @($value.Split('/')|Where-Object {$_ -eq '..' -or $_ -eq '.'}).Count){throw 'Unsafe remote path in inventory.'}
    }
    $runName='UnityProcessBridge_'+[Guid]::NewGuid().ToString('N').Substring(0,12)
    $stagePath=Join-Path $toolDir $runName
    New-Item -ItemType Directory -Path $stagePath|Out-Null
    Copy-Item -LiteralPath (Join-Path $socketDir 'process_analysis.py'),(Join-Path $socketDir 'process_worker.py'),(Join-Path $toolDir 'agent_check.py'),(Join-Path $toolDir 'agent_reference.json') -Destination $stagePath
    $state.model_root=$modelRoot;$state.python=$python;$state.bridge=$runName;$state.remote_port=$RemotePort
    $workerConfig=Get-Content -LiteralPath (Join-Path $toolDir 'process-ai.local.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $workerConfig.url=('ws://127.0.0.1:{0}/fab' -f $RemotePort)
    $configJson=$workerConfig|ConvertTo-Json -Depth 10 -Compress
    $forward=('127.0.0.1:{0}:127.0.0.1:8765' -f $RemotePort)
    Write-Host ('Jetson private tunnel port: '+$RemotePort+' (existing connections are preserved)')
    Write-Host ('Existing model: '+$modelRoot)
    Write-Host ('Existing Python: '+$python)
    Write-Host 'Model files are not replaced. No packages will be installed.'
    if($PrepareOnly){Write-Host 'PROCESS_WORKER_PLAN_OK (no SSH connection made)';return}
    $options=@('-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=yes','-o',('UserKnownHostsFile='+(Join-Path $toolDir 'known_hosts')))
    $ssh=Join-Path $env:WINDIR 'System32/OpenSSH/ssh.exe';$scp=Join-Path $env:WINDIR 'System32/OpenSSH/scp.exe'
    $state.status='waiting_for_copy_login';$state|ConvertTo-Json|Set-Content -LiteralPath $statusFile -Encoding UTF8
    Write-Host 'STEP 1/2: Enter the Jetson password to copy the isolated request bridge.'
    & $scp @options -r $stagePath 'jetson@192.168.213.167:./'
    if($LASTEXITCODE -ne 0){throw 'Worker bridge upload failed.'}
    $state.status='waiting_for_worker_login';$state|ConvertTo-Json|Set-Content -LiteralPath $statusFile -Encoding UTF8
    Write-Host 'STEP 2/2: Enter the Jetson password again. Keep this window open.'
    Write-Host 'Wait for PROCESS_MODEL_VERIFIED and PROCESS_WORKER_CONNECTED.'
    $remoteCommand="cd './$runName' && '$python' -u process_worker.py --root '$modelRoot' --reference ./agent_reference.json --config-stdin"
    $previousPreference=$ErrorActionPreference
    try {
        $ErrorActionPreference='Continue'
        $configJson | & $ssh @options -o ExitOnForwardFailure=yes -R $forward 'jetson@192.168.213.167' $remoteCommand 2>&1 | ForEach-Object {
            if($_.ToString() -eq 'PROCESS_WORKER_CONNECTED'){$state.status='running';$state|ConvertTo-Json|Set-Content -LiteralPath $statusFile -Encoding UTF8}
            $_
        } | Tee-Object -FilePath (Join-Path $toolDir 'process-worker.log')
        $code=$LASTEXITCODE
    } finally {$ErrorActionPreference=$previousPreference}
    if($code -ne 0){throw 'Worker stopped with an error; see process-worker.log.'}
    $state.status='stopped'
} catch {$state.status='failed';$state.error=$_.Exception.Message;Write-Host $state.error -ForegroundColor Red}
finally {
    if(-not $PrepareOnly){$state|ConvertTo-Json|Set-Content -LiteralPath $statusFile -Encoding UTF8;Write-Host ('Worker: '+$state.status);Read-Host 'Press Enter to close'}
}
