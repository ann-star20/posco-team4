using System;
using UnityEngine;

// Verified Gateway approval changes process setpoints, never metrology limits or historical results.
public sealed class GatewayApprovedRecipe : MonoBehaviour
{
    [Serializable] public sealed class Approval
    {
        public string proposal_id,run_id,lot_id,selected_tcad_request_id,decision,decided_by;
        public GatewayFullCycleProtocol.Parameters process_parameters;
        public bool real_tcad_confirmed_by_operator;
        public string confirmed_at;
    }
    public string Status{get;private set;}="승인 보정값 없음";
    public Approval Applied{get;private set;}
    public Approval Pending{get;private set;}
    IonImplantCycle ion;IntegratedOxidationCycle oxidation;
    readonly System.Collections.Generic.Dictionary<string,string> accepted=new System.Collections.Generic.Dictionary<string,string>();
    public void Bind(IonImplantCycle implant,IntegratedOxidationCycle furnace){ion=implant;oxidation=furnace;}
    public static void Validate(Approval a,string expectedRun,string expectedLot,string expectedProposal,string expectedCandidate)
    {
        if(a==null||a.decision!="approved"||string.IsNullOrWhiteSpace(a.decided_by)||
           !Guid.TryParse(a.run_id,out _)||string.IsNullOrWhiteSpace(a.lot_id)||!Guid.TryParse(a.proposal_id,out _)||!Guid.TryParse(a.selected_tcad_request_id,out _)||
           a.run_id!=expectedRun||a.lot_id!=expectedLot||a.proposal_id!=expectedProposal||a.selected_tcad_request_id!=expectedCandidate)
            throw new ArgumentException("Gateway 승인과 대상 RUN·LOT·후보 식별자가 일치해야 합니다.");
        var p=a.process_parameters;
        if(p==null||!GatewayInspectionProtocol.Positive(p.body_dose)||!GatewayInspectionProtocol.Positive(p.epi_doping)||!GatewayInspectionProtocol.Positive(p.oxide_thickness)||
           !FilmInspectionRecipe.Finite((float)p.body_dose)||!FilmInspectionRecipe.Finite((float)(p.oxide_thickness*1000)))
            throw new ArgumentException("승인 공정값 누락 또는 단위/범위 오류");
    }
    public bool Stage(Approval approval,string run,string lot,string proposal,string candidate)
    {
        Validate(approval,run,lot,proposal,candidate);
        if(accepted.TryGetValue(proposal,out var previous))
        {
            if(previous!=candidate)throw new InvalidOperationException("같은 보정 그룹의 승인 후보가 변경됐습니다. 서버 결정 확인 필요");
            return false;
        }
        if(!ion||!oxidation)throw new InvalidOperationException("보정값을 적용할 이온주입기·산화로 연결이 필요합니다.");
        if(Pending!=null)throw new InvalidOperationException("앞선 승인값의 적용 대기 상태를 먼저 확인하세요.");
        if(approval.real_tcad_confirmed_by_operator)DemoApprovedLotRecipes.Remember(approval);
        Pending=JsonUtility.FromJson<Approval>(JsonUtility.ToJson(approval));accepted.Add(proposal,candidate);
        Status="승인값 저장 · 진행 중 LOT 유지 / 다음 LOT용 설정 준비 대기";ApplyIfIdle();return true;
    }
    void Update()=>ApplyIfIdle();
    public bool ApplyIfIdle()
    {
        if(Pending==null||!ion||!oxidation||ion.Running||oxidation.Running)return false;
        var a=Pending;var p=a.process_parameters;
        ion.targetDose=(float)p.body_dose;
        oxidation.targetOxideNm=(float)(p.oxide_thickness*1000);
        // Epitaxy is a recipe parameter; no epitaxy actuator exists in this scene.
        ion.approvedEpiDoping=oxidation.approvedEpiDoping=p.epi_doping;
        ion.approvedRecipeId=oxidation.approvedRecipeId=a.proposal_id;
        Applied=a;Pending=null;
        Status="다음 LOT 기본 설정 준비 완료 · 주입 "+p.body_dose.ToString("0.000E+00")+" cm⁻² / 산화막 "+oxidation.targetOxideNm.ToString("F3")+" nm · 기존 CSV·판정·HOLD 유지";
        return true;
    }
}
