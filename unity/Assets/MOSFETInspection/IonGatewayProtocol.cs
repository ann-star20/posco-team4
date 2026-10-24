using System;
using UnityEngine;

// IMP-01 uses completed simulated dose and frozen, registered LOT context, not CSV truth labels.
public static class IonGatewayProtocol
{
    public enum Review {Pending,Normal,Diagnosis}
    public static Review ReviewCompleted(IonImplantCycle source)
    {
        if(!source||!source.completed||source.failed||source.InspectionCsv==null)return Review.Pending;
        var m=CsvMeasurements(source.InspectionCsv);
        var dose=IonDoseAssessment.Evaluate(source.dose,source.dashboard?source.dashboard.doseLower:0,
            source.dashboard?source.dashboard.doseUpper:0,true,false);
        var electrical=ElectricalSpec.Evaluate((float)m.vth,(float)m.bv);
        if(dose=="FAIL"||electrical==ElectricalSpec.Verdict.NG)return Review.Diagnosis;
        return dose=="OK"&&electrical==ElectricalSpec.Verdict.OK?Review.Normal:Review.Pending;
    }

    [Serializable] public class Snapshot
    {
        public string inspection_id,lot_id,unit_id,completed_at,condition_source,csv_sample_id,csv_sha256,electrical_source;
        public double dose_cm2,target_cm2,lower_cm2,upper_cm2,epi_doping,oxide_thickness_um;
    }
    [Serializable] public class Measurements {public double vth,gm,id_on,bv;}
    [Serializable] public class InspectionResult
    {
        public string purpose="normal_inspection_record",completed_at,verdict="OK",dose_verdict="OK",electrical_verdict="OK";
        public double dose_cm2,target_cm2,lower_cm2,upper_cm2;
        public string dose_unit="cm^-2",vth_unit="V",gm_unit="uS/um",id_on_unit="uA/um",bv_unit="V";
        public Measurements measurements;
        public bool diagnosis_requested=false,correction_candidate=false;
    }
    // Separate wire type: JsonUtility expands null nested classes into default objects.
    [Serializable] public class NormalProvenance
    {
        public string equipment_id="IMP-01",data_source="jetson_csv_test",sample_id,csv_sha256,inspection_id,condition_source;
        public string electrical_source="tcad_csv_not_measurement",process_origin="completed_csv_ion_dose_and_same_row_context";
        public string dose_unit="cm^-2",epi_unit="cm^-3",oxide_unit="um";
        public double completed_dose_cm2;
        public InspectionResult inspection_result;
    }
    [Serializable] public class NormalInput
    {
        public GatewayInspectionProtocol.Parameters process_parameters;
        public string[] requested_outputs={"vth","gm","id_on","bv"};
        public NormalProvenance provenance;
    }
    [Serializable] public class NormalRequest
    {
        public string type="surrogate.requested",request_id,run_id,lot_id,unit_id,stage_id="ion_inspection_record",model_contract_version="fab-ml-v1";
        public int schema_version=1,stage_attempt=1;
        public NormalInput input_payload;
    }
    public static NormalRequest BuildNormalRecord(GatewayInspectionBridge.Job job)
    {
        var s=job?.ion;var d=job?.diagnosisRequest;var m=d?.input_payload?.measurements;
        if(s==null||m==null||job.request==null||s.lot_id!=d.lot_id||s.unit_id!=d.unit_id||job.inspectionId!=s.inspection_id||
            string.IsNullOrEmpty(s.completed_at)||!Guid.TryParse(job.request.request_id,out _)||!Guid.TryParse(job.request.run_id,out _)||
            IonDoseAssessment.Evaluate((float)s.dose_cm2,s.lower_cm2,s.upper_cm2,true,false)!="OK"||
            ElectricalSpec.Evaluate((float)m.vth,(float)m.bv)!=ElectricalSpec.Verdict.OK)
            throw new ArgumentException("같은 완료 검사의 주입량·전기특성 OK 판정이 필요합니다.");
        var process=Build(s).input_payload.process_parameters;
        return new NormalRequest{request_id=job.request.request_id,run_id=job.request.run_id,lot_id=s.lot_id,unit_id=s.unit_id,
            input_payload=new NormalInput{process_parameters=process,provenance=new NormalProvenance{
                sample_id=s.csv_sample_id,csv_sha256=s.csv_sha256,inspection_id=s.inspection_id,condition_source=s.condition_source,completed_dose_cm2=s.dose_cm2,
                inspection_result=new InspectionResult{completed_at=s.completed_at,dose_cm2=s.dose_cm2,
                    target_cm2=s.target_cm2,lower_cm2=s.lower_cm2,upper_cm2=s.upper_cm2,
                    measurements=JsonUtility.FromJson<Measurements>(JsonUtility.ToJson(m))}}}};
    }

