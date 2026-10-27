#if UNITY_EDITOR
using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad] public static class GatewayApprovedRecipeChecks
{
    static GatewayApprovedRecipeChecks(){EditorApplication.update+=Tick;}
    static void Check(bool condition,string why){if(!condition)throw new Exception(why);}
    static void Reject(Action action){try{action();}catch(ArgumentException){return;}catch(InvalidOperationException){return;}throw new Exception("Invalid approval was accepted");}
    static void Tick()
    {
        if(!File.Exists("GatewayApprovedRecipeCheck.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("GatewayApprovedRecipeCheck.once");
        try{Run();File.WriteAllText("GatewayApprovedRecipeCheck.result","APPROVED_RECIPE_CORE_OK\nADMIN_PASSWORD_GATE_OK\nPENDING_ELECTRICAL_GATE_OK\nSERVER_SPEC_VERDICT_FAKE_GUARD_OK\n"+DateTime.UtcNow.ToString("O")+"\nApproval-only / run, lot, proposal and candidate matching / missing and nonfinite values rejected / um to nm / busy deferral / original readings and quality limits unchanged / duplicate idempotency and conflicting decision rejected / local fixture only, no Gateway approval sent");}
        catch(Exception e){File.WriteAllText("GatewayApprovedRecipeCheck.result","FAILED\n"+e);Debug.LogException(e);}
    }
    [MenuItem("MOSFET/Gateway/Test approved recipe core (offline)")]
    public static void Run()
    {
        ProtocolChecks();
        AdminChecks();
        PendingElectricalChecks();
        var root=new GameObject("Approval offline check"){hideFlags=HideFlags.HideAndDontSave};root.SetActive(false);
        try
        {
            var ion=root.AddComponent<IonImplantCycle>();var ox=root.AddComponent<IntegratedOxidationCycle>();var service=root.AddComponent<GatewayApprovedRecipe>();service.Bind(ion,ox);
            var spec=ScriptableObject.CreateInstance<FilmInspectionRecipe>();var limits=new[]{spec.lowerNm,spec.upperNm};
            ion.dose=8.2e12f;ion.progress=1;ion.completed=true;ox.completed=true;
            var a=new GatewayApprovedRecipe.Approval{proposal_id=Guid.NewGuid().ToString(),run_id=Guid.NewGuid().ToString(),lot_id="SIM-LOT-RECIPE-TEST",selected_tcad_request_id=Guid.NewGuid().ToString(),decision="approved",decided_by="offline-test",process_parameters=new GatewayFullCycleProtocol.Parameters{body_dose=7.01e12,epi_doping=1.7e16,oxide_thickness=.06375}};
            void Validate()=>GatewayApprovedRecipe.Validate(a,a.run_id,a.lot_id,a.proposal_id,a.selected_tcad_request_id);
            a.decision="rejected";Reject(Validate);a.decision="approved";
            Reject(()=>GatewayApprovedRecipe.Validate(a,Guid.NewGuid().ToString(),a.lot_id,a.proposal_id,a.selected_tcad_request_id));
            Reject(()=>GatewayApprovedRecipe.Validate(a,a.run_id,"other-lot",a.proposal_id,a.selected_tcad_request_id));
            a.process_parameters.body_dose=double.NaN;Reject(Validate);a.process_parameters.body_dose=7.01e12;
            var running=typeof(IonImplantCycle).GetField("running",BindingFlags.NonPublic|BindingFlags.Instance);running.SetValue(ion,true);
            float before=ion.targetDose;Check(service.Stage(a,a.run_id,a.lot_id,a.proposal_id,a.selected_tcad_request_id),"Did not stage");
            Check(service.Pending!=null&&service.Applied==null&&ion.targetDose==before,"Busy equipment changed");
            a.process_parameters.body_dose=9e12;running.SetValue(ion,false);Check(service.ApplyIfIdle(),"Idle application failed");
            Check(Math.Abs(ion.targetDose-7.01e12)/7.01e12<1e-6&&Math.Abs(ox.targetOxideNm-63.75)<.001,"Units or immutable pending copy incorrect");
            Check(ion.dose==8.2e12f&&ion.progress==1&&ion.completed&&ox.completed&&spec.lowerNm==limits[0]&&spec.upperNm==limits[1],"Historical measurement or specification changed");
            Check(!service.Stage(a,a.run_id,a.lot_id,a.proposal_id,a.selected_tcad_request_id),"Duplicate approval applied twice");
            a.selected_tcad_request_id=Guid.NewGuid().ToString();Reject(()=>service.Stage(a,a.run_id,a.lot_id,a.proposal_id,a.selected_tcad_request_id));
            UnityEngine.Object.DestroyImmediate(spec);
        }
        finally{UnityEngine.Object.DestroyImmediate(root);}
    }
    static void PendingElectricalChecks()
    {
        foreach(bool equipmentOk in new[]{true,false})foreach(bool predictionOk in new[]{true,false})
        {
            var s=new GatewayFullCycleProtocol.State(Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),"LOT-PENDING","UNIT-1",equipmentOk,false,false);
            Check(!s.NormalInspection&&!s.PendingDiagnosis,"Pending inspection completed before server result");
            s.Accept(GatewayFullCycleChecks.Prediction(s,predictionOk?2.260060537596672:2.9,4.599146017602794,5.207198932949856,41.11501514951402).ToString());
            bool normal=equipmentOk&&predictionOk;
            Check(s.NormalInspection==normal&&s.PendingDiagnosis!=normal,"Missing original electrical result treated as NG");
            if(normal){Check(s.DiagnosisId==null&&!s.InspectionNg,"Normal request generated diagnosis or quality HOLD");Reject(()=>s.DiagnosisJson());}
        }
        var knownNg=new GatewayFullCycleProtocol.State(Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),"LOT-KNOWN-NG","UNIT-1",true,false,true);
        knownNg.Accept(GatewayFullCycleChecks.Prediction(knownNg,2.26,4.599,5.207,41.115).ToString());
        Check(knownNg.PendingDiagnosis&&knownNg.InspectionNg&&!knownNg.NormalInspection,"Confirmed original NG was skipped");
        var job=new GatewayInspectionBridge.Job{request=new GatewayInspectionProtocol.Request{run_id=Guid.NewGuid().ToString(),request_id=Guid.NewGuid().ToString(),lot_id="LOT-PENDING",unit_id="UNIT-1"}};
        typeof(GatewayInspectionBridge).GetMethod("StartFullCycle",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{job,true,false,false});
        job.cycle.Accept(GatewayFullCycleChecks.Prediction(job.cycle,2.26,4.599,5.207,41.115).ToString());
        Check(job.cycle.NormalInspection&&!job.cycle.PendingDiagnosis,"Bridge lost original electrical availability flag");
    }
    static void AdminChecks()
    {
        var gate=new GatewayTcadApprovalView.AdminGate();
        Check(!gate.Consume("candidate-A"),"Approval allowed without authentication");
        foreach(string wrong in new[]{null,"","0000","12345"," 1234"})Check(!gate.Authorize(wrong,"candidate-A")&&!gate.Consume("candidate-A"),"Wrong password approved");
        Check(gate.Authorize("1234","candidate-A")&&gate.Consume("candidate-A"),"Configured password rejected");
        Check(!gate.Consume("candidate-A"),"Password confirmation reused");
        gate.Authorize("1234","candidate-A");Check(!gate.Consume("candidate-B")&&!gate.Consume("candidate-A"),"Authentication transferred to another candidate");
        gate.Authorize("1234","candidate-A");gate.Clear();Check(!gate.Consume("candidate-A"),"Cancel kept authorization");
        gate.Authorize("1234","candidate-A");Check(!gate.Authorize("wrong","candidate-A")&&!gate.Consume("candidate-A"),"Failure retained prior authorization");
        Check(!gate.Authorize("1234",null),"Unbound authorization allowed");
    }
    static void ProtocolChecks()
    {
        var s=new GatewayFullCycleProtocol.State(Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),"LOT-APPROVAL","UNIT-1",false,true);
        s.Accept(GatewayFullCycleChecks.Prediction(s,2.9,3.7,3.4,44.2).ToString());
        Check(!s.DiagnosisJson().Contains("\"task_type\""),"Gateway rejects extra task_type");
        s.Accept(GatewayFullCycleChecks.Diagnosis(s,"tcad_verify").ToString());
        var c=new GatewayTcadApprovalProtocol.Candidate{tcad_request_id=Guid.NewGuid().ToString(),candidate_index=0,
            process_parameters=new GatewayFullCycleProtocol.Parameters{body_dose=7.01e12,epi_doping=1.7e16,oxide_thickness=.06375},
            result_payload=new GatewayTcadApprovalProtocol.Outputs{vth=2.15,bv=42.6,gm=4.5,id_on=5.2},spec_verdict=new GatewayTcadApprovalProtocol.Verdict{overall="in_spec"}};
        var p=new GatewayTcadApprovalProtocol.Proposal{proposal_id=Guid.NewGuid().ToString(),job_id=s.DiagnosisJob,run_id=s.Run,status="review_required",candidates=new[]{c}};
        string list=JsonUtility.ToJson(new GatewayTcadApprovalProtocol.ListResponse{proposals=new[]{p}});
        Check(GatewayTcadApprovalProtocol.ReadList(list).proposals[0].candidates.Length==1,"GET list contract");
        string response=JsonUtility.ToJson(new GatewayTcadApprovalProtocol.DecisionResponse{proposal_id=p.proposal_id,status="approved",process_parameters=c.process_parameters});
        var receipt=GatewayTcadApprovalProtocol.Confirm(response,p,c,s.Run,s.Lot,"offline-operator");
        c.result_payload.vth=99;c.result_payload.bv=1;
        Check(GatewayTcadApprovalProtocol.Eligible(c),"Unity recalculated server in_spec verdict");
        c.result_payload.vth=2.15;c.result_payload.bv=42.6;
        s.ObserveApprovalContext(JsonUtility.ToJson(new GatewayFullCycleProtocol.Event{run_id=s.Run,unity_mode="mock",approval_allowed=true}));
        Check(s.TestTcad&&!s.RealApplicationAllowed,"Mock response enabled actual application");
        s.ObserveApprovalContext(JsonUtility.ToJson(new GatewayFullCycleProtocol.Event{run_id=s.Run,unity_mode="real",approval_allowed=false}));
        Check(!s.RealApplicationAllowed,"Server application denial ignored");
        s.ObserveApprovalContext(JsonUtility.ToJson(new GatewayFullCycleProtocol.Event{run_id=s.Run,unity_mode="real",approval_allowed=true}));
        Check(s.RealApplicationAllowed,"Explicit real and permitted context rejected");
        string fake=Guid.NewGuid().ToString();s.Candidates[fake]=new GatewayFullCycleProtocol.EventPayload{metadata=new GatewayFullCycleProtocol.Metadata{calc_mode="fake"}};
        Check(!s.RealApplicationAllowed,"Fake TCAD candidate bypassed protection");s.Candidates.Remove(fake);
        Check(receipt.process_parameters.oxide_thickness==.06375&&receipt.selected_tcad_request_id==c.tcad_request_id,"POST identity or units");
        Reject(()=>GatewayTcadApprovalProtocol.Confirm(response,p,c,Guid.NewGuid().ToString(),s.Lot,"offline"));
        c.spec_verdict.overall="bv_unconfirmed";Check(!GatewayTcadApprovalProtocol.Eligible(c),"Unconfirmed BV eligible");
        Reject(()=>GatewayTcadApprovalProtocol.Confirm(response,p,c,s.Run,s.Lot,"offline"));
        c.spec_verdict.overall="out_of_spec";Check(!GatewayTcadApprovalProtocol.Eligible(c),"NG eligible");c.spec_verdict.overall="in_spec";
        var unavailable=new GatewayTcadApprovalProtocol.Candidate{tcad_request_id=Guid.NewGuid().ToString(),candidate_index=1,spec_verdict=new GatewayTcadApprovalProtocol.Verdict{overall="bv_unconfirmed"}};
        p.candidates=new[]{unavailable,c};
        var sorted=GatewayTcadApprovalProtocol.ReadList(JsonUtility.ToJson(new GatewayTcadApprovalProtocol.ListResponse{proposals=new[]{p}})).proposals[0];
        Check(sorted.candidates[0].tcad_request_id==c.tcad_request_id,"Normal candidate was not offered first");
        c.spec_verdict.overall="out_of_spec";
        Check(!Array.Exists(p.candidates,GatewayTcadApprovalProtocol.Eligible),"All unavailable group allowed approval");c.spec_verdict.overall="in_spec";
        c.process_parameters.oxide_thickness=45.2;
        Reject(()=>GatewayTcadApprovalProtocol.Confirm(response,p,c,s.Run,s.Lot,"offline"));
        Check(c.process_parameters.oxide_thickness*1000==45200,"Example um incorrectly inferred as nm");
        Check(!GatewayTcadApprovalProtocol.Body("offline",null,false).Contains("selected_tcad_request_id"),"Reject included candidate");
        Check(GatewayTcadApprovalProtocol.Body("offline",c.tcad_request_id,true).Contains(c.tcad_request_id),"Approval selection missing");
        var address=GatewayTcadApprovalProtocol.Address("ws://127.0.0.1:8111/api/v1/stream","/"+p.proposal_id+"/decision");
        Check(address.Scheme=="http"&&address.Port==8111&&address.AbsolutePath.EndsWith("/decision"),"REST address");
        s.ObserveReview(p.proposal_id);Check(s.Done&&s.KeepSubscription&&!s.DecisionReceived,"Review closed stream before human decision");
        s.ObserveDecision(p.proposal_id,"approved");Check(!s.KeepSubscription&&s.DecisionReceived,"Decision did not complete review");
        s.ObserveDecision(p.proposal_id,"approved");Reject(()=>s.ObserveDecision(p.proposal_id,"rejected"));
    }
}
#endif
