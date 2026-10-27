#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class GatewayTcadChecks
{
    static GatewayTcadChecks(){EditorApplication.update+=Tick;}
    static void Check(bool condition,string message){if(!condition)throw new Exception(message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode||!File.Exists("GatewayTcadCheck.once"))return;
        File.Delete("GatewayTcadCheck.once");
        try
        {
            var package=JsonUtility.FromJson<TcadVerificationPackage.Package>(File.ReadAllText("Tools/Gateway/fixtures/legacy-diagnostic-candidate.json"));
            var r=new LotProcessAnalysis.Record{lotId=package.lot_id,inspectionId=package.inspection_id,requestId=package.diagnosis.request_id,
                electrical=package.diagnosis.input,inspectionSnapshot=package.inspection,tcadCondition=package.model_reference,result=package.diagnosis};
            var request=GatewayTcadProtocol.Build(r);
            string wire=JsonUtility.ToJson(request,true);
            Check(Guid.TryParse(request.request_id,out _)&&Guid.TryParse(request.run_id,out _)&&request.stage_id=="tcad_candidate_prediction","Missing candidate UUID or stage");
            Check(!wire.Contains("dose_ratio")&&!wire.Contains("epi_ratio")&&!wire.Contains("oxide_ratio")&&!wire.Contains("B081"),"Simulation truth leaked into candidate model request");
            Check(!wire.Contains("api_token")&&!wire.Contains("X-Unity-Token")&&!wire.Contains("\"diagnosis\":"),"Credential or legacy response passed as canonical service diagnosis");
            Check(wire.Contains("separate_legacy_diagnostic_worker")&&wire.Contains("gp_tabpfn"),"Legacy diagnostic origin hidden");
            var p=request.input_payload.process_parameters;
            Check(Math.Abs(p.body_dose-package.candidate_after.body_dose)<1&&Math.Abs(p.oxide_thickness-package.candidate_after.oxide_thickness)<1e-9,"Candidate values changed");
            var setup=request.input_payload.provenance.tcad.tcad_setup;
            Check(setup.@fixed.diffusion_time_min==30&&setup.@fixed.diffusion_temp_c==1100&&setup.device_temperature_k==300&&setup.bias.vd_v==.1&&setup.bias.vg_sweep_v[1]==4&&setup.units.gm=="uS/um","TCAD setup differs from team contract");
            var job=new GatewayInspectionBridge.Job{request=request,inspectionId=r.inspectionId,jobId=Guid.NewGuid().ToString(),eventId=Guid.NewGuid().ToString(),sequence=1,origin="prod",hasIdOn=true,
                result=new GatewayStreamClient.Result{vth_present=true,gm_present=true,bv_present=true,vth=2.460,gm=4.529,id_on=4.578,bv=47.96}};
            var forward=GatewayTcadProtocol.Complete(job);
            Check(forward.spec.vth_max==2.6&&forward.predicted_outputs.vth==2.460&&!forward.approved&&!forward.tcad_executed&&forward.job_id==job.jobId,"Forward values or state incorrect");
            job.origin="mock";bool rejected=false;try{GatewayTcadProtocol.Complete(job);}catch(ArgumentException){rejected=true;}Check(rejected,"Mock candidate accepted");
            job.origin="prod";job.hasIdOn=false;rejected=false;try{GatewayTcadProtocol.Complete(job);}catch(ArgumentException){rejected=true;}Check(rejected,"Missing current accepted");
            File.WriteAllText("Tools/Gateway/tcad-candidate-check.request.json",wire);
            File.WriteAllText("GatewayTcadCheck.result","GATEWAY_TCAD_PROTOCOL_OK\nUUIDs / exact candidate / fixed TCAD setup / double spec / no CSV truth / explicit legacy diagnostic origin\nPredictions require matching DB event and prod outputs; mock/missing output rejected\nOffline only; live candidate submission is separate");
        }
        catch(Exception error){File.WriteAllText("GatewayTcadCheck.result",error.ToString());Debug.LogException(error);}
    }
}
#endif
