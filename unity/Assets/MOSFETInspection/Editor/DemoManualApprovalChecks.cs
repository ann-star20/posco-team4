#if UNITY_EDITOR
using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad] public static class DemoManualApprovalChecks
{
    static DemoManualApprovalChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
    static void Tick()
    {
        if(!File.Exists("DemoManualApprovalCheck.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("DemoManualApprovalCheck.once");
        try{Run();File.WriteAllText("DemoManualApprovalCheck.result","DEMO_MANUAL_APPROVAL_OK\nCandidate change/reset, 1234 password scope, persisted confirmation, old LOT freeze, next LOT process parameters, um-to-nm, reload, Gateway payload, original quality limits. Offline only; no server request.\n"+DateTime.UtcNow.ToString("O"));}
        catch(Exception e){File.WriteAllText("DemoManualApprovalCheck.result","FAILED\n"+e);Debug.LogException(e);}
    }
    static GatewayLotConditions.Condition Register(string id)
    {
        var c=new GatewayLotConditions.Condition{lot_id=id,body_dose=7.7e12,epi_doping=1.7e16,oxide_reference_um=.06,dose_unit="cm^-2",epi_unit="cm^-3",source="offline demo approval check"};
        GatewayLotConditions.RegisterSimulationLot(id,c);return c;
    }
    public static void Run()
    {
        string oldPath=DemoApprovedLotRecipes.TestPath;
        DemoApprovedLotRecipes.TestPath=Path.GetFullPath("Temp/demo-approval-"+Guid.NewGuid().ToString("N")+".json");DemoApprovedLotRecipes.Reload();
        var root=new GameObject("Offline demo manual approval check"){hideFlags=HideFlags.HideAndDontSave};root.SetActive(false);
        try
        {
            GatewayApprovedRecipeChecks.Run();
            string oldLot="SIM-LOT-OLD-"+Guid.NewGuid().ToString("N"),nextLot="SIM-LOT-NEXT-"+Guid.NewGuid().ToString("N");
            Register(oldLot);Register(nextLot);
            var frozen=DemoApprovedLotRecipes.BeginLot(oldLot);
            var a=new GatewayApprovedRecipe.Approval{proposal_id=Guid.NewGuid().ToString(),run_id=Guid.NewGuid().ToString(),lot_id="SIM-LOT-INSPECTED",selected_tcad_request_id=Guid.NewGuid().ToString(),decision="approved",decided_by="offline-operator",real_tcad_confirmed_by_operator=true,confirmed_at=DateTimeOffset.UtcNow.ToString("O"),process_parameters=new GatewayFullCycleProtocol.Parameters{body_dose=9.622e12,epi_doping=1.276e16,oxide_thickness=.054263109}};
            var service=root.AddComponent<GatewayApprovedRecipe>();var ion=root.AddComponent<IonImplantCycle>();var ox=root.AddComponent<IntegratedOxidationCycle>();service.Bind(ion,ox);
            typeof(IonImplantCycle).GetField("running",BindingFlags.NonPublic|BindingFlags.Instance).SetValue(ion,true);
            Check(service.Stage(a,a.run_id,a.lot_id,a.proposal_id,a.selected_tcad_request_id)&&service.Pending!=null,"Busy approval not staged");
            DemoApprovedLotRecipes.Reload();
            Check(GatewayLotConditions.ForLot(oldLot).body_dose==frozen.body_dose,"In-flight LOT recipe changed");
            var next=DemoApprovedLotRecipes.BeginLot(nextLot);
            Check(next.body_dose==a.process_parameters.body_dose&&next.epi_doping==a.process_parameters.epi_doping&&next.oxide_reference_um==a.process_parameters.oxide_thickness&&next.approved_proposal_id==a.proposal_id,"Next LOT did not use saved approval");
            DemoApprovedLotRecipes.Reload();Check(GatewayLotConditions.ForLot(nextLot).approved_proposal_id==a.proposal_id,"LOT snapshot not persisted");
            var request=GatewayInspectionProtocol.BuildAutomatic(new GatewayInspectionSnapshot{lot_id=nextLot,unit_id="UNIT-1",inspection_id="OFFLINE",oxide_thickness_um=next.oxide_reference_um,thickness_points_nm=new[]{54.263109f,54.263109f,54.263109f},data_source="simulation"},next);
            Check(request.input_payload.process_parameters.body_dose==next.body_dose&&request.input_payload.process_parameters.epi_doping==next.epi_doping&&request.input_payload.process_parameters.oxide_thickness==next.oxide_reference_um,"Gateway request retained old recipe");
            a.process_parameters.body_dose=1;Check(GatewayLotConditions.ForLot(nextLot).body_dose!=1,"Approval snapshot is mutable");
            var film=root.AddComponent<EllipsometerCycle>();var spec=ScriptableObject.CreateInstance<FilmInspectionRecipe>();film.recipe=spec;film.electricalDemo=EllipsometerCycle.ElectricalDemo.Normal;
            typeof(EllipsometerCycle).GetField("approvedInspectionTargetNm",BindingFlags.NonPublic|BindingFlags.Instance).SetValue(film,(float)(next.oxide_reference_um*1000));
            var readings=film.DemoReadings();Check(Math.Abs(readings[1]-next.oxide_reference_um*1000*1.001)<.001,"Non-CSV demonstration ignored approved oxide");
            Check(spec.targetNm==60&&spec.lowerNm==57&&spec.upperNm==63,"Quality limits changed with recipe");UnityEngine.Object.DestroyImmediate(spec);
            SelectionChecks();
        }
        finally{UnityEngine.Object.DestroyImmediate(root);DemoApprovedLotRecipes.TestPath=oldPath;DemoApprovedLotRecipes.Reload();}
    }
    static void SelectionChecks()
    {
        var type=typeof(GatewayTcadApprovalView);var reviewType=type.GetNestedType("Review",BindingFlags.NonPublic);var review=Activator.CreateInstance(reviewType,true);
        var s=new GatewayFullCycleProtocol.State(Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),"LOT","UNIT",false,false,false);
        var p=new GatewayTcadApprovalProtocol.Proposal{proposal_id=Guid.NewGuid().ToString(),candidates=new[]{new GatewayTcadApprovalProtocol.Candidate{tcad_request_id=Guid.NewGuid().ToString()},new GatewayTcadApprovalProtocol.Candidate{tcad_request_id=Guid.NewGuid().ToString()}}};
        reviewType.GetField("job").SetValue(review,new GatewayInspectionBridge.Job{cycle=s});reviewType.GetField("proposal").SetValue(review,p);
        var scope=type.GetMethod("Scope",BindingFlags.Static|BindingFlags.NonPublic);
        string first=(string)scope.Invoke(null,new[]{review,(object)true,"operator"});reviewType.GetField("confirmedScope").SetValue(review,first);
        type.GetMethod("SelectCandidate",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,new[]{review,(object)1});
        Check(reviewType.GetField("confirmedScope").GetValue(review)==null,"Changing candidate retained real TCAD confirmation");
        string second=(string)scope.Invoke(null,new[]{review,(object)true,"operator"});Check(first!=second,"Candidate confirmation scope collided");
        var gate=new GatewayTcadApprovalView.AdminGate();Check(gate.Authorize("1234",first)&&!gate.Consume(second),"Password authorization moved to another candidate");
    }
}
#endif
