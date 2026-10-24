#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class TcadHandoffChecks
{
    static TcadHandoffChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode||!File.Exists("TcadHandoffCheck.once"))return;
        File.Delete("TcadHandoffCheck.once");
        try
        {
            var input=ProcessAnalysisView.NewInput("LOT-001","tcad-gp-test",1,new ProcessAnalysisView.Measurement{vth=3.273f,gm=3.875e-6f,id4v=2.474e-6f,bv=50.446f});
            var s=GatewayInspectionSnapshot.Create("inspection-test","LOT-001","unit-test",new[]{59.172f,59.172f,59.172f},input,true);
            s.has_csv_ratios=true;s.csv_dose_ratio=1.6482;s.csv_epi_ratio=.732;s.csv_oxide_ratio=.9862;s.reference_thickness_nm=60;
            var c=GatewayLotConditions.ForLot("LOT-001");
            var r=new LotProcessAnalysis.Record{lotId="LOT-001",inspectionId=s.inspection_id,requestId=input.request_id,electrical=input,inspectionSnapshot=s,tcadCondition=c};
            var p=new ProcessAnalysisView.Payload{input=input,lot_id=r.lotId,request_id=r.requestId,baseline_version=input.baseline_version,proposal_id="proposal-test",delivery="computed",tcad_status="not_run",estimated_dose=1.4f,estimated_epi=.75f,estimated_oxide=1.1f,dose_factor=.85f,oxide_factor=1.15f,top_cause="도즈+에피",decided=false};
            var package=TcadVerificationPackage.Build(r,p);
            bool Near(double a,double b)=>Math.Abs(a-b)<Math.Max(1e-8,Math.Abs(b)*1e-6);
            Check(Near(package.inspection_process_conditions.body_dose,7.7e12*1.6482),"CSV before-state dose lost");
            Check(Near(package.candidate_after.body_dose,7.7e12*1.4*.85),"Factor must apply to inferred state, not known CSV dose");
            Check(Near(package.candidate_after.oxide_thickness,.06*1.1*1.15),"Oxide reference/factor conversion failed");
            Check(Near(package.candidate_after.epi_doping,package.estimated_before.epi_doping),"Epi changed by correction");
            Check(!package.approved&&!package.applied&&package.review_note.Contains("불확실")&&package.inspection.electrical.current_quantity=="id4v","Uncertain proposal or measurement identity misrepresented");
            string wire=JsonUtility.ToJson(package);
            Check(!wire.Contains("api_token")&&!wire.Contains("X-Unity-Token")&&wire.Contains("candidate_after"),"Export missing candidate or contains token");
            bool Reject(){try{TcadVerificationPackage.Build(r,p);return false;}catch(ArgumentException){return true;}}
            p.delivery="replay";Check(Reject(),"Historical replay exported as fresh diagnosis");p.delivery="computed";
            p.input=JsonUtility.FromJson<ProcessAnalysisView.Input>(JsonUtility.ToJson(input));p.input.measurement.vth=2;Check(Reject(),"Different measurement exported");p.input=input;
            r.superseded=true;Check(Reject(),"Superseded inspection exported");r.superseded=false;
            p.oxide_factor=float.NaN;Check(Reject(),"Invalid factor exported");
            File.WriteAllText("TcadHandoffCheck.result","TCAD_HANDOFF_OK\nFrozen same-inspection CSV inputs / physical units / posterior-state correction / epi unchanged / IDs and missing context guarded\nReplay, superseded, changed measurements and NaN rejected / unverified and unapplied flags preserved / no token exported\nOffline only; no TCAD, approval or Gateway job sent");
        }
        catch(Exception error){File.WriteAllText("TcadHandoffCheck.result",error.ToString());Debug.LogException(error);}
    }
}
#endif
