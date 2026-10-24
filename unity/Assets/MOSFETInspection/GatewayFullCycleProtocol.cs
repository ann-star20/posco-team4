using System;
using System.Collections.Generic;
using System.Linq;
using System.Globalization;
using System.Text.RegularExpressions;
using UnityEngine;

// Unity orchestrates the two independent Gateway requests. Gateway alone queues TCAD.
public static class GatewayFullCycleProtocol
{
    [Serializable] public class Electrical {public double vth,gm,id_on,bv;public bool hasBv;}
    [Serializable] public class Parameters {public double body_dose,epi_doping,oxide_thickness;}
    [Serializable] public class Estimate {public double mean,mean_ratio;}
    [Serializable] public class Knobs {public Estimate body_dose,epi_doping,oxide_thickness,dose,epi,oxide;}
    [Serializable] public class Decision {public string top_category;public double top_probability;public bool decided;}
    [Serializable] public class Compensation {public string route;public bool high_confidence,requires_human_approval;public Parameters target_process_parameters;}
    [Serializable] public class NextMeasurement {public string recommendation_code;}
    [Serializable] public class Result {public Decision decision;public Compensation compensation;public Knobs knobs;public NextMeasurement next_measurement;}
    [Serializable] public class ProposalCandidate {public string name,label;public Parameters process_parameters;public Electrical predicted_outputs;}
    [Serializable] public class Proposal {public string proposal_id;public ProposalCandidate[] candidates;}
    [Serializable] public class Units {public string vth,gm,id_on,bv;}
    [Serializable] public class SpecVerdict {public string overall,spec_source;}
    [Serializable] public class Metadata {public Units units;public string representation,calc_mode;}
    [Serializable] public class Response {public string status,request_id,job_id,result_origin,error_code,error_message;public Result result_payload;public Metadata metadata;public Proposal tcad_proposal;}
    [Serializable] public class EventPayload
    {
        public string request_id,job_id,proposal_id,tcad_request_id,status,error_code,error_message;
        public int candidate_index;
        public Response response;
        public Electrical result_payload;
        public Metadata metadata;
        public SpecVerdict spec_verdict;
    }
    [Serializable] public class Event {public long sequence;public string event_id,run_id,event_type,unity_mode;public bool approval_allowed;public EventPayload payload;}
    [Serializable] class DiagnosisInput {public Measurements measurements;public int n_wafers=1;public bool refine=false;}
    [Serializable] class Measurements {public double vth,gm,id_on,bv;}
    [Serializable] class DiagnosisRequest
    {
        public string type="diagnosis.requested",request_id,run_id,lot_id,unit_id,stage_id="diagnosis",model_contract_version="fab-ml-v1";
        // Gateway dispatches by type and rejects task_type; its Worker adds task_type for Jetson.
        public int schema_version=1,stage_attempt=1;
        public DiagnosisInput input_payload;
    }
    [Serializable] class Accepted {public string type,request_id,job_id,code;}
    public static bool Finite(double v)=>!double.IsNaN(v)&&!double.IsInfinity(v);
    public static bool ElectricalOk(Electrical m)=>m!=null&&m.hasBv&&Finite(m.vth)&&Finite(m.bv)&&m.vth>=1.7-1e-6&&m.vth<=2.6+1e-6&&m.bv>=40-1e-6;
    static void Uuid(string id){if(!Guid.TryParse(id,out _))throw new FormatException("UUID 확인 필요");}
    static Electrical ReadElectrical(string raw)
    {
        // Output objects are flat; require explicit numeric fields rather than JsonUtility's missing-field zeros.
        var match=Regex.Match(raw,"\"result_payload\"\\s*:\\s*\\{([^{}]*)\\}");
        if(!match.Success)throw new FormatException("전기특성 result_payload 없음");
        string body=match.Groups[1].Value;
        double Number(string key)
        {
            var m=Regex.Match(body,"(?:^|,)\\s*\""+key+"\"\\s*:\\s*(-?(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)\\s*(?=,|$)");
            if(!m.Success||!double.TryParse(m.Groups[1].Value,NumberStyles.Float,CultureInfo.InvariantCulture,out double n)||!Finite(n))throw new FormatException("전기특성 "+key+" 누락/형식 오류");
            return n;
        }
        bool nullBv=Regex.IsMatch(body,"(?:^|,)\\s*\"bv\"\\s*:\\s*null\\s*(?=,|$)");
        return new Electrical{vth=Number("vth"),gm=Number("gm"),id_on=Number("id_on"),bv=nullBv?0:Number("bv"),hasBv=!nullBv};
    }
    static void CheckUnits(Units u)
    {
        if(u==null||u.vth!="V"||u.gm!="uS/um"||u.id_on!="uA/um"||u.bv!="V")throw new FormatException("예측 단위 확인 필요: V / uS/um / uA/um / V");
    }
    public sealed class State
    {
        public readonly string Run,PredictionId,Lot,Unit;
        public string DiagnosisId{get;private set;}
        public string PredictionJob{get;private set;}
        public string DiagnosisJob{get;private set;}
        public string Route{get;private set;}
        public Electrical Electrical{get;private set;}
        public Response Diagnosis{get;private set;}
        public long Sequence{get;private set;}
        public bool Done{get;private set;}
        public bool BatchReceived{get;private set;}
        public bool ReviewRequired{get;private set;}
        public string ProposalId{get;private set;}
        public string DecisionStatus{get;private set;}
        public bool DecisionReceived=>DecisionStatus!=null;
        public string UnityMode{get;private set;}
        public bool ApprovalAllowed{get;private set;}
        public bool TestTcad=>UnityMode=="mock"||UnityMode=="fake"||Candidates.Values.Any(c=>c.metadata?.calc_mode=="fake");
        public bool RealApplicationAllowed=>ApprovalAllowed&&(UnityMode=="real"||UnityMode=="live"||UnityMode=="prod")&&!TestTcad;
        public void ObserveApprovalContext(string raw)
        {
            var e=JsonUtility.FromJson<Event>(raw);
            if(e?.run_id==Run&&!string.IsNullOrWhiteSpace(e.unity_mode)){UnityMode=e.unity_mode;ApprovalAllowed=e.approval_allowed;}
        }
        public bool KeepSubscription=>!Done||Route=="tcad_verify"&&!DecisionReceived;
        public void ObserveReview(string proposal)
        {
            Uuid(proposal);
            if(Route!="tcad_verify"||ProposalId!=null&&ProposalId!=proposal)throw new ArgumentException("TCAD 검토 그룹 불일치");
            ProposalId=proposal;ReviewRequired=true;Done=true;
            if(!DecisionReceived)Notice="TCAD 검증 완료 · 후보 승인 대기 / 미적용";
        }
        public void ObserveDecision(string proposal,string status)
        {
            ObserveReview(proposal);
            if(status!="approved"&&status!="rejected"||DecisionStatus!=null&&DecisionStatus!=status)throw new ArgumentException("TCAD 결정 불일치");
            DecisionStatus=status;Notice=status=="approved"?"Gateway 승인 확인 · 설비 설정 적용 상태 확인 / HOLD 유지":"Gateway 반려 확인 · 공정 설정 미변경";
        }
        public void ObserveReviewEvent(string raw)
        {
            var e=JsonUtility.FromJson<Event>(raw);
            if(e==null||e.run_id!=Run||e.sequence<=Sequence)throw new ArgumentException("검토 이벤트 RUN/순서 오류");
            Uuid(e.event_id);if(!eventIds.Add(e.event_id))throw new ArgumentException("검토 이벤트 중복 ID");
            Sequence=e.sequence;
        }
        public bool PendingDiagnosis=>Electrical!=null&&Diagnosis==null&&!Done;
        bool OriginalBlocks=>originalElectricalKnown&&!originalOk;
        public bool InspectionNg=>!equipmentOk||OriginalBlocks||Electrical!=null&&!ElectricalOk(Electrical);
        public bool NormalInspection=>Done&&equipmentOk&&!OriginalBlocks&&ElectricalOk(Electrical)&&Diagnosis==null&&Route==null;
        public bool WaitingTcad=>Route=="tcad_verify"&&!Done;
        public string Notice{get;private set;}="1/3 전기특성 예측 요청 대기";
        public readonly Dictionary<string,EventPayload> Candidates=new Dictionary<string,EventPayload>();
        public readonly Dictionary<string,string> RawCandidates=new Dictionary<string,string>();
        readonly bool equipmentOk,originalOk,originalElectricalKnown;
        readonly HashSet<string> eventIds=new HashSet<string>();
        public State(string run,string prediction,string lot,string unit,bool equipmentOk,bool originalOk,bool originalElectricalKnown=true)
        {
            Uuid(run);Uuid(prediction);
            if(run==prediction||string.IsNullOrWhiteSpace(lot)||string.IsNullOrWhiteSpace(unit))throw new FormatException("검사 LOT·웨이퍼·UUID 필요");
            Run=run;PredictionId=prediction;Lot=lot;Unit=unit;this.equipmentOk=equipmentOk;this.originalOk=originalOk;this.originalElectricalKnown=originalElectricalKnown;
        }
        public string DiagnosisJson()
        {
            if(!PendingDiagnosis)throw new InvalidOperationException("진단할 예측 결과 없음");
            if(DiagnosisId==null)DiagnosisId=Guid.NewGuid().ToString();
            var e=Electrical;
            string json=JsonUtility.ToJson(new DiagnosisRequest{request_id=DiagnosisId,run_id=Run,lot_id=Lot,unit_id=Unit,
                input_payload=new DiagnosisInput{measurements=new Measurements{vth=e.vth,gm=e.gm,id_on=e.id_on,bv=e.bv}}});
            return e.hasBv?json:Regex.Replace(json,"\"bv\"\\s*:\\s*[^,}]+","\"bv\":null");
        }
        public void AcceptAck(string raw,string request)
        {
            var a=JsonUtility.FromJson<Accepted>(raw);
            if(a?.type=="request.rejected")throw new FormatException("Gateway 요청 거절: "+(a.code??"사유 미제공"));
            if(a?.type!="request.accepted"||a.request_id!=request)throw new FormatException("요청 접수 응답 식별자 확인 필요");
            Uuid(a.job_id);
            if(request==PredictionId){if(PredictionJob!=null&&PredictionJob!=a.job_id)throw new FormatException("예측 JOB 불일치");PredictionJob=a.job_id;}
            else if(request==DiagnosisId){if(DiagnosisJob!=null&&DiagnosisJob!=a.job_id)throw new FormatException("진단 JOB 불일치");DiagnosisJob=a.job_id;}
            else throw new FormatException("다른 요청의 접수 응답");
        }
        public bool Accept(string raw)
        {
            var e=JsonUtility.FromJson<Event>(raw);
            if(e==null||e.run_id!=Run||e.sequence<=Sequence)return false;
            ObserveApprovalContext(raw);
            Uuid(e.event_id);if(string.IsNullOrEmpty(e.event_type)||e.payload==null)throw new FormatException("이벤트 형식 오류");
            if(!eventIds.Add(e.event_id))throw new FormatException("중복 event_id의 sequence 변경");
            var p=e.payload;bool prediction=p.request_id==PredictionId&&e.event_type.StartsWith("surrogate.",StringComparison.Ordinal);
            bool diagnosis=DiagnosisId!=null&&p.request_id==DiagnosisId&&e.event_type.StartsWith("diagnosis.",StringComparison.Ordinal);
            bool tcad=DiagnosisId!=null&&p.request_id==DiagnosisId&&e.event_type.StartsWith("tcad.verification.",StringComparison.Ordinal);
            if(!prediction&&!diagnosis&&!tcad){Sequence=e.sequence;return false;}
            string job=p.job_id??p.response?.job_id;Uuid(job);
            string expected=prediction?PredictionJob:DiagnosisJob;
            if(expected!=null&&expected!=job)throw new FormatException("다른 JOB의 결과");
            if(prediction)PredictionJob=job;else DiagnosisJob=job;
            if(prediction&&(e.event_type=="surrogate.completed"||e.event_type=="surrogate.failed"))
            {
                if(Electrical!=null){Sequence=e.sequence;return false;}
                CheckResponse(p.response,PredictionId,job);CheckUnits(p.response.metadata?.units);
                if(p.response.metadata?.representation=="synthetic_normalized_fixture")throw new FormatException("MOCK 결과로 후속 진단하지 않음");
                Electrical=ReadElectrical(raw);
                if(equipmentOk&&!OriginalBlocks&&ElectricalOk(Electrical)){Done=true;Notice="정상 검사·예측 OK · DB 결과 수신 / 진단·보정 생략";}
                else Notice="1/3 예측 완료 · 2/3 Gateway 진단 요청 대기";
            }
            if(diagnosis&&(e.event_type=="diagnosis.completed"||e.event_type=="diagnosis.failed"))
            {
                if(Diagnosis!=null){Sequence=e.sequence;return false;}
                CheckResponse(p.response,DiagnosisId,job);
                string route=p.response.result_payload?.compensation?.route;
                if(route!="tcad_verify"&&route!="apply"&&route!="no_action"&&route!="manual")throw new FormatException("진단 compensation.route 확인 필요");
                Diagnosis=p.response;Route=route;
                if(route=="tcad_verify")Notice="3/3 TCAD 검증 대기 · Gateway 자동 접수 / 약 20–30분";
                else{Done=true;Notice=route=="apply"?"보정안 수신 · 담당자 승인 대기 / 자동 적용 없음":route=="manual"?"진단 완료 · 담당자 검토 필요":"진단 완료 · 추가 보정 없음";}
            }
            if(tcad)
            {
                if(Route!="tcad_verify")throw new FormatException("TCAD 대상 진단 결과보다 먼저 수신됨");
                Uuid(p.proposal_id);
                if(ProposalId!=null&&ProposalId!=p.proposal_id)throw new FormatException("다른 TCAD 검증 그룹의 이벤트");
                ProposalId=p.proposal_id;
                if(e.event_type.StartsWith("tcad.verification.candidate_",StringComparison.Ordinal))
                {
                    Uuid(p.tcad_request_id);if(p.tcad_request_id==DiagnosisId||p.candidate_index<0)throw new FormatException("TCAD 후보 식별자 오류");
                    string status=e.event_type.Substring("tcad.verification.candidate_".Length);
                    if((status!="queued"&&status!="running"&&status!="succeeded"&&status!="failed"&&status!="cancelled")||p.status!=status)throw new FormatException("TCAD 상태 불일치");
                    foreach(var pair in Candidates)
                        if(pair.Key!=p.tcad_request_id&&pair.Value.proposal_id==p.proposal_id&&pair.Value.candidate_index==p.candidate_index)throw new FormatException("동일 후보의 TCAD ID 변경");
                    if(Candidates.TryGetValue(p.tcad_request_id,out var previous))
                    {
                        if(previous.proposal_id!=p.proposal_id||previous.candidate_index!=p.candidate_index)throw new FormatException("TCAD 후보 연결 변경");
                        if(previous.status=="succeeded"||previous.status=="failed"||previous.status=="cancelled"){Sequence=e.sequence;return false;}
                    }
                    if(status=="succeeded")p.result_payload=ReadElectrical(raw);
                    Candidates[p.tcad_request_id]=p;RawCandidates[p.tcad_request_id]=raw;
                    Notice="3/3 TCAD 후보 "+(p.candidate_index+1)+" · "+status+" / 배치 완료 대기";
                }
                else if(e.event_type=="tcad.verification.batch_completed"){BatchReceived=true;Done=true;Notice="TCAD 배치 종료 수신 · 후보별 성공/실패와 규격 확인 / 미승인·미적용";}
                else if(e.event_type=="tcad.verification.review_required"){ReviewRequired=true;Notice="TCAD 결과 담당자 검토 필요 · 미승인·미적용";}
            }
            Sequence=e.sequence;return true;
        }
        static void CheckResponse(Response r,string request,string job)
        {
            if(r==null||r.status!="succeeded")throw new FormatException((r?.error_code??"MODEL_FAILED")+" · "+r?.error_message);
            if(r.result_origin!="prod")throw new FormatException("실제 모델 응답(prod)만 후속 처리합니다.");
            if(!string.IsNullOrEmpty(r.request_id)&&r.request_id!=request||!string.IsNullOrEmpty(r.job_id)&&r.job_id!=job)throw new FormatException("응답 내부 식별자 불일치");
        }
    }
}
