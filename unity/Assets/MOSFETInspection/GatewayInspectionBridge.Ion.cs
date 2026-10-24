using System;
using System.IO;
using UnityEngine;

public partial class GatewayInspectionBridge
{
    public Job IonJob(string inspection)=>jobs.Find(j=>j.ion!=null&&j.inspectionId==inspection);
    public Job IonDiagnosis(string inspection)=>jobs.Find(j=>(j.kind=="ion_diagnosis"||j.kind=="tcad_candidate_prediction"&&j.ion!=null)&&j.inspectionId==inspection);
    public void Capture(IonImplantCycle source)
    {
        if(!Armed||IonJob(source.InspectionId)!=null)return;
        try
        {
            foreach(var prior in jobs)if((prior.kind=="ion_surrogate"||prior.kind=="ion_diagnosis")&&!prior.ready&&!prior.finished&&prior.ion?.unit_id==source.InspectionUnitId&&string.IsNullOrEmpty(prior.ion.completed_at))
            {prior.finished=true;prior.credential=null;prior.state="이전 주입 검사 중단 · 전송하지 않음";}
            if(jobs.FindAll(j=>!j.finished).Count>=8)throw new ArgumentException("Gateway 대기 작업이 8건입니다.");
            var condition=source.InspectionCondition??GatewayLotConditions.ForLot(source.incomingLotId);
            if(!GatewayInspectionProtocol.Positive(condition.oxide_reference_um))throw new ArgumentException("LOT 산화막 TCAD 기준이 없습니다.");
            var snapshot=new IonGatewayProtocol.Snapshot{inspection_id=source.InspectionId,lot_id=source.incomingLotId,unit_id=source.InspectionUnitId,
                target_cm2=source.targetDose,lower_cm2=source.dashboard?source.dashboard.doseLower:0,upper_cm2=source.dashboard?source.dashboard.doseUpper:0,
                epi_doping=condition.epi_doping,oxide_thickness_um=condition.oxide_reference_um,
                condition_source=condition.source+"; epi and oxide are registered TCAD simulation context, not equipment measurements"};
            var csv=source.InspectionCsv;
            if(csv?.row!=null)
            {
                snapshot.csv_sample_id=csv.row.id;snapshot.csv_sha256=csv.dataset_sha256;snapshot.electrical_source=csv.measurement_source;
                snapshot.epi_doping=condition.epi_doping*csv.row.epi_doping_ratio;
                snapshot.oxide_thickness_um=condition.oxide_reference_um*csv.row.oxide_ratio;
                snapshot.condition_source=condition.source+"; same frozen Jetson CSV row; dose is completed simulation value; epi and oxide are TCAD references times CSV ratios; not sensor measurements";
            }
            // Gateway full cycle starts from completed process values; no direct Jetson diagnosis is queued.
            var requestId=Guid.NewGuid().ToString();var runId=Guid.NewGuid().ToString();
            var diagnosis=csv?.row==null?null:IonGatewayProtocol.DiagnoseCsv(snapshot,csv,requestId,runId);
            var request=new GatewayInspectionProtocol.Request{request_id=requestId,run_id=runId,lot_id=snapshot.lot_id,unit_id=snapshot.unit_id};
            jobs.Add(new Job{kind="ion_full_cycle",ion=snapshot,inspectionId=source.InspectionId,request=request,diagnosisRequest=diagnosis,condition=condition,
                streamAddress=StreamAddress,credential=Token,state="이온주입 완료 대기 · 완료 공정값으로 Gateway 전체 사이클"});
            Notice="검사 완료 후 Gateway 예측 → 진단 → 조건부 TCAD 검증";
        }
        catch(ArgumentException error){Notice="이온주입 전송 보류 · "+error.Message;}
    }
    public void Submit(IonImplantCycle source)
    {
        var job=IonJob(source.InspectionId);if(job==null||job.ready||job.finished)return;
        try
        {
            if(!source.completed||source.failed||source.incomingLotId!=job.ion.lot_id||source.InspectionUnitId!=job.ion.unit_id)
                throw new ArgumentException("완료 상태·LOT·웨이퍼가 시작 시 검사와 다릅니다.");
            job.ion.dose_cm2=source.dose;job.ion.completed_at=DateTimeOffset.UtcNow.ToString("O");
            SubmitIonFullCycle(job,source);
        }
        catch(Exception e) when(e is ArgumentException||e is IOException||e is UnauthorizedAccessException)
        {job.finished=true;job.credential=null;Notice=job.state="이온주입 전송 보류 · "+e.Message;}
    }
    public string QueueIonTcadCandidate(string inspection,ProcessAnalysisView.Payload result)
    {
        if(FullCycleJob(inspection)!=null)return FullCycleJob(inspection).state;
        var job=IonDiagnosis(inspection);
        if(job==null)return "Gateway 자동 연동 꺼짐 · 보정 후보 DB 미전송";
        if(job.directDiagnosis!=null)return job.state;
        if(!Armed||job.finished||job.ready||string.IsNullOrEmpty(job.ion.completed_at))return "직접 진단 완료 · DB 전송 보류 / 검사 연결 확인 필요";
        try
        {
            var request=GatewayTcadProtocol.BuildIon(job,result);
            job.directDiagnosis=request.input_payload.provenance.tcad.direct_diagnosis;
            job.request=request;job.diagnosisRequest=null;job.kind="tcad_candidate_prediction";
            job.result=null;job.hasIdOn=job.hasId=false;job.origin=null;job.units=null;
            job.credential=Token;SaveRequest(job);job.ready=true;
            return Notice=job.state="직접 진단 완료 · 보정 후보 Gateway 예측 요청 대기";
        }
        catch(Exception error) when(error is ArgumentException||error is IOException||error is UnauthorizedAccessException)
        {return Notice=job.state="직접 진단 완료 · DB 전송 보류 · "+error.Message;}
    }
    void QueueIonDiagnosis(Job parent)
    {
        if(IonDiagnosis(parent.inspectionId)!=null)return;
        if(!Armed)throw new ArgumentException("자동 연동이 꺼져 새 진단은 보내지 않습니다.");
        var diagnosis=IonGatewayProtocol.Diagnose(parent);
        var request=new GatewayInspectionProtocol.Request{type=diagnosis.type,request_id=diagnosis.request_id,run_id=diagnosis.run_id,
            lot_id=diagnosis.lot_id,unit_id=diagnosis.unit_id,stage_id=diagnosis.stage_id};
        var job=new Job{kind="ion_diagnosis",request=request,diagnosisRequest=diagnosis,ion=parent.ion,inspectionId=parent.inspectionId,
            streamAddress=parent.streamAddress,credential=Token,state="전기특성 예측 완료 · Gateway 진단 요청 대기"};
        SaveRequest(job);jobs.Add(job);job.ready=true;
    }
    public static string RequestJson(Job job)=>job.filmRecordRequest!=null?JsonUtility.ToJson(job.filmRecordRequest):job.normalRequest!=null?JsonUtility.ToJson(job.normalRequest):job.diagnosisRequest!=null?JsonUtility.ToJson(job.diagnosisRequest):JsonUtility.ToJson(job.request);
    public void CancelIon(string inspection)
    {
        var job=IonJob(inspection);if(job==null||job.ready||job.finished||!string.IsNullOrEmpty(job.ion.completed_at))return;
        job.finished=true;job.credential=null;Notice=job.state="이온주입 검사 중단 · 완료값 전송하지 않음";
    }
    static void SaveRequest(Job job)
    {
        string folder=Path.Combine(Application.dataPath,"../Tools/Gateway/Requests");Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder,job.request.request_id+".json"),RequestJson(job));
        if(job.ion!=null)File.WriteAllText(Path.Combine(folder,job.request.request_id+".inspection.json"),JsonUtility.ToJson(job.ion,true));
    }
    public string IonSummary(string inspection)
    {
        var full=FullCycleJob(inspection);if(full!=null)return full.state;
        string direct=ProcessAnalysisView.Instance?ProcessAnalysisView.Instance.IonDirectSummary(inspection):null;
        if(direct!=null)return direct;
        var prediction=IonJob(inspection);if(prediction==null)return Armed?"검사 시작 후 완료값 자동 전송":"Gateway 자동 연동 꺼짐 · 주소·토큰 확인 후 연동 시작";
        var diagnosis=IonDiagnosis(inspection);
        if(diagnosis?.diagnosis!=null)return IonGatewayProtocol.Describe(diagnosis.diagnosis);
        return diagnosis?.state??prediction.state;
    }
}
