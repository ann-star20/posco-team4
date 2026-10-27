using System;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public partial class GatewayInspectionBridge
{
    public Job FullCycleJob(string inspection)=>jobs.Find(j=>j.cycle!=null&&j.inspectionId==inspection);
    public bool OwnsInspection(string inspection)=>jobs.Exists(j=>j.inspectionId==inspection&&(j.cycle!=null||j.kind=="ion_full_cycle"));
    static void StartFullCycle(Job job,bool equipmentOk,bool originalOk,bool originalElectricalKnown=true)
    {
        job.cycle=new GatewayFullCycleProtocol.State(job.request.run_id,job.request.request_id,job.request.lot_id,job.request.unit_id,equipmentOk,originalOk,originalElectricalKnown);
        job.cycleStarted=DateTime.UtcNow;job.cycleDeadline=job.cycleStarted.AddSeconds(180);
        job.kind="gateway_full_cycle";
    }
    void SubmitIonFullCycle(Job job,IonImplantCycle source)
    {
        var request=IonGatewayProtocol.Build(job.ion);request.request_id=job.request.request_id;request.run_id=job.request.run_id;job.request=request;
        string dose=IonDoseAssessment.Evaluate(source.dose,job.ion.lower_cm2,job.ion.upper_cm2,true,false);
        if(dose!="OK"&&dose!="FAIL")throw new ArgumentException("주입량 판정/허용 범위 확인 필요");
        var m=job.diagnosisRequest?.input_payload?.measurements;
        bool originalOk=m==null||ElectricalSpec.Evaluate((float)m.vth,(float)m.bv)==ElectricalSpec.Verdict.OK;
        // Reuse the dedicated inspection-record wire DTO; it has no TCAD candidate fields.
        if(m!=null)
        {
            bool ok=dose=="OK"&&originalOk;
            job.normalRequest=new IonGatewayProtocol.NormalRequest{request_id=request.request_id,run_id=request.run_id,lot_id=request.lot_id,unit_id=request.unit_id,
                input_payload=new IonGatewayProtocol.NormalInput{process_parameters=request.input_payload.process_parameters,
                    provenance=new IonGatewayProtocol.NormalProvenance{inspection_id=job.inspectionId,sample_id=job.ion.csv_sample_id,csv_sha256=job.ion.csv_sha256,
                        completed_dose_cm2=job.ion.dose_cm2,condition_source=job.ion.condition_source,
                        inspection_result=new IonGatewayProtocol.InspectionResult{purpose="ion_inspection_record",completed_at=job.ion.completed_at,
                            verdict=ok?"OK":"NG",dose_verdict=dose=="OK"?"OK":"NG",electrical_verdict=originalOk?"OK":"NG",
                            dose_cm2=job.ion.dose_cm2,target_cm2=job.ion.target_cm2,lower_cm2=job.ion.lower_cm2,upper_cm2=job.ion.upper_cm2,
                            measurements=m,diagnosis_requested=!ok}}}};
            request.stage_id=job.normalRequest.stage_id;
        }
        job.diagnosisRequest=null;StartFullCycle(job,dose=="OK",originalOk);SaveRequest(job);job.ready=true;
        Notice=job.state="검사값 Gateway 전송 대기 · 예측 → 진단 → 조건부 TCAD";
    }
    void PumpFullCycles()
    {
        foreach(var job in jobs)
        {
            if(job.cycle==null||job.finished||!job.ready)continue;
            try
            {
                if(!job.cycleStream)
                {
                    job.cycleStream=gameObject.AddComponent<GatewayStreamClient>();job.cycleStream.endpoint=job.streamAddress;job.cycleStream.runId=job.request.run_id;
                    job.cycleStream.EventReceived+=e=>job.cycleEvents.Enqueue(e);
                    job.cycleStream.ConnectStream();job.state="결과 수신 연결 중 · Gateway 전체 사이클";
                }
                job.cycleStream.Pump();
                if(!job.predictionSent&&job.cycleStream.Connected)
                {
                    if(job.cycleBlocked){CloseFullCycle(job,"새 전송 꺼짐 · 검사 요청 미전송");continue;}
                    job.predictionSent=true;job.state="1/3 검사 공정값 전송 · 서로게이트 예측 대기";
                    _=SendFullCycle(job,RequestJson(job),job.cycle.PredictionId,lifetime.Token);
                }
                while(job.cycleEvents.Count>0)
                {
                    var e=job.cycleEvents.Dequeue();
                    if(e.sequence<=job.cycle.Sequence)continue;
                    if(e.event_type=="tcad.verification.review_required"||e.event_type=="tcad.verification.decided")
                    {
                        GatewayTcadApprovalView.For(this).Observe(job,e.rawJson);
                        job.cycle.ObserveReviewEvent(e.rawJson);
                    }
                    else if(!job.cycle.Accept(e.rawJson))continue;
                    job.rawEvent=e.rawJson;job.eventId=e.event_id;job.sequence=e.sequence;job.state=job.cycle.Notice;
                    job.cycleWarning=null;
                    SaveFullCycleEvent(job,e.rawJson);PublishFullCycle(job);
                    if(e.event_type=="surrogate.completed"||e.event_type=="diagnosis.completed")
                    {
                        var view=GetComponent<ProcessAnalysisView>();
                        if(view){view.OpenFullCycle(job);if(e.event_type=="diagnosis.completed")view.SetAnalysisTab(1);}
                    }
                }
                if(!job.cycle.KeepSubscription){CloseFullCycle(job,job.cycle.Notice);continue;}
                if(job.cycle.PendingDiagnosis&&!job.diagnosisSent)
                {
                    if(job.cycleBlocked){CloseFullCycle(job,"예측 DB 결과 수신 · 새 전송 꺼짐으로 진단 미전송");continue;}
                    string body=job.cycle.DiagnosisJson();job.diagnosisSent=true;job.cycleDeadline=DateTime.UtcNow.AddSeconds(180);
                    File.WriteAllText(Path.Combine(Application.dataPath,"../Tools/Gateway/Requests",job.cycle.DiagnosisId+".json"),body);
                    job.state="2/3 예측 전기특성으로 Gateway 진단 요청 · 원인·보정안 대기";
                    _=SendFullCycle(job,body,job.cycle.DiagnosisId,lifetime.Token);
                }
                if(job.cycle.WaitingTcad&&job.tcadStarted==default)
                {job.tcadStarted=DateTime.UtcNow;job.cycleDeadline=job.tcadStarted.AddMinutes(90);}
                if(DateTime.UtcNow>job.cycleDeadline)
                {
                    // Keep the subscription alive: a slow accepted task can still deliver its committed result.
                    job.cycleWarning="응답 지연 · 서버 작업 ID 확인 필요 / 재접속 수신 계속 · 자동 재전송 없음";
                }
                PublishFullCycle(job);
            }
            catch(Exception error) when(error is FormatException||error is ArgumentException||error is IOException||error is UnauthorizedAccessException)
            {CloseFullCycle(job,"전체 사이클 확인 필요 · "+error.Message);}
        }
    }
    async Task SendFullCycle(Job job,string body,string requestId,CancellationToken cancel)
    {
        bool sent=false;
        try
        {
            using(var socket=new ClientWebSocket())
            using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancel))
            {
                timeout.CancelAfter(TimeSpan.FromSeconds(15));socket.Options.Proxy=null;
                socket.Options.SetRequestHeader("X-Unity-Token",job.credential??Token);
                await socket.ConnectAsync(ControlUri(job.streamAddress,job.cycle.Run),timeout.Token);
                var bytes=Encoding.UTF8.GetBytes(body);sent=true;
                await socket.SendAsync(new ArraySegment<byte>(bytes),WebSocketMessageType.Text,true,timeout.Token);
                using(var reply=new MemoryStream())
                {
                    var buffer=new byte[8192];WebSocketReceiveResult part;
                    do{part=await socket.ReceiveAsync(new ArraySegment<byte>(buffer),timeout.Token);if(part.MessageType!=WebSocketMessageType.Text||reply.Length+part.Count>65536)throw new FormatException("요청 접수 응답 형식 오류");reply.Write(buffer,0,part.Count);}while(!part.EndOfMessage);
                    string rawAck=Encoding.UTF8.GetString(reply.ToArray());
                    File.WriteAllText(Path.Combine(Application.dataPath,"../Tools/Gateway/Requests",requestId+".ack.json"),rawAck);
                    job.cycle.AcceptAck(rawAck,requestId);
                    job.jobId=requestId==job.cycle.PredictionId?job.cycle.PredictionJob:job.cycle.DiagnosisJob;
                    // ACK is never completion; do not overwrite an event that arrived first.
                }
            }
        }
        catch(Exception error)
        {
            if(cancel.IsCancellationRequested||job.finished)return;
            if(error is FormatException)CloseFullCycle(job,"요청 접수 거절/식별자 확인 필요 · "+error.Message);
            else if(!sent)CloseFullCycle(job,"요청 연결 실패 · 주소·토큰 확인 / 자동 재전송 없음");
            else job.cycleWarning="접수 응답 미확인 · 완료 이벤트 수신 계속 / 동일 요청 자동 재전송 없음";
        }
        finally{job.credential=null;}
    }
    static void SaveFullCycleEvent(Job job,string raw)
    {
        string folder=Path.Combine(Application.dataPath,"../Tools/Gateway/Requests");Directory.CreateDirectory(folder);
        File.AppendAllText(Path.Combine(folder,job.cycle.PredictionId+".events.jsonl"),raw+Environment.NewLine);
    }
    static void PublishFullCycle(Job job)
    {
        var record=LotProcessAnalysis.Instance?LotProcessAnalysis.Instance.ForInspection(job.inspectionId):null;
        if(record==null||record.inspectionId!=job.inspectionId)return;
        record.gatewayManaged=true;record.detail=job.state;record.tcadGatewayState=job.state;
        if(job.cycle.Done)record.status=job.cycle.Route==null?LotProcessAnalysis.Status.Pass:LotProcessAnalysis.Status.Complete;
        else if(job.cycle.Diagnosis!=null)record.status=LotProcessAnalysis.Status.Complete;
        else if(job.predictionSent)record.status=LotProcessAnalysis.Status.Running;
        RefreshRecord(job);
    }
    void CloseFullCycle(Job job,string message)
    {
        job.state=message;job.finished=true;job.credential=null;Notice=message;
        if(job.cycleStream){job.cycleStream.DisconnectStream();if(Application.isPlaying)Destroy(job.cycleStream);else DestroyImmediate(job.cycleStream);}job.cycleStream=null;
        PublishFullCycle(job);
        if(!job.cycle.Done)
        {
            var record=LotProcessAnalysis.Instance?LotProcessAnalysis.Instance.ForInspection(job.inspectionId):null;
            if(record!=null&&record.inspectionId==job.inspectionId)record.status=LotProcessAnalysis.Status.Failed;
        }
        var view=GetComponent<ProcessAnalysisView>();if(view)view.OpenFullCycle(job);
    }
    void StopFullCycleStreams()
    {
        foreach(var job in jobs)if(job.cycleStream){job.cycleStream.DisconnectStream();if(Application.isPlaying)Destroy(job.cycleStream);else DestroyImmediate(job.cycleStream);job.cycleStream=null;}
    }
}
