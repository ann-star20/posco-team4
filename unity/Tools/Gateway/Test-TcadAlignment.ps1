param([Parameter(Mandatory=$true)][string]$Token,[string]$HostAddress='192.168.212.10:8000',[string[]]$Samples=@('B001','B038','B081'))
$ErrorActionPreference='Stop'
function Read-Text($Socket,$Cancel) {
    $buffer=[byte[]]::new(65536);$message=[IO.MemoryStream]::new()
    try {
        do {
            $part=$Socket.ReceiveAsync([ArraySegment[byte]]::new($buffer),$Cancel).GetAwaiter().GetResult()
            if($part.MessageType -ne [Net.WebSockets.WebSocketMessageType]::Text){throw 'Expected Gateway JSON text.'}
            if($message.Length+$part.Count -gt 4000000){throw 'Gateway message too large.'}
            $message.Write($buffer,0,$part.Count)
        } while(-not $part.EndOfMessage)
        return [Text.Encoding]::UTF8.GetString($message.ToArray())
    } finally {$message.Dispose()}
}
$folder=Join-Path $PSScriptRoot 'AlignmentChecks';New-Item -ItemType Directory -Force $folder | Out-Null
$rows=Import-Csv (Join-Path $PSScriptRoot '../JetsonTestData/jetson_테스트입력.csv')
foreach($sample in $Samples) {
    $row=$rows | Where-Object ID -eq $sample
    $numberCulture=[Globalization.CultureInfo]::InvariantCulture
    $dose=[double]::Parse($row.도즈,$numberCulture);$epi=[double]::Parse($row.에피,$numberCulture);$tox=[double]::Parse($row.산화막,$numberCulture)
    $request=[ordered]@{type='surrogate.requested';schema_version=1;request_id=[Guid]::NewGuid().ToString();run_id=[Guid]::NewGuid().ToString();lot_id='LOT-ML-ALIGNMENT-TEST';unit_id=('SIM-ALIGN-'+$sample);stage_id='electrical';stage_attempt=1;model_contract_version='fab-ml-v1';input_payload=@{process_parameters=@{body_dose=7.7e12*$dose;epi_doping=1.7e16*$epi;oxide_thickness=.06*$tox};requested_outputs=@('vth','gm','id_on','bv');provenance=@{data_source='simulation';sample_id=$sample;verification_only=$true;reference_thickness_nm=60;dose_ratio=$dose;epi_ratio=$epi;oxide_ratio=$tox}}}
    $cancel=[Threading.CancellationTokenSource]::new(180000)
    $control=[Net.WebSockets.ClientWebSocket]::new();$stream=[Net.WebSockets.ClientWebSocket]::new()
    try {
        $control.Options.Proxy=$null;$stream.Options.Proxy=$null
        $stream.ConnectAsync([Uri]("ws://$HostAddress/api/v1/stream?run_id="+$request.run_id+'&after_sequence=0'),$cancel.Token).GetAwaiter().GetResult() | Out-Null
        $control.Options.SetRequestHeader('X-Unity-Token',$Token)
        $control.ConnectAsync([Uri]("ws://$HostAddress/api/v1/control"),$cancel.Token).GetAwaiter().GetResult() | Out-Null
        $bytes=[Text.Encoding]::UTF8.GetBytes(($request | ConvertTo-Json -Depth 12 -Compress))
        $control.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,$cancel.Token).GetAwaiter().GetResult() | Out-Null
        $ack=(Read-Text $control $cancel.Token) | ConvertFrom-Json
        if($ack.type -ne 'request.accepted' -or $ack.request_id -ne $request.request_id){throw 'Gateway did not accept this request.'}
        do {$event=(Read-Text $stream $cancel.Token) | ConvertFrom-Json} while($event.event_type -ne 'surrogate.completed' -or $event.payload.request_id -ne $request.request_id)
        if($event.payload.job_id -ne $ack.job_id){throw 'Job ID mismatch.'}
        $response=$event.payload.response
        @{request=$request;accepted=$ack;event=$event} | ConvertTo-Json -Depth 40 | Set-Content -Encoding utf8 (Join-Path $folder ($sample+'-'+$request.request_id+'.json'))
        [pscustomobject]@{sample=$sample;status=$response.status;origin=$response.result_origin;vth=$response.result_payload.vth;gm=$response.result_payload.gm;id_on=$response.result_payload.id_on;bv=$response.result_payload.bv;error=$response.error_code;run_id=$request.run_id} | ConvertTo-Json -Compress
        if($response.status -ne 'succeeded' -or $response.result_origin -ne 'prod'){throw ('Real model did not return a result for '+$sample)}
    } finally {$control.Dispose();$stream.Dispose();$cancel.Dispose()}
}
