#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class ElectricalVerdictPlayCheck
{
    const string Key="ELECTRICAL_VERDICT_CHECK";
    static ElectricalVerdictPlayCheck(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        try
        {
            if(SessionState.GetInt(Key,0)==0)
            {
                if(!File.Exists("ElectricalVerdict.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("ElectricalVerdict.once");SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(!Application.isPlaying)return;
            var manager=LotProcessAnalysis.Instance;var view=ProcessAnalysisView.Instance;
            var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();
            Check(manager&&view&&film,"Missing runtime components");manager.enabled=false;
            film.lotId="ELECTRICAL-SPEC-CHECK";film.ResetDashboardDemo();film.readings=(float[])film.recipe.passDemo.Clone();film.EvaluateInspection();film.completed=true;
            Check(film.verdict=="PASS"&&!film.lotHeld,"Thickness PASS setup");
            var input=ProcessAnalysisView.NewInput(film.lotId,manager.PairedScenario.baseline_version,5,new ProcessAnalysisView.Measurement{vth=2.63f,gm=4.1e-6f,id4v=4.2e-6f,bv=42});
            Check(!manager.ReceiveElectrical(film,"old-inspection",input,true),"Stale inspection accepted");
            input.lot_id="OTHER";Check(!manager.ReceiveElectrical(film,film.InspectionId,input,true),"Wrong LOT accepted");input.lot_id=film.lotId;
            Check(manager.ReceiveElectrical(film,film.InspectionId,input,true),"Electrical data not attached");
            Check(manager.Latest(film.lotId).electricalVerdict==ElectricalSpec.Verdict.NG&&film.lotHeld&&!film.CanProceed,"Electrical NG failed to HOLD thickness PASS");
            Check(manager.Latest(film.lotId).status==LotProcessAnalysis.Status.Queued,"NG did not queue diagnosis");
            Check(!film.ApproveRelease(),"Electrical NG released by thickness approval");
            input.measurement.vth=2.26f;manager.ReceiveElectrical(film,film.InspectionId,input,false);
            Check(manager.Latest(film.lotId).electricalVerdict==ElectricalSpec.Verdict.Pending&&!film.ApproveRelease(),"Missing BV released LOT");
            manager.ReceiveElectrical(film,film.InspectionId,input,true);
            Check(manager.Latest(film.lotId).electricalVerdict==ElectricalSpec.Verdict.OK&&film.lotHeld,"OK automatically released HOLD");
            Check(film.ApproveRelease(),"Existing thickness review blocked despite electrical OK");
            input.measurement.bv=39;manager.ReceiveElectrical(film,film.InspectionId,input,true);
            Check(manager.Latest(film.lotId).electricalVerdict==ElectricalSpec.Verdict.NG&&!film.CanProceed,"BV NG not blocked");
            film.ResetDashboardDemo();film.readings=(float[])film.recipe.passDemo.Clone();film.EvaluateInspection();film.completed=true;
            Check(!film.CanProceed&&!film.ApproveRelease(),"Reinspection bypassed previous electrical NG");
            Check(manager.RequestsSent==0,"Offline integration test dispatched a remote request");
            File.WriteAllText("ElectricalVerdictPlay.result","ELECTRICAL_VERDICT_PLAY_OK\nThickness PASS + electrical NG holds LOT; queues diagnosis; missing BV pending; OK never auto-releases; stale/other LOT rejected; reinspection cannot bypass electrical NG. No Jetson/TCAD execution or recipe application.");
            SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;
        }
        catch(Exception e){File.WriteAllText("ElectricalVerdictPlay.result","FAILED: "+e);SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;Debug.LogException(e);}
    }
}
#endif
