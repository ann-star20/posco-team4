param([string]$Origin='ws://192.168.212.10:8000',[switch]$ReplayOnly)
$ErrorActionPreference='Stop'
$folder=Join-Path $PSScriptRoot 'IonIntegration'
[IO.Directory]::CreateDirectory($folder)|Out-Null
function Save($name,$value){$value|ConvertTo-Json -Depth 80|Set-Content -LiteralPath (Join-Path $folder $name) -Encoding utf8}
function Connect($path,[bool]$control=$false){
    $socket=[Net.WebSockets.ClientWebSocket]::new();$socket.Options.Proxy=$null
    if($control){$socket.Options.SetRequestHeader('X-Unity-Token',$env:UNITY_GATEWAY_TEST_TOKEN)}
    $cancel=[Threading.CancellationTokenSource]::new(10000)
    try{[void]$socket.ConnectAsync([Uri]($Origin+$path),$cancel.Token).GetAwaiter().GetResult();return $socket}
    catch{$socket.Dispose();throw}finally{$cancel.Dispose()}
}
function Receive($socket,[int]$seconds){
    $cancel=[Threading.CancellationTokenSource]::new($seconds*1000);$data=[IO.MemoryStream]::new();$buffer=[byte[]]::new(16384)
    try{
        do{$part=$socket.ReceiveAsync([ArraySegment[byte]]::new($buffer),$cancel.Token).GetAwaiter().GetResult()
            if($part.MessageType -ne [Net.WebSockets.WebSocketMessageType]::Text -or $data.Length+$part.Count -gt 4000000){throw 'Invalid event frame'}
            $data.Write($buffer,0,$part.Count)
        }while(!$part.EndOfMessage)
        return ([Text.Encoding]::UTF8.GetString($data.ToArray())|ConvertFrom-Json)
    }finally{$data.Dispose();$cancel.Dispose()}
}
function SendOnce($body){
    $socket=Connect '/api/v1/control' $true
    try{
        $bytes=[Text.Encoding]::UTF8.GetBytes(($body|ConvertTo-Json -Depth 40 -Compress))
        $cancel=[Threading.CancellationTokenSource]::new(10000)
        try{[void]$socket.SendAsync([ArraySegment[byte]]::new($bytes),[Net.WebSockets.WebSocketMessageType]::Text,$true,$cancel.Token).GetAwaiter().GetResult()}finally{$cancel.Dispose()}
        $ack=Receive $socket 15
        if($ack.type -ne 'request.accepted' -or $ack.request_id -ne $body.request_id -or $ack.status -ne 'queued'){throw 'Request not accepted; do not resubmit automatically'}
        return $ack
    }finally{$socket.Dispose()}
}
function WaitEvent($socket,$request,$job,[string]$type,[int]$seconds){
    $deadline=[DateTime]::UtcNow.AddSeconds($seconds)
    do{
        $left=[Math]::Max(1,[int]($deadline-[DateTime]::UtcNow).TotalSeconds)
        $event=Receive $socket $left
        $event|ConvertTo-Json -Depth 80 -Compress|Add-Content -LiteralPath (Join-Path $folder 'events.jsonl') -Encoding utf8
        if($event.run_id -ne $request.run_id){throw 'Wrong run received'}
        $id=$event.payload.request_id;if(!$id){$id=$event.payload.response.request_id}
        if($id -ne $request.request_id){continue}
        if($event.payload.job_id -ne $job){throw 'Job mismatch'}
        if($event.event_type -like '*.failed'){Save 'failure.event.json' $event;throw 'Gateway worker failed; see failure.event.json'}
        if($event.event_type -eq $type){return $event}
    }while([DateTime]::UtcNow -lt $deadline)
    throw 'Timed out; query existing IDs instead of creating a second job'
}
$active=Join-Path $folder 'active.json'
if($ReplayOnly){
    $request=Get-Content (Join-Path $folder 'diagnosis.request.json') -Raw|ConvertFrom-Json
    $ack=Get-Content (Join-Path $folder 'diagnosis.accepted.json') -Raw|ConvertFrom-Json
    $original=Get-Content (Join-Path $folder 'diagnosis.event.json') -Raw|ConvertFrom-Json
    $socket=Connect ('/api/v1/stream?run_id='+$request.run_id+'&after_sequence=0')
    try{$replay=WaitEvent $socket $request $ack.job_id 'diagnosis.completed' 30;Save 'diagnosis.replayed.json' $replay
        if($replay.event_id -ne $original.event_id){throw 'DB replay event changed'}
        'ION_DB_REPLAY_OK '+$replay.event_id
    }finally{$socket.Dispose()}
    exit
}
if(Test-Path -LiteralPath $active){throw 'An integration run already exists. Use -ReplayOnly; do not resubmit.'}
if([string]::IsNullOrWhiteSpace($env:UNITY_GATEWAY_TEST_TOKEN)){throw 'Set UNITY_GATEWAY_TEST_TOKEN in this process; token is never saved'}
$request=Get-Content (Join-Path $PSScriptRoot '../../Temp/IonGateway/surrogate.request.json') -Raw|ConvertFrom-Json
$request.request_id=[Guid]::NewGuid().ToString();$request.run_id=[Guid]::NewGuid().ToString()
$request.lot_id='LOT-UNITY-ION-INTEGRATION-TEST';$request.unit_id='SIM-IMP01-WAFER13'
$request.input_payload.process_parameters.body_dose=7.7e12
$request.input_payload.provenance.completed_dose_cm2=7.7e12
$request.input_payload.provenance.inspection_id=[Guid]::NewGuid().ToString('N')
$request.input_payload.provenance.condition_source='integration test of TCAD reference 7.7e12 / 1.7e16 / 0.06 um; simulated input, not a Unity runtime inspection or hardware measurement'
Save 'active.json' @{run_id=$request.run_id;prediction_request_id=$request.request_id;origin=$Origin;simulation_only=$true}
Save 'surrogate.request.json' $request
$stream=Connect ('/api/v1/stream?run_id='+$request.run_id+'&after_sequence=0')
try{
    $ack=SendOnce $request;Save 'surrogate.accepted.json' $ack
    'ION_PREDICTION_ACCEPTED '+$request.request_id
    $prediction=WaitEvent $stream $request $ack.job_id 'surrogate.completed' 90;Save 'surrogate.event.json' $prediction
    $response=$prediction.payload.response;$r=$response.result_payload;$units=$response.metadata.units
    if($response.status -ne 'succeeded' -or $response.result_origin -ne 'prod' -or $units.gm -ne 'uS/um' -or $units.id_on -ne 'uA/um' -or $units.vth -ne 'V' -or $units.bv -ne 'V'){throw 'Model origin/units invalid; no diagnosis submitted'}
    foreach($key in 'vth','gm','id_on','bv'){if(!$r.PSObject.Properties[$key] -or ![double]::IsFinite([double]$r.$key) -or $r.$key -le 0){throw 'Prediction missing or invalid'}}
    $diagnosis=@{type='diagnosis.requested';schema_version=1;request_id=[Guid]::NewGuid().ToString();run_id=$request.run_id;lot_id=$request.lot_id;unit_id=$request.unit_id;stage_id='ion_diagnosis';stage_attempt=1;model_contract_version='fab-ml-v1';
        input_payload=@{measurements=@{vth=$r.vth;gm=$r.gm;id_on=$r.id_on;bv=$r.bv};n_wafers=1;refine=$false;
            provenance=@{data_source='simulation';equipment_id='IMP-01';inspection_id=$request.input_payload.provenance.inspection_id;parent_request_id=$request.request_id;electrical_source='surrogate_prediction_not_measurement'}}}
    Save 'diagnosis.request.json' $diagnosis
    $diagnosisAck=SendOnce $diagnosis;Save 'diagnosis.accepted.json' $diagnosisAck
    'ION_DIAGNOSIS_ACCEPTED '+$diagnosis.request_id
    $result=WaitEvent $stream $diagnosis $diagnosisAck.job_id 'diagnosis.completed' 120;Save 'diagnosis.event.json' $result
    'ION_DIAGNOSIS_RECEIVED '+$result.event_id
    Save 'summary.json' @{run_id=$request.run_id;prediction_request_id=$request.request_id;diagnosis_request_id=$diagnosis.request_id;
        prediction_event_id=$prediction.event_id;diagnosis_event_id=$result.event_id;response_status=$result.payload.response.status;
        decision=$result.payload.response.result_payload.decision;compensation=$result.payload.response.result_payload.compensation;simulation_only=$true}
}finally{$stream.Dispose();Remove-Item Env:UNITY_GATEWAY_TEST_TOKEN -ErrorAction SilentlyContinue}
