using System;

// Gateway stores the candidate request and its model response. The Gateway team forwards to TCAD.
public static class GatewayTcadProtocol
{
    [Serializable] public class Fixed {public int diffusion_time_min=30,diffusion_temp_c=1100;public string source_drain_doping="arsenic 5e15 cm^-2";}
    [Serializable] public class Bias {public double vd_v=.1;public double[] vg_sweep_v={0.0,4.0};}
    [Serializable] public class Units {public string gm="uS/um",id_on="uA/um",vth="V",bv="V";}
    [Serializable] public class Setup
    {
        public string deck="최종_trench_template.in",athena_atlas="DeckBuild 5.0.10.R / Atlas 5.28.1.R";
        public Fixed @fixed=new Fixed();public double device_temperature_k=300;public Bias bias=new Bias();
        public string id_on_definition="Id at Vg=4.0 V",width_normalization="per 1 um of device width",bv_criterion="leakage 1e-9 A/um";
        public Units units=new Units();
    }
    [Serializable] public class Spec
    {
        public double vth_min=1.7,vth_max=2.6,bv_min=40,comparison_tolerance=1e-6;
        public string gm_id_rule="diagnostic_only_no_acceptance_limits";
    }
    [Serializable] public class Context
    {
        public string purpose="tcad_candidate_prediction_for_gateway_forwarding",recipient="gateway_team",diagnosis_source="separate_legacy_diagnostic_worker";
        public string diagnosis_request_id,proposal_id,diagnosis_model,diagnosis_mode,legacy_top_cause_ko,review_note,warning;
        public double cause_probability,dose_factor,oxide_factor;
        public GatewayInspectionProtocol.Parameters estimated_before;
        public ProcessAnalysisView.Payload direct_diagnosis;
        public bool exploratory_only,approved=false,applied=false;
        public string parent_gateway_request_id,parent_gateway_run_id,parent_gateway_job_id;
        public string predicted_outputs_source="matching surrogate.completed payload.response.result_payload; not a TCAD result";
        public Setup tcad_setup=new Setup();public Spec spec=new Spec();
    }
    [Serializable] public class Outputs {public double vth,gm,id_on,bv;}
    [Serializable] public class ForwardRequest
    {
        public string request_id,run_id,job_id,lot_id,unit_id,inspection_id,db_event_id;
        public long db_sequence;
        public GatewayInspectionProtocol.Parameters process_parameters;
        public Outputs predicted_outputs;
        public string[] requested_outputs={"vth","gm","id_on","bv"};
        public string dose_unit="cm^-2",epi_unit="cm^-3",oxide_unit="um";
        public Context context;
        public Setup tcad_setup;
        public Spec spec;
        public string status="candidate_prediction_committed_waiting_gateway_team_forward";
        public bool tcad_executed=false,approved=false,applied=false;
    }
    public static GatewayInspectionProtocol.Request Build(LotProcessAnalysis.Record record,GatewayInspectionBridge.Job parent=null)
    {
        var package=TcadVerificationPackage.Build(record,record?.result,parent);
        var p=package.diagnosis;
        var c=new Context{diagnosis_request_id=p.request_id,proposal_id=p.proposal_id,diagnosis_model=p.model_version,diagnosis_mode=p.mode,
            legacy_top_cause_ko=p.top_cause,cause_probability=p.top_probability,dose_factor=p.dose_factor,oxide_factor=p.oxide_factor,
            exploratory_only=!p.decided||p.top_cause=="정상",review_note=package.review_note,warning=p.warning,estimated_before=package.estimated_before,
            parent_gateway_request_id=package.gateway_request_id,parent_gateway_run_id=package.gateway_run_id,parent_gateway_job_id=package.gateway_job_id};
        string run=Guid.TryParse(package.gateway_run_id,out var existing)?existing.ToString():Guid.NewGuid().ToString();
        return new GatewayInspectionProtocol.Request{request_id=Guid.NewGuid().ToString(),run_id=run,lot_id=record.lotId,unit_id=package.unit_id,stage_id="tcad_candidate_prediction",
            input_payload=new GatewayInspectionProtocol.Input{process_parameters=package.candidate_after,provenance=new GatewayInspectionProtocol.Provenance{
                data_source="simulation",inspection_id=record.inspectionId,process_origin="diagnostic_posterior_candidate",electrical_source="legacy_diagnostic_worker",tcad=c}}};
    }
    public static GatewayInspectionProtocol.Request BuildIon(GatewayInspectionBridge.Job parent,ProcessAnalysisView.Payload result)
    {
        var s=parent?.ion;var reference=parent?.condition;
        if(s==null||reference==null||parent.request==null||parent.inspectionId!=s.inspection_id||reference.lot_id!=s.lot_id||
            parent.request.lot_id!=s.lot_id||parent.request.unit_id!=s.unit_id||string.IsNullOrEmpty(s.completed_at)||
            !GatewayInspectionProtocol.Positive(s.dose_cm2)||reference.dose_unit!="cm^-2"||reference.epi_unit!="cm^-3"||
            !GatewayInspectionProtocol.Positive(reference.body_dose)||!GatewayInspectionProtocol.Positive(reference.epi_doping)||!GatewayInspectionProtocol.Positive(reference.oxide_reference_um)||
            !Guid.TryParse(parent.request.request_id,out _)||!Guid.TryParse(parent.request.run_id,out _))
            throw new ArgumentException("완료된 이온주입 검사·LOT 기준·요청 식별자를 확인하세요.");
        IonGatewayProtocol.AttachDirectDiagnosis(parent.diagnosisRequest,result);
        var p=parent.diagnosisRequest.input_payload.provenance.direct_diagnosis;
        bool Factor(float n)=>n>=.84999f&&n<=1.15001f;
        if(p.baseline_version!=p.input.baseline_version||!GatewayInspectionProtocol.Positive(p.estimated_dose)||
            !GatewayInspectionProtocol.Positive(p.estimated_epi)||!GatewayInspectionProtocol.Positive(p.estimated_oxide)||!Factor(p.dose_factor)||!Factor(p.oxide_factor))
            throw new ArgumentException("진단 모델 기준·추정 상태·보정계수를 확인하세요.");
        var estimated=new GatewayInspectionProtocol.Parameters{body_dose=reference.body_dose*p.estimated_dose,
            epi_doping=reference.epi_doping*p.estimated_epi,oxide_thickness=reference.oxide_reference_um*p.estimated_oxide};
        var candidate=new GatewayInspectionProtocol.Parameters{body_dose=estimated.body_dose*p.dose_factor,
            epi_doping=estimated.epi_doping,oxide_thickness=estimated.oxide_thickness*p.oxide_factor};
        var context=new Context{diagnosis_request_id=p.request_id,proposal_id=p.proposal_id,diagnosis_model=p.model_version,diagnosis_mode=p.mode,
            legacy_top_cause_ko=p.top_cause,cause_probability=p.top_probability,dose_factor=p.dose_factor,oxide_factor=p.oxide_factor,
            estimated_before=estimated,direct_diagnosis=p,warning=p.warning,exploratory_only=!p.decided||p.top_cause=="정상",
            review_note=!p.decided?"원인 불확실: 추가 측정 및 탐색용 TCAD 검토 후보. 권장 레시피나 승인값이 아님.":
                p.top_cause=="정상"?"정상 후보: 보정 필요성이 확인되지 않음. 변경 권고가 아닌 검토 자료.":"모델 보정 후보: TCAD 재계산과 엔지니어 검토 필요. 장비 설정값이 아님."};
        return new GatewayInspectionProtocol.Request{request_id=parent.request.request_id,run_id=parent.request.run_id,lot_id=s.lot_id,unit_id=s.unit_id,
            stage_id="tcad_candidate_prediction",input_payload=new GatewayInspectionProtocol.Input{process_parameters=candidate,
                provenance=new GatewayInspectionProtocol.Provenance{data_source="simulation",equipment_id="IMP-01",inspection_id=s.inspection_id,
                    sample_id=s.csv_sample_id,csv_sha256=s.csv_sha256,completed_dose_cm2=s.dose_cm2,process_origin="diagnostic_posterior_candidate",
                    electrical_source="legacy_diagnostic_worker",tcad=context}}};
    }
    public static ForwardRequest Complete(GatewayInspectionBridge.Job job)
    {
        var r=job?.result;var c=job?.request?.input_payload?.provenance?.tcad;
        if(c==null||job.origin!="prod"||r==null||!r.vth_present||!r.gm_present||!r.bv_present||!job.hasIdOn||
            !Guid.TryParse(job.jobId,out _)||!Guid.TryParse(job.eventId,out _)||job.sequence<=0||
            !GatewayInspectionProtocol.Positive(r.vth)||!GatewayInspectionProtocol.Positive(r.gm)||!GatewayInspectionProtocol.Positive(r.id_on)||!GatewayInspectionProtocol.Positive(r.bv))
            throw new ArgumentException("같은 후보의 prod 예측값과 DB 완료 이벤트가 필요합니다.");
        return new ForwardRequest{request_id=job.request.request_id,run_id=job.request.run_id,job_id=job.jobId,lot_id=job.request.lot_id,unit_id=job.request.unit_id,
            inspection_id=job.inspectionId,db_event_id=job.eventId,db_sequence=job.sequence,process_parameters=job.request.input_payload.process_parameters,
            predicted_outputs=new Outputs{vth=r.vth,gm=r.gm,id_on=r.id_on,bv=r.bv},context=c,tcad_setup=c.tcad_setup,spec=c.spec};
    }
}