    [Serializable] public class Provenance
    {
        public string data_source="simulation",equipment_id="IMP-01",inspection_id,parent_request_id;
        public string electrical_source="surrogate_prediction_not_measurement";
        public string sample_id,csv_sha256;
        public string vth_unit="V",gm_unit="uS/um",id_on_unit="uA/um",bv_unit="V";
        public string archive_purpose;
        public ProcessAnalysisView.Payload direct_diagnosis;
    }
    [Serializable] public class DiagnosisInput
    {
        public Measurements measurements;
        public int n_wafers=1;
        public bool refine=false;
        public Provenance provenance;
    }
    [Serializable] public class DiagnosisRequest
    {
        public string type="diagnosis.requested",request_id,run_id,lot_id,unit_id,stage_id="ion_diagnosis",model_contract_version="fab-ml-v1";
        public int schema_version=1,stage_attempt=1;
        public DiagnosisInput input_payload;
    }
    [Serializable] public class Decision {public string top_category;public double top_probability;public bool decided;}
    [Serializable] public class Compensation
    {
        public string route;public bool high_confidence;
        public GatewayInspectionProtocol.Parameters target_process_parameters;
    }
    [Serializable] public class DiagnosisResult {public Decision decision;public Compensation compensation;}
    [Serializable] public class DiagnosisResponse
    {
        public string status,request_id,job_id,result_origin,model_version;
        public bool anomaly_detected;
        public DiagnosisResult result_payload;
    }
    [Serializable] class DiagnosisPayload {public DiagnosisResponse response;}
    [Serializable] class DiagnosisEnvelope {public DiagnosisPayload payload;}
    public static void AttachDirectDiagnosis(DiagnosisRequest request,ProcessAnalysisView.Payload result)
    {
        var m=result?.input?.measurement;var expected=request?.input_payload?.measurements;
        bool Same(double a,double b)=>Math.Abs(a-b)<=Math.Max(1e-8,Math.Abs(b)*1e-6);
        if(m==null||expected==null||result.delivery!="computed"||result.applied||result.tcad_status!="not_run"||
            result.request_id!=result.input.request_id||result.lot_id!=request.lot_id||result.input.lot_id!=request.lot_id||
            result.input.units?.gm!="A/V/um"||result.input.units?.id4v!="A/um"||
            !Same(m.vth,expected.vth)||!Same(m.gm*1e6,expected.gm)||!Same(m.id4v*1e6,expected.id_on)||!Same(m.bv,expected.bv))
            throw new ArgumentException("직접 진단 입력과 해당 CSV 검사·LOT·단위가 일치해야 합니다.");
        request.input_payload.provenance.direct_diagnosis=JsonUtility.FromJson<ProcessAnalysisView.Payload>(JsonUtility.ToJson(result));
        request.input_payload.provenance.archive_purpose="preserve_jetson_direct_result_in_committed_request; gateway_rediagnosis_is_separate";
    }
    public static string DescribeDirect(ProcessAnalysisView.Payload result)
    {
        if(result==null)return "Jetson 직접 진단 결과 대기";
        string correction=result.top_cause=="정상"&&result.decided?"보정 제안 없음":
            $"추정 상태 대비 보정 후보: 도즈 ×{result.dose_factor:F3} / 산화막 ×{result.oxide_factor:F3} / 에피 변경 없음";
        return $"원인: {result.top_cause} ({result.top_probability:P0}) · {(result.decided?"판정됨":"불확실 · 추가 측정 필요")}\n{correction}";
    }
    public static Measurements CsvMeasurements(JetsonTestDataProtocol.Selection selection)
    {
        if(selection?.measurement_source!="TCAD"||!JetsonTestDataProtocol.CanSelect(selection.row,"TCAD"))
            throw new ArgumentException("같은 CSV 행의 TCAD 전기특성 4개 값이 필요합니다. PC 예측값으로 대체하지 않습니다.");
        var m=selection.row.tcad;
        // CSV stores SI units; the diagnosis service accepts micro units.
        return new Measurements{vth=m.vth,gm=m.gm*1e6,id_on=m.id4v*1e6,bv=m.bv};
    }
    public static DiagnosisRequest DiagnoseCsv(Snapshot snapshot,JetsonTestDataProtocol.Selection selection,string requestId,string runId)
    {
        var m=CsvMeasurements(selection);
        if(snapshot==null||string.IsNullOrWhiteSpace(snapshot.inspection_id)||string.IsNullOrWhiteSpace(snapshot.lot_id)||string.IsNullOrWhiteSpace(snapshot.unit_id)||
            snapshot.csv_sample_id!=selection.row.id||snapshot.csv_sha256!=selection.dataset_sha256||selection.dataset_sha256?.Length!=64||
            !Guid.TryParse(requestId,out _)||!Guid.TryParse(runId,out _))
            throw new ArgumentException("CSV 행·해시·검사 ID·LOT·웨이퍼 연결을 확인하세요.");
        return new DiagnosisRequest{request_id=requestId,run_id=runId,lot_id=snapshot.lot_id,unit_id=snapshot.unit_id,
            input_payload=new DiagnosisInput{measurements=m,n_wafers=1,refine=false,
                provenance=new Provenance{data_source="jetson_csv_test",electrical_source="tcad_csv_not_measurement",inspection_id=snapshot.inspection_id,
                    sample_id=selection.row.id,csv_sha256=selection.dataset_sha256}}};
    }
    public static string CsvElectricalText(JetsonTestDataProtocol.Selection selection)
    {
        try
        {
            var m=CsvMeasurements(selection);
            return $"전기특성 {ElectricalSpec.Evaluate((float)m.vth,(float)m.bv)} · TCAD CSV {selection.row.id}\nVth {m.vth:F3} V / BV {m.bv:F3} V / gm {m.gm:F3} µS/µm / Id {m.id_on:F3} µA/µm";
        }
        catch(ArgumentException){return "전기특성 없음 · 같은 CSV 행의 TCAD 값 확인 필요";}
    }
    public static GatewayInspectionProtocol.Request Build(Snapshot s)
    {
        if(s==null||string.IsNullOrWhiteSpace(s.inspection_id)||string.IsNullOrWhiteSpace(s.lot_id)||string.IsNullOrWhiteSpace(s.unit_id)||
            !GatewayInspectionProtocol.Positive(s.dose_cm2)||!GatewayInspectionProtocol.Positive(s.epi_doping)||!GatewayInspectionProtocol.Positive(s.oxide_thickness_um))
            throw new ArgumentException("완료된 주입량과 같은 LOT의 TCAD 공정조건이 필요합니다.");
        var request=GatewayInspectionProtocol.BuildPhysical(null,s.lot_id,s.unit_id,s.inspection_id,null,s.dose_cm2,s.epi_doping,s.oxide_thickness_um);
        request.stage_id="ion_implantation";
        var p=request.input_payload.provenance;
        p.data_source="simulation";p.equipment_id="IMP-01";p.process_origin="completed_ion_dose_and_registered_lot_context";
        p.condition_source=s.condition_source;p.electrical_source="surrogate_prediction_not_measurement";
        p.completed_dose_cm2=s.dose_cm2;
        if(!string.IsNullOrEmpty(s.csv_sample_id))
        {
            p.data_source="jetson_csv_test";p.process_origin="completed_csv_ion_dose_and_same_row_context";
            p.sample_id=s.csv_sample_id;p.csv_sha256=s.csv_sha256;
        }
        return request;
    }
    public static DiagnosisRequest Diagnose(GatewayInspectionBridge.Job parent)
    {
        var r=parent?.result;var units=parent?.units;
        if(parent?.ion==null||parent.request==null||parent.inspectionId!=parent.ion.inspection_id||parent.request.lot_id!=parent.ion.lot_id||parent.request.unit_id!=parent.ion.unit_id)
            throw new ArgumentException("예측 결과와 주입 검사 ID·LOT·웨이퍼가 일치해야 합니다.");
        if(parent?.ion==null||parent.origin!="prod"||r==null||!r.vth_present||!r.gm_present||!parent.hasIdOn||!r.bv_present||
            !GatewayInspectionProtocol.Positive(r.vth)||!GatewayInspectionProtocol.Positive(r.gm)||!GatewayInspectionProtocol.Positive(r.id_on)||!GatewayInspectionProtocol.Positive(r.bv))
            throw new ArgumentException("같은 주입 검사의 실제 모델 예측 4개 출력이 필요합니다. MOCK·누락·실패 결과는 진단하지 않습니다.");
        if(units==null||units.vth!="V"||units.gm!="uS/um"||units.id_on!="uA/um"||units.bv!="V")
            throw new ArgumentException("서버 예측 단위 확인 필요: V / uS/um / uA/um / V");
        return new DiagnosisRequest{request_id=Guid.NewGuid().ToString(),run_id=parent.request.run_id,lot_id=parent.request.lot_id,unit_id=parent.request.unit_id,
            input_payload=new DiagnosisInput{measurements=new Measurements{vth=r.vth,gm=r.gm,id_on=r.id_on,bv=r.bv},
                provenance=new Provenance{inspection_id=parent.inspectionId,parent_request_id=parent.request.request_id}}};
    }
    public static DiagnosisResponse ReadDiagnosis(GatewayInspectionBridge.Job job,GatewayStreamClient.DbEvent e)
    {
        if(job?.diagnosisRequest==null||!GatewayInspectionProtocol.Matches(job.request,e)||e.event_type!="diagnosis.completed"||string.IsNullOrEmpty(e.rawJson))
            throw new ArgumentException("이 주입 검사와 연결된 diagnosis.completed 이벤트가 필요합니다.");
        var response=JsonUtility.FromJson<DiagnosisEnvelope>(e.rawJson)?.payload?.response;
        if(!string.IsNullOrEmpty(response?.request_id)&&response.request_id!=job.request.request_id||
            !string.IsNullOrEmpty(response?.job_id)&&response.job_id!=(job.jobId??e.payload.job_id))
            throw new ArgumentException("진단 응답 내부 request_id/job_id가 이 검사와 다릅니다.");
        if(response?.status!="succeeded"||response.result_origin!="prod"||string.IsNullOrWhiteSpace(response.result_payload?.decision?.top_category))
            throw new ArgumentException("진단 결과 형식·출처 확인 필요 · 정상 또는 0으로 대체하지 않습니다.");
        return response;
    }
    public static string Describe(DiagnosisResponse response)
    {
        var decision=response?.result_payload?.decision;if(decision==null)return "원인 분석 결과 대기";
        var c=response.result_payload.compensation;var p=c?.target_process_parameters;
        string cause=decision.top_category=="normal"?"정상":decision.top_category;
        string correction=p!=null&&GatewayInspectionProtocol.Positive(p.body_dose)&&GatewayInspectionProtocol.Positive(p.epi_doping)&&GatewayInspectionProtocol.Positive(p.oxide_thickness)?
            $"보정 후보: 도즈 {p.body_dose:0.00E+00} cm⁻² / 에피 {p.epi_doping:0.00E+00} cm⁻³ / 산화막 {p.oxide_thickness:G6} µm":
            c?.route=="none"||decision.top_category=="normal"?"보정 제안 없음":"보정 공정값 미제공 · 진단 원문 확인";
        return $"원인: {cause} ({decision.top_probability:P0}) · {(decision.decided?"판정됨":"불확실 · 추가 측정 필요")}\n{correction}";
    }
}
