param([string]$HostAddress='192.168.212.10:8000')
$ErrorActionPreference='Stop'
$active=Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'LiveRuns/active.json') | ConvertFrom-Json
$response=Invoke-RestMethod -Uri ("http://$HostAddress/api/v1/events?run_id="+$active.run_id+'&after_sequence=0&limit=200') -TimeoutSec 10
$response | ConvertTo-Json -Depth 90 | Set-Content -Encoding UTF8 (Join-Path $active.folder 'db-observation.json')
$matches=@($response.events | Where-Object {$_.payload.request_id -eq $active.request_id})
if($matches.Count -eq 0){
    [pscustomobject]@{status='NO_RESULT_EVENT_YET';run_id=$active.run_id;request_id=$active.request_id}
}else{
    $matches | Select-Object sequence,event_id,event_type,@{n='status';e={$_.payload.response.status}},@{n='route';e={$_.payload.response.result_payload.compensation.route}}
}
