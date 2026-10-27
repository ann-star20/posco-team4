using System;
using System.IO;
using System.Text;
using UnityEngine;

// A review file, not a Gateway command or an approved equipment recipe.
public static class TcadVerificationPackage
{
    [Serializable] public class Package
    {
        public string type="tcad.verification.package",created_at,inspection_id,lot_id,unit_id;
        public int schema_version=1;
        public string data_source="simulation",status="awaiting_tcad_review",proposal_id;
        public string gateway_request_id,gateway_run_id,gateway_job_id;
        public string candidate_basis="posterior_mean_ratios_times_model_reference_then_correction_factors";
        public string dose_unit="cm^-2",epi_unit="cm^-3",oxide_unit="um";
        public bool approved=false,applied=false;
        public string review_note;
        public GatewayInspectionSnapshot inspection;
        public GatewayLotConditions.Condition model_reference;
        public GatewayInspectionProtocol.Parameters inspection_process_conditions,estimated_before,candidate_after;
        public ProcessAnalysisView.Payload diagnosis;
        public string[] requested_outputs={"vth","gm","id_on","bv"};
        public float vth_min=ElectricalSpec.VthMin,vth_max=ElectricalSpec.VthMax,bv_min=ElectricalSpec.BvMin;
        public string gm_id_rule="diagnostic_only_no_acceptance_limits";
        public string tcad_setup="TCAD engineer must identify device deck, solver version, bias conditions and width normalization; no deck is inferred by Unity";
    }
    public static Package Build(LotProcessAnalysis.Record r,ProcessAnalysisView.Payload p,GatewayInspectionBridge.Job job=null)
    {
        if(r==null||r.superseded||r.inspectionSnapshot==null||r.tcadCondition==null||p?.input?.measurement==null||
            p.delivery!="computed"||p.applied||p.tcad_status!="not_run"||p.request_id!=r.requestId||p.lot_id!=r.lotId||
            p.baseline_version!=r.electrical?.baseline_version||p.input.lot_id!=r.lotId||
            JsonUtility.ToJson(p.input.measurement)!=JsonUtility.ToJson(r.electrical.measurement))
            throw new ArgumentException("해당 검사의 새 진단 결과와 고정된 공정조건이 필요합니다.");
        var s=r.inspectionSnapshot;var c=r.tcadCondition;
        if(s.inspection_id!=r.inspectionId||s.lot_id!=r.lotId||c.lot_id!=r.lotId||!GatewayInspectionProtocol.Positive(c.oxide_reference_um)||
            !Positive(p.estimated_dose)||!Positive(p.estimated_epi)||!Positive(p.estimated_oxide)||
            !Factor(p.dose_factor)||!Factor(p.oxide_factor))throw new ArgumentException("검사 식별자·기준값·보정계수를 확인하세요.");
        var before=GatewayInspectionProtocol.BuildAutomatic(s,c).input_payload.process_parameters;
        var estimated=new GatewayInspectionProtocol.Parameters{body_dose=c.body_dose*p.estimated_dose,epi_doping=c.epi_doping*p.estimated_epi,oxide_thickness=c.oxide_reference_um*p.estimated_oxide};
        // Agent compensate() applies factors to posterior state, not to the measured/registered process values.
        var candidate=new GatewayInspectionProtocol.Parameters{body_dose=estimated.body_dose*p.dose_factor,epi_doping=estimated.epi_doping,oxide_thickness=estimated.oxide_thickness*p.oxide_factor};
        var result=new Package{created_at=DateTimeOffset.UtcNow.ToString("O"),inspection_id=r.inspectionId,lot_id=r.lotId,unit_id=s.unit_id,proposal_id=p.proposal_id,
            inspection=s,model_reference=c,inspection_process_conditions=before,estimated_before=estimated,candidate_after=candidate,diagnosis=p,
            review_note=!p.decided?"원인 불확실: 추가 측정 및 탐색용 TCAD 검토 후보. 권장 레시피나 승인값이 아님.":p.top_cause=="정상"?"정상 후보: 보정 필요성이 확인되지 않음. 변경 권고가 아닌 검토 자료.":"모델 보정 후보: TCAD 재계산과 엔지니어 검토 필요. 장비 설정값이 아님."};
        if(job!=null&&job.inspectionId==r.inspectionId&&job.request?.lot_id==r.lotId)
        {result.gateway_request_id=job.request.request_id;result.gateway_run_id=job.request.run_id;result.gateway_job_id=job.jobId;}
        return result;
    }
    static bool Positive(float n)=>GatewayInspectionProtocol.Positive(n);
    static bool Factor(float n)=>Positive(n)&&n>=.84999f&&n<=1.15001f;
    public static string Save(LotProcessAnalysis.Record r,ProcessAnalysisView.Payload p,GatewayInspectionBridge.Job job=null)
    {
        var package=Build(r,p,job);
        string folder=Path.GetFullPath(Path.Combine(Application.dataPath,"../Tools/TCAD/Outbox"));Directory.CreateDirectory(folder);
        string path=Path.Combine(folder,Guid.NewGuid().ToString("N")+".json");
        File.WriteAllText(path,JsonUtility.ToJson(package,true),new UTF8Encoding(false));return path;
    }
}
