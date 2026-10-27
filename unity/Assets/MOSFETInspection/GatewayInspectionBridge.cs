using System;
using System.Collections.Generic;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

// Completed equipment inspection + matching LOT conditions -> Gateway -> matching DB event.
public partial class GatewayInspectionBridge : MonoBehaviour
{
    public static GatewayInspectionBridge Instance {get;private set;}
    [NonSerialized] public string StreamAddress="ws://192.168.212.10:8000/api/v1/stream";
    [NonSerialized] public string Token="";
    public bool Armed {get;private set;}
    public string Notice {get;private set;}="연동을 켜면 산화막·이온주입 완료값이 자동 전송됩니다.";
    [Serializable] public class Job
    {
        public GatewayInspectionProtocol.Request request;
        public GatewayLotConditions.Condition condition;
        public GatewayInspectionSnapshot inspection;
        public string inspectionId,state,jobId,eventId,origin,model,streamAddress;
        public string errorCode,errorMessage;
        public string kind,rawEvent;
        public IonGatewayProtocol.Snapshot ion;
        public IonGatewayProtocol.DiagnosisRequest diagnosisRequest;
        public IonGatewayProtocol.NormalRequest normalRequest;
        public GatewayInspectionSnapshot.RecordRequest filmRecordRequest;
        public IonGatewayProtocol.DiagnosisResponse diagnosis;
        public ProcessAnalysisView.Payload directDiagnosis;
        public GatewayStreamClient.OutputUnits units;
        public GatewayTcadProtocol.ForwardRequest tcadForward;
        public double oxideInputRatio;
        public long sequence;
        public GatewayStreamClient.Result result;
        [NonSerialized] public GatewayFullCycleProtocol.State cycle;
        [NonSerialized] internal GatewayStreamClient cycleStream;
        [NonSerialized] internal bool predictionSent,diagnosisSent,cycleBlocked;
        [NonSerialized] internal DateTime cycleStarted,cycleDeadline,tcadStarted;
        [NonSerialized] internal string cycleWarning;
        [NonSerialized] internal readonly Queue<GatewayStreamClient.DbEvent> cycleEvents=new Queue<GatewayStreamClient.DbEvent>();
        public bool hasId,hasIdOn;
        [NonSerialized] internal string credential;
        [NonSerialized] internal bool ready,finished;
    }
    readonly List<Job> jobs=new List<Job>();
    public IReadOnlyList<Job> Jobs=>jobs;
    public Job Last=>jobs.Count==0?null:jobs[jobs.Count-1];
    Job active;
    GatewayStreamClient stream;
    CancellationTokenSource lifetime;
    DateTime deadline;
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]static void ResetStatic(){Instance=null;}
    void OnEnable(){EnsureSession();}
    public void EnsureSession()
    {
        if(Instance==this&&lifetime!=null&&!lifetime.IsCancellationRequested)return;
        lifetime?.Dispose();lifetime=new CancellationTokenSource();Instance=this;Armed=false;Token="";jobs.Clear();active=null;
    }
    public bool Arm()
    {
        try
        {
            GatewayStreamClient.StreamUri(StreamAddress,Guid.NewGuid().ToString(),0);
            if(string.IsNullOrWhiteSpace(Token)||Token.Length>4096||Token.Contains("\r")||Token.Contains("\n"))throw new ArgumentException("Gateway 요청 토큰을 입력하세요.");
            Armed=true;Notice="검사 연동 켜짐 · 다음 검사부터 전송 / TCAD 후보는 담당자 승인 후 설정 적용";return true;
        }
        catch(Exception e){Notice=e.Message;return false;}
    }
    public void Disarm()
    {
        Armed=false;
        foreach(var job in jobs)
        {
            if(job.cycle!=null){job.cycleBlocked=true;if(job.predictionSent)continue;}
            if(!job.ready&&!job.finished){job.finished=true;job.credential=null;job.state="연동 해제 · 전송하지 않음";}
        }
        Notice="새 검사 전송 꺼짐 · 이미 보낸 요청의 결과 수신은 계속합니다.";
    }
    public void Capture(EllipsometerCycle source)
    {
        if(!Armed||jobs.Exists(j=>j.inspectionId==source.InspectionId))return;
        var record=LotProcessAnalysis.Instance?LotProcessAnalysis.Instance.Latest(source.lotId):null;
        if(record!=null)record.gatewayManaged=true;
        try
        {
            foreach(var prior in jobs)if(prior.cycle==null&&prior.kind!="ion_surrogate"&&prior.kind!="ion_diagnosis"&&!prior.ready&&!prior.finished){prior.finished=true;prior.credential=null;prior.state="이전 검사 미완료 · 전송하지 않음";}
            if(jobs.FindAll(j=>!j.finished).Count>=8)throw new InvalidOperationException("Gateway 대기 검사 8건 초과 · 검사 전송 상태를 확인하세요.");
            string unit=source.waferId;
            if(string.IsNullOrWhiteSpace(unit))unit=source.InspectionCsv?.wafer_key;
            if(string.IsNullOrWhiteSpace(unit))unit="SIM-WAFER-"+source.InspectionId;
            var condition=GatewayLotConditions.ForLot(source.lotId);
            var request=new GatewayInspectionProtocol.Request{request_id=Guid.NewGuid().ToString(),run_id=Guid.NewGuid().ToString(),lot_id=source.lotId,unit_id=unit};
            var job=new Job{request=request,condition=condition,inspectionId=source.InspectionId,state="검사 진행 중 · 완료된 측정값 자동 전송 대기",streamAddress=StreamAddress,credential=Token};
            if(jobs.Count>=32){int i=jobs.FindIndex(j=>j.finished);if(i>=0)jobs.RemoveAt(i);}
            jobs.Add(job);Notice=job.state;
        }
        catch(Exception e){Notice="Gateway 전송 보류 · "+e.Message;if(record!=null)record.detail=Notice;}
    }
    public void Submit(EllipsometerCycle source)
    {
        var job=jobs.Find(j=>j.inspectionId==source.InspectionId);
        if(job==null||job.ready||job.finished)return;
        try
        {
            var record=LotProcessAnalysis.Instance?LotProcessAnalysis.Instance.Latest(source.lotId):null;
            job.inspection=GatewayInspectionSnapshot.Capture(source,record);
            var built=GatewayInspectionProtocol.BuildAutomatic(job.inspection,job.condition);
            built.request_id=job.request.request_id;built.run_id=job.request.run_id;
            job.filmRecordRequest=GatewayInspectionSnapshot.BuildRecord(built,job.inspection);
            built.stage_id=job.filmRecordRequest.stage_id;job.request=built;job.kind="film_inspection_record";
            string originalVerdict=job.filmRecordRequest.input_payload.provenance.inspection_result.electrical_verdict;
            bool originalKnown=originalVerdict=="OK"||originalVerdict=="NG";
            if(!originalKnown&&!string.Equals(originalVerdict,"Pending",StringComparison.OrdinalIgnoreCase))throw new ArgumentException("원본 전기특성 판정 형식 확인 필요");
            StartFullCycle(job,job.inspection.verdict=="PASS",originalVerdict=="OK",originalKnown);
            string folder=Path.Combine(Application.dataPath,"../Tools/Gateway/Requests");Directory.CreateDirectory(folder);
            File.WriteAllText(Path.Combine(folder,job.request.request_id+".json"),RequestJson(job));
            job.ready=true;job.state="전송 대기";Notice=job.state;
            RefreshRecord(job);
            var view=GetComponent<ProcessAnalysisView>();if(view)view.OpenGatewayRequests();
        }
        catch(Exception e) when(e is IOException||e is UnauthorizedAccessException||e is ArgumentException)
        {job.finished=true;job.credential=null;Notice=job.state=e is ArgumentException?e.Message:"요청 기록 저장 실패 · 전송하지 않음";RefreshRecord(job);}
    }
    public Job QueueTcadCandidate(LotProcessAnalysis.Record record)
    {
        if(record==null)throw new ArgumentException("검사 기록이 없습니다.");
        if(FullCycleJob(record.inspectionId)!=null)throw new ArgumentException("Gateway 전체 사이클에서 진단 route에 따라 TCAD를 자동 접수합니다. 별도 후보 요청은 보내지 않습니다.");
        if(!LotProcessAnalysis.NeedsDiagnosis(record))throw new ArgumentException("정상 검사 또는 판정 대기 · 보정 후보 전송 대상 아님");
        var existing=jobs.Find(j=>j.kind=="tcad_candidate_prediction"&&j.inspectionId==record.inspectionId);
        if(existing!=null)return existing;
        if(!Armed)throw new ArgumentException("Gateway의 요청 토큰을 입력하고 자동 검사 연동을 시작하세요.");
        if(jobs.FindAll(j=>!j.finished).Count>=8)throw new ArgumentException("Gateway 대기 작업이 8건입니다. 완료 후 다시 보내세요.");
        var parent=jobs.Find(j=>j.kind!="tcad_candidate_prediction"&&j.inspectionId==record.inspectionId);
        var request=GatewayTcadProtocol.Build(record,parent);
        var job=new Job{kind="tcad_candidate_prediction",request=request,inspectionId=record.inspectionId,state="보정 후보 Gateway 전송 대기",streamAddress=StreamAddress,credential=Token};
        string folder=Path.Combine(Application.dataPath,"../Tools/Gateway/Requests");Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder,request.request_id+".json"),JsonUtility.ToJson(request,true));
        if(jobs.Count>=32){int index=jobs.FindIndex(j=>j.finished);if(index>=0)jobs.RemoveAt(index);}
        jobs.Add(job);job.ready=true;Notice=job.state;return job;
    }
    public Job TcadJob(string inspection)=>jobs.Find(j=>j.kind=="tcad_candidate_prediction"&&j.inspectionId==inspection);
    public static Uri ControlUri(string address,string run)
    {
        var b=new UriBuilder(GatewayStreamClient.StreamUri(address,run,0)){Path="/api/v1/control",Query=""};return b.Uri;
    }
    async Task Send(Job job,CancellationToken cancel)
    {
        bool sending=false;
        try
        {
            using(var socket=new ClientWebSocket())
            using(var timeout=CancellationTokenSource.CreateLinkedTokenSource(cancel))
            {
                timeout.CancelAfter(TimeSpan.FromSeconds(12));socket.Options.Proxy=null;
                socket.Options.SetRequestHeader("X-Unity-Token",job.credential);
                await socket.ConnectAsync(ControlUri(job.streamAddress,job.request.run_id),timeout.Token);
                byte[] body=Encoding.UTF8.GetBytes(RequestJson(job));sending=true;
                await socket.SendAsync(new ArraySegment<byte>(body),WebSocketMessageType.Text,true,timeout.Token);
                var buffer=new byte[4096];
                using(var reply=new MemoryStream())
                {
                    WebSocketReceiveResult part;
                    do
                    {
                        part=await socket.ReceiveAsync(new ArraySegment<byte>(buffer),timeout.Token);
                        if(part.MessageType!=WebSocketMessageType.Text||reply.Length+part.Count>65536)throw new FormatException();
                        reply.Write(buffer,0,part.Count);
                    }while(!part.EndOfMessage);
                    var ack=GatewayInspectionProtocol.ParseAccepted(Encoding.UTF8.GetString(reply.ToArray()),job.request);
                    if(!job.finished)
                    {
                        if(job.jobId!=null&&job.jobId!=ack.job_id)throw new FormatException();
                        job.jobId=ack.job_id;job.state=job.kind=="ion_inspection_record"?"정상 검사 결과 DB 요청 접수됨 · 완료 이벤트 확인 대기":"DB 요청 접수됨 · Jetson 분석 결과 대기 (미완료)";
                        RefreshRecord(job);
                    }
                }
                if(socket.State==WebSocketState.Open)await socket.CloseOutputAsync(WebSocketCloseStatus.NormalClosure,"Request queued",timeout.Token);
            }
        }
        catch(Exception)
        {
            if(!job.finished)
            {
                job.state=sending?"접수 여부 확인 필요 · 자동 재전송하지 않음 · 결과 수신은 계속":"요청 연결 실패 · 서버 주소·요청 토큰 확인";Notice=job.state;
                RefreshRecord(job);
                if(!sending&&active==job)Finish(job.state);
            }
        }
        finally{job.credential=null;}
    }
    void Update()
    {
        PumpFullCycles();
        if(active==null)
        {
            active=jobs.Find(j=>j.cycle==null&&j.ready&&!j.finished);
            if(active==null)return;
            stream=gameObject.AddComponent<GatewayStreamClient>();stream.endpoint=active.streamAddress;stream.runId=active.request.run_id;
            stream.ConnectStream();active.state="결과 수신 연결 중 · 아직 요청 전송 전";deadline=DateTime.UtcNow.AddSeconds(10);
            RefreshRecord(active);
        }
        if(active.state=="결과 수신 연결 중 · 아직 요청 전송 전"&&stream.Connected)
        {
            active.state="검사 데이터 전송 중";deadline=DateTime.UtcNow.AddSeconds(180);_=Send(active,lifetime.Token);
            if(active!=null)RefreshRecord(active);
        }
        if(active==null||!stream)return;
        foreach(var e in stream.Events)
        {
            if(active.kind=="ion_diagnosis"&&GatewayInspectionProtocol.Matches(active.request,e)&&(e.event_type=="diagnosis.completed"||e.event_type=="diagnosis.failed"))
            {
                string id=e.payload.job_id??e.payload.response?.job_id;
                if(!Guid.TryParse(id,out _)||active.jobId!=null&&active.jobId!=id)continue;
                active.jobId=id;active.eventId=e.event_id;active.sequence=e.sequence;active.rawEvent=e.rawJson;
                try{active.diagnosis=IonGatewayProtocol.ReadDiagnosis(active,e);Finish("원인 분석·보정 제안 DB 저장 확인 · TCAD 검증/승인 별도");}
                catch(ArgumentException error){Finish("진단 실패/결과 확인 필요 · "+error.Message);}
                return;
            }
            if(active.kind!="ion_diagnosis"&&GatewayInspectionProtocol.Matches(active.request,e)&&(e.event_type=="surrogate.completed"||e.event_type=="surrogate.failed"))
            {
                string jobId=e.payload.job_id??e.payload.response?.job_id;
                if(!Guid.TryParse(jobId,out _)||active.jobId!=null&&active.jobId!=jobId)continue;
                active.jobId=jobId;active.eventId=e.event_id;active.sequence=e.sequence;
                var response=e.payload.response;
                active.origin=response?.metadata?.representation=="synthetic_normalized_fixture"?"mock":response?.result_origin;active.model=response?.model_version;
                active.errorCode=GatewayInspectionProtocol.ErrorCode(response);active.errorMessage=GatewayInspectionProtocol.ErrorMessage(response);
                active.oxideInputRatio=response?.metadata?.input_ratios?.tox??0;active.units=response?.metadata?.units;active.rawEvent=e.rawJson;
                active.result=response?.status=="succeeded"?response.result_payload:null;active.hasId=e.hasId;active.hasIdOn=e.hasIdOn;
                Finish(response?.status=="succeeded"&&active.result!=null?
                    "결과 수신 완료 · "+(active.origin=="mock"?"MOCK 시험값 / 실제 예측 아님":"출처 "+(active.origin??"미확인")):GatewayInspectionProtocol.FailureTitle(response));
                return;
            }
        }
        if(DateTime.UtcNow>deadline)Finish("응답 대기 시간 초과 · 요청 ID로 서버 기록 확인 · 자동 재전송 없음");
    }
    void Finish(string state)
    {
        bool ionResult=active.ion!=null;
        if(active.kind=="tcad_candidate_prediction"&&active.result!=null)
        {
            try{active.tcadForward=GatewayTcadProtocol.Complete(active);state="보정 후보·예측값 DB 저장 확인 · Gateway 팀원 전달 대기 / TCAD 미실행";}
            catch(ArgumentException error){state="보정 후보 전달 보류 · "+error.Message;}
        }
        if(active.kind=="film_inspection_record"&&active.result!=null)
            state="산화막 검사값·판정 DB 저장 확인 · "+(active.filmRecordRequest.input_payload.provenance.inspection_result.verdict=="OK"?"진단·보정 불필요":"NG 진단·보정 후보는 별도 작업");
        if(active.kind=="ion_inspection_record"&&active.result!=null)
            state="정상 검사값·OK 판정 DB 저장 확인 · 진단·보정 후보 없음";
        if(active.kind=="ion_surrogate"&&active.result!=null)
        {
            try{QueueIonDiagnosis(active);state="전기특성 예측 DB 저장 확인 · 자동 진단 요청 대기";}
            catch(Exception error) when(error is ArgumentException||error is IOException||error is UnauthorizedAccessException){state="예측 수신 · 진단 전송 보류 · "+error.Message;}
        }
        active.finished=true;active.state=state;active.credential=null;Notice=state;
        RefreshRecord(active);
        try{File.WriteAllText(Path.Combine(Application.dataPath,"../Tools/Gateway/Requests",active.request.request_id+".result.json"),JsonUtility.ToJson(active,true));}
        catch(Exception error) when(error is IOException||error is UnauthorizedAccessException){Notice+=" · 로컬 결과 기록 실패";}
        if(stream){stream.DisconnectStream();Destroy(stream);}stream=null;active=null;
        var view=GetComponent<ProcessAnalysisView>();if(view&&!ionResult)view.OpenGatewayRequests();
    }
    static void RefreshRecord(Job job)
    {
        var record=LotProcessAnalysis.Instance?LotProcessAnalysis.Instance.ForInspection(job.inspectionId):null;
        if(record==null||record.inspectionId!=job.inspectionId)return;
        // Gateway status is shown in its own window; preserve diagnosis state on the LOT monitor.
        if(record.source&&record.source.InspectionId==record.inspectionId&&record.source.dashboard)record.source.dashboard.Refresh();
    }
    void OnDisable()
    {
        StopFullCycleStreams();
        Armed=false;lifetime?.Cancel();Token="";
        foreach(var j in jobs){j.credential=null;if(!j.finished){j.finished=true;j.state="연결 종료 · 요청 ID로 서버 기록 확인";}}
        if(stream){stream.DisconnectStream();Destroy(stream);}stream=null;active=null;
    }
    void OnDestroy(){lifetime?.Dispose();if(Instance==this)Instance=null;}
}
