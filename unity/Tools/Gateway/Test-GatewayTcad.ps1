param([Parameter(Mandatory=$true)][string]$Token,[string]$HostAddress='192.168.212.10:8000')
$ErrorActionPreference='Stop'
$path=Join-Path $PSScriptRoot 'tcad-candidate-check.request.json'
$wire=[IO.File]::ReadAllText($path)
$request=$wire|ConvertFrom-Json
if($request.type -ne 'surrogate.requested' -or $request.stage_id -ne 'tcad_candidate_prediction' -or -not $request.input_payload.provenance.tcad){throw 'Expected the prepared candidate prediction request.'}
if($wire -match 'dose_ratio|epi_ratio|oxide_ratio|csv_sha256'){throw 'Evaluation truth is not permitted in this candidate request.'}
function Read-Text($Socket,$Cancel){
    $buffer=[byte[]]::new(65536);$message=[IO.MemoryStream]::new()
    try{
        do{
            $part=$Socket.ReceiveAsync([ArraySegment[byte]]::new($buffer),$Cancel).GetAwaiter().GetResult()
            if($part.MessageType -ne [Net.WebSockets.WebSocketMessageType]::Text -or $message.Length+$part.Count -gt 4000000){throw 'Invalid Gateway text response.'}
            $message.Write($buffer,0,$part.Count)
        }while(-not $part.EndOfMessage)
        [Text.Encoding]::UTF8.GetString($message.ToArray())
    }finally{$message.Dispose()}
}
$cancel=[Threading.CancellationTokenSource]::new(120000)
$stream=[Net.WebSockets.ClientWebSocket]::new();$control=[Net.WebSockets.ClientWebSocket]::new()
try{
    $stream.Options.Proxy=$null;$control.Options.Proxy=$null
    $stream.ConnectAsync([Uri]("ws://$HostAddress/api/v1/stream?run_id="+$request.run_id+'&after_sequence=0'),$cancel.Token).GetAwaiter().GetResult()|Out-Null
    $control.Options.SetRequestHeader('X-Unity-Token',$Token)
    $control.ConnectAsync([Uri]("ws://$HostAddress/api/v1/control"),$cancel.Token).GetAwaiter().GetResult()|Out-Null
    $bytes=[Text.Encoding]::UTF8.GetBytes($wire)
    $control.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,$cancel.Token).GetAwaiter().GetResult()|Out-Null
    $ack=(Read-Text $control $cancel.Token)|ConvertFrom-Json
    if($ack.type -ne 'request.accepted' -or $ack.request_id -ne $request.request_id){throw 'Candidate not accepted.'}
    do{$event=(Read-Text $stream $cancel.Token)|ConvertFrom-Json}while($event.payload.request_id -ne $request.request_id -or $event.event_type -notin @('surrogate.completed','surrogate.failed'))
    if($event.payload.job_id -ne $ack.job_id){throw 'Candidate job mismatch.'}
    $response=$event.payload.response
    $folder=Join-Path $PSScriptRoot 'TcadChecks';New-Item -ItemType Directory -Force -Path $folder|Out-Null
    $job=Invoke-RestMethod -Uri ("http://$HostAddress/api/v1/jobs/"+$ack.job_id) -Headers @{'X-Unity-Token'=$Token} -TimeoutSec 10
    $replay=Invoke-RestMethod -Uri ("http://$HostAddress/api/v1/events?run_id="+$request.run_id+'&after_sequence=0&limit=200') -TimeoutSec 10
    $dbEvent=@($replay.events|Where-Object event_id -eq $event.event_id)
    $proof=@{request=$request;accepted=$ack;event=$event;db_job=$job;replayed_event_count=$dbEvent.Count}
    $proof|ConvertTo-Json -Depth 70|Set-Content -LiteralPath (Join-Path $folder ($request.request_id+'.json')) -Encoding UTF8
    if($response.status -ne 'succeeded' -or $response.result_origin -ne 'prod' -or $dbEvent.Count -ne 1){throw 'Candidate prediction or DB replay failed; inspect saved evidence.'}
    if($job.status -ne 'completed' -or $job.result_event_id -ne $event.event_id -or $dbEvent[0].payload.input_payload.provenance.tcad.tcad_setup.deck -ne '최종_trench_template.in'){throw 'TCAD setup or result receipt missing from persisted DB event.'}
    [pscustomobject]@{status='CANDIDATE_DB_VERIFIED';request_id=$request.request_id;run_id=$request.run_id;job_id=$ack.job_id;event_id=$event.event_id;sequence=$event.sequence;predicted_outputs=$response.result_payload}|ConvertTo-Json -Depth 8
}finally{$stream.Dispose();$control.Dispose();$cancel.Dispose()}
