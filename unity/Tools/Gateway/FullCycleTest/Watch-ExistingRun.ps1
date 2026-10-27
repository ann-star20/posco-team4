param(
    [string]$Gateway='http://192.168.212.10:8000',
    [string]$Run='91b3bd1b-0951-465b-9b20-76f9bf8428fa',
    [string]$DiagnosisRequest='b3a22781-c8e9-48cb-b4b4-b4daa2dbdf30',
    [int]$Seconds=2400
)
$ErrorActionPreference='Stop'
if(-not [guid]::TryParse($Run,[ref]([guid]::Empty))){throw 'RUN UUID required'}
$folder=Join-Path $PSScriptRoot ('LiveRuns/'+$Run)
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$cursor=0L;$seen=@{};$deadline=(Get-Date).AddSeconds($Seconds)
$result=[ordered]@{run_id=$Run;diagnosis_request_id=$DiagnosisRequest;source='Existing Unity inspection; read-only observation; no new request';prediction_received=$false;diagnosis_received=$false;route=$null;tcad_events=0;tcad_batch_received=$false;last_sequence=0;state='watching';checked_at_utc=$null}
while((Get-Date) -lt $deadline){
    try{
        $reply=Invoke-RestMethod -Uri ($Gateway+'/api/v1/events?run_id='+$Run+'&after_sequence='+$cursor+'&limit=200') -TimeoutSec 10
        $reply | ConvertTo-Json -Depth 100 | Set-Content (Join-Path $folder 'latest-db-replay.json') -Encoding UTF8
        foreach($event in $reply.events){
            if($seen.ContainsKey([string]$event.event_id)){continue}
            if([string]$event.run_id -ne $Run){throw 'Wrong RUN returned'}
            $seen[[string]$event.event_id]=$true
            $event | ConvertTo-Json -Depth 100 -Compress | Add-Content (Join-Path $folder 'events.jsonl') -Encoding UTF8
            if([long]$event.sequence -gt $cursor){$cursor=[long]$event.sequence}
            $kind=[string]$event.event_type
            Write-Output ('EVENT sequence='+$event.sequence+' type='+$kind+' request='+$event.payload.request_id)
            if($kind -eq 'surrogate.completed'){$result.prediction_received=$true}
            if($event.payload.request_id -ne $DiagnosisRequest){continue}
            if($kind -eq 'diagnosis.completed'){
                $result.diagnosis_received=$true;$result.route=$event.payload.response.result_payload.compensation.route
                $event | ConvertTo-Json -Depth 100 | Set-Content (Join-Path $folder 'diagnosis-event.json') -Encoding UTF8
                Write-Output ('DIAGNOSIS status='+$event.payload.response.status+' route='+$result.route)
                if($event.payload.response.status -ne 'succeeded'){$result.state='diagnosis_failed'}
                elseif($result.route -ne 'tcad_verify'){$result.state='non_tcad_route'}
            }
            if($kind.StartsWith('tcad.verification.')){$result.tcad_events++;$event | ConvertTo-Json -Depth 100 | Set-Content (Join-Path $folder ($event.sequence+'-tcad-event.json')) -Encoding UTF8}
            if($kind -eq 'tcad.verification.batch_completed'){$result.tcad_batch_received=$true;$result.state='tcad_batch_received'}
        }
        $result.last_sequence=$cursor;$result.checked_at_utc=(Get-Date).ToUniversalTime().ToString('o')
        $result | ConvertTo-Json -Depth 15 | Set-Content (Join-Path $folder 'summary.json') -Encoding UTF8
        if($result.state -ne 'watching'){break}
    }catch{
        Write-Output ('OBSERVATION_ERROR '+$_.Exception.Message)
    }
    Start-Sleep -Seconds 15
}
if($result.state -eq 'watching'){$result.state='observation_window_ended_server_not_cancelled'}
$result.checked_at_utc=(Get-Date).ToUniversalTime().ToString('o')
$result | ConvertTo-Json -Depth 15 | Set-Content (Join-Path $folder 'summary.json') -Encoding UTF8
$result | ConvertTo-Json -Depth 15
