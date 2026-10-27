#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Unity.Plastic.Newtonsoft.Json.Linq;

[InitializeOnLoad]
public static class IonGatewayChecks
{
    static IonGatewayChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Reject(Action action,string message){bool rejected=false;try{action();}catch(ArgumentException){rejected=true;}Check(rejected,message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode||!File.Exists("IonGatewayCheck.once"))return;
        File.Delete("IonGatewayCheck.once");
        try{Run();}catch(Exception e){File.WriteAllText("IonGatewayCheck.result",e.ToString());Debug.LogException(e);}
    }
    public static void Run()
    {
        var data=JsonUtility.FromJson<JetsonTestDataProtocol.Dataset>(File.ReadAllText("Temp/ion-dataset-offline.json"));
        var selected=new JetsonTestDataProtocol.Selection{row=data.rows[0].Snapshot(),measurement_source="TCAD",dataset_sha256=data.dataset_sha256,n_wafers=1};
        var csvSnapshot=new IonGatewayProtocol.Snapshot{inspection_id="CSV-TEST",lot_id="LOT-001",unit_id="WAFER-CSV",csv_sample_id=selected.row.id,csv_sha256=selected.dataset_sha256};
        var csvRequest=IonGatewayProtocol.DiagnoseCsv(csvSnapshot,selected,Guid.NewGuid().ToString(),Guid.NewGuid().ToString());
        var m=csvRequest.input_payload.measurements;
        Check(Math.Abs(m.gm-selected.row.tcad.gm*1e6)<1e-9&&Math.Abs(m.id_on-selected.row.tcad.id4v*1e6)<1e-9,"CSV SI-to-micro conversion missing or repeated");
        Check(m.vth==selected.row.tcad.vth&&m.bv==selected.row.tcad.bv,"CSV TCAD values replaced by PC/surrogate");
        Check(csvRequest.type=="diagnosis.requested"&&csvRequest.input_payload.provenance.electrical_source=="tcad_csv_not_measurement","CSV not sent directly as diagnosis");
        Check(csvRequest.input_payload.provenance.sample_id==selected.row.id,"CSV row provenance missing");
        var direct=JsonUtility.FromJson<ProcessAnalysisView.Payload>(JObject.Parse(File.ReadAllText("Tools/FabSocket/process_computed_fixture.json"))["payload"].ToString());
        direct.input=ProcessAnalysisView.NewInput(csvSnapshot.lot_id,direct.baseline_version,1,new ProcessAnalysisView.Measurement{vth=selected.row.tcad.vth,gm=selected.row.tcad.gm,id4v=selected.row.tcad.id4v,bv=selected.row.tcad.bv});
        direct.request_id=direct.input.request_id;direct.lot_id=csvSnapshot.lot_id;direct.delivery="computed";
        IonGatewayProtocol.AttachDirectDiagnosis(csvRequest,direct);
        Check(csvRequest.input_payload.provenance.direct_diagnosis.request_id==direct.request_id,"Direct result not preserved for Gateway storage");
        csvSnapshot.dose_cm2=7.7e12;csvSnapshot.completed_at=DateTimeOffset.UtcNow.ToString("O");
        var ionParent=new GatewayInspectionBridge.Job{ion=csvSnapshot,inspectionId=csvSnapshot.inspection_id,diagnosisRequest=csvRequest,
            request=new GatewayInspectionProtocol.Request{request_id=csvRequest.request_id,run_id=csvRequest.run_id,lot_id=csvRequest.lot_id,unit_id=csvRequest.unit_id},condition=GatewayLotConditions.ForLot("LOT-001")};
        var ionCandidate=GatewayTcadProtocol.BuildIon(ionParent,direct);
        Check(ionCandidate.type=="surrogate.requested"&&ionCandidate.stage_id=="tcad_candidate_prediction","Ion candidate does not use film Gateway request type/stage");
        var cp=ionCandidate.input_payload.process_parameters;
        Check(Math.Abs(cp.body_dose/(7.7e12*direct.estimated_dose*direct.dose_factor)-1)<1e-12&&cp.epi_doping==1.7e16*direct.estimated_epi&&
            Math.Abs(cp.oxide_thickness/(.06*direct.estimated_oxide*direct.oxide_factor)-1)<1e-12,"Candidate scaled CSV truth or wrong units instead of posterior state");
        var context=ionCandidate.input_payload.provenance.tcad;
        Check(context.legacy_top_cause_ko==direct.top_cause&&context.direct_diagnosis.request_id==direct.request_id&&context.exploratory_only&&!context.approved&&!context.applied,"Cause or review boundaries lost");
        Check(ionCandidate.run_id==csvRequest.run_id&&ionCandidate.input_payload.provenance.sample_id==selected.row.id,"Candidate lost inspection/run/CSV association");
        direct.dose_factor=.1f;Reject(()=>GatewayTcadProtocol.BuildIon(ionParent,direct),"Invalid correction factor accepted");direct.dose_factor=context.direct_diagnosis.dose_factor;
        direct.input.measurement.gm=1;Reject(()=>IonGatewayProtocol.AttachDirectDiagnosis(csvRequest,direct),"Wrong-unit/different CSV result archived");
        selected.row.tcad.gm=99;Check(m.gm<10,"Frozen diagnosis mutated with CSV selection");
        selected.measurement_source="PC";Reject(()=>IonGatewayProtocol.DiagnoseCsv(csvSnapshot,selected,Guid.NewGuid().ToString(),Guid.NewGuid().ToString()),"PC values accepted in TCAD-only diagnosis");
        selected.measurement_source="TCAD";selected.row.has_tcad=false;
        Reject(()=>IonGatewayProtocol.DiagnoseCsv(csvSnapshot,selected,Guid.NewGuid().ToString(),Guid.NewGuid().ToString()),"Missing TCAD silently became zero");
        var snapshot=new IonGatewayProtocol.Snapshot{inspection_id="TEST-IMP-001",lot_id="LOT-TEST",unit_id="WAFER-TEST",dose_cm2=7.6e12,
            target_cm2=7.7e12,lower_cm2=7.315e12,upper_cm2=8.085e12,epi_doping=1.7e16,oxide_thickness_um=.06,condition_source="test-only TCAD reference"};
        var request=IonGatewayProtocol.Build(snapshot);var parameters=request.input_payload.process_parameters;
        Check(parameters.body_dose==7.6e12&&parameters.body_dose!=snapshot.target_cm2,"Target substituted for completed dose");
        Check(parameters.epi_doping==1.7e16&&parameters.oxide_thickness==.06,"LOT context or um units corrupted");
        Check(request.input_payload.provenance.data_source=="simulation"&&request.input_payload.provenance.equipment_id=="IMP-01","Simulation origin lost");
        snapshot.dose_cm2=1;Check(parameters.body_dose==7.6e12,"Frozen request mutated");
        var parent=new GatewayInspectionBridge.Job{kind="ion_surrogate",ion=snapshot,request=request,inspectionId=snapshot.inspection_id,origin="prod",hasIdOn=true,
            result=new GatewayStreamClient.Result{vth=2.874,gm=3.767,id_on=3.468,bv=44.186,vth_present=true,gm_present=true,bv_present=true},
            units=new GatewayStreamClient.OutputUnits{vth="V",gm="uS/um",id_on="uA/um",bv="V"}};
        var diagnosis=IonGatewayProtocol.Diagnose(parent);
        Check(diagnosis.run_id==request.run_id&&diagnosis.request_id!=request.request_id&&Guid.TryParse(diagnosis.request_id,out _),"Diagnosis lost run identity or reused request ID");
        Check(diagnosis.input_payload.measurements.gm==3.767&&diagnosis.input_payload.measurements.id_on==3.468&&diagnosis.input_payload.n_wafers==1&&!diagnosis.input_payload.refine,"Micro units or wafer count changed");
        var wire=JObject.Parse(JsonUtility.ToJson(diagnosis));
        var worker=AsyncTcadContract.BuildWorkerRequest(wire,Guid.NewGuid().ToString());
        Check((string)worker["task_type"]=="diagnosis"&&!wire.ContainsKey("task_type"),"Gateway/service envelope boundary changed");
        Check(!wire.ToString().Contains("csv_dose_ratio")&&!wire.ToString().Contains("api_token"),"CSV truth or credentials leaked");
        parent.origin="mock";Reject(()=>IonGatewayProtocol.Diagnose(parent),"MOCK accepted");parent.origin="prod";
        parent.hasIdOn=false;Reject(()=>IonGatewayProtocol.Diagnose(parent),"Legacy id accepted as id_on");parent.hasIdOn=true;
        parent.units.gm="A/V/um";Reject(()=>IonGatewayProtocol.Diagnose(parent),"Wrong gm units accepted");parent.units.gm="uS/um";
        parent.result.bv_present=false;Reject(()=>IonGatewayProtocol.Diagnose(parent),"Missing BV became zero");parent.result.bv_present=true;
        var child=new GatewayInspectionBridge.Job{kind="ion_diagnosis",ion=snapshot,inspectionId=snapshot.inspection_id,diagnosisRequest=diagnosis,
            request=new GatewayInspectionProtocol.Request{type=diagnosis.type,request_id=diagnosis.request_id,run_id=diagnosis.run_id,lot_id=diagnosis.lot_id,unit_id=diagnosis.unit_id}};
        Check(JObject.Parse(GatewayInspectionBridge.RequestJson(child))["input_payload"]?["measurements"]!=null,"Bridge sent surrogate DTO for diagnosis");
        string job=Guid.NewGuid().ToString();
        var body=new JObject{["sequence"]=1,["event_id"]=Guid.NewGuid().ToString(),["run_id"]=diagnosis.run_id,["event_type"]="diagnosis.completed",
            ["payload"]=new JObject{["request_id"]=diagnosis.request_id,["job_id"]=job,["lot_id"]=diagnosis.lot_id,["unit_id"]=diagnosis.unit_id,
            ["response"]=new JObject{["status"]="succeeded",["result_origin"]="prod",["request_id"]=diagnosis.request_id,["job_id"]=job,
            ["result_payload"]=new JObject{["decision"]=new JObject{["top_category"]="oxide",["top_probability"]=.95,["decided"]=true},
                ["compensation"]=new JObject{["route"]="tcad_verify",["target_process_parameters"]=new JObject{["body_dose"]=7.01e12,["epi_doping"]=1.7e16,["oxide_thickness"]=.06375}}},
            ["tcad_proposal"]=new JObject{["candidates"]=new JArray(new JObject{["candidate_id"]="A"},new JObject{["candidate_id"]="B"})}}}};
        var e=GatewayStreamClient.Parse(body.ToString(),diagnosis.run_id);var result=IonGatewayProtocol.ReadDiagnosis(child,e);
        Check(result.result_payload.compensation.target_process_parameters.body_dose==7.01e12&&result.result_payload.decision.top_category=="oxide","Cause or correction lost");
        Check(JObject.Parse(e.rawJson)["payload"]?["response"]?["tcad_proposal"]?["candidates"]?.Count()==2,"Multiple candidates lost from archived response");
        Check(IonGatewayProtocol.Describe(result).Contains("보정 후보"),"Correction display missing");
        e.payload.request_id=Guid.NewGuid().ToString();Reject(()=>IonGatewayProtocol.ReadDiagnosis(child,e),"Different inspection response accepted");
        e.payload.request_id=diagnosis.request_id;e.payload.lot_id="OTHER-LOT";Reject(()=>IonGatewayProtocol.ReadDiagnosis(child,e),"Different LOT accepted");
        parent.ion.lot_id="OTHER-LOT";Reject(()=>IonGatewayProtocol.Diagnose(parent),"Prediction paired with another LOT");parent.ion.lot_id=request.lot_id;
        snapshot.dose_cm2=double.NaN;Reject(()=>IonGatewayProtocol.Build(snapshot),"Nonfinite dose accepted");
        string livePath="Tools/Gateway/IonIntegration/surrogate.event.json";
        if(File.Exists(livePath))
        {
            var liveRequest=JsonUtility.FromJson<GatewayInspectionProtocol.Request>(File.ReadAllText("Tools/Gateway/IonIntegration/surrogate.request.json"));
            var live=GatewayStreamClient.Parse(File.ReadAllText(livePath),liveRequest.run_id);var response=live.payload.response;
            Check(GatewayInspectionProtocol.Matches(liveRequest,live),"Live Gateway event correlation failed");
            var liveParent=new GatewayInspectionBridge.Job{request=liveRequest,inspectionId=liveRequest.input_payload.provenance.inspection_id,
                ion=new IonGatewayProtocol.Snapshot{lot_id=liveRequest.lot_id,unit_id=liveRequest.unit_id,inspection_id=liveRequest.input_payload.provenance.inspection_id},
                result=response.result_payload,origin=response.result_origin,units=response.metadata.units,hasIdOn=live.hasIdOn};
            var next=IonGatewayProtocol.Diagnose(liveParent);
            Check(next.input_payload.measurements.gm==response.result_payload.gm&&next.input_payload.measurements.id_on==response.result_payload.id_on,"Live micro units changed");
        }
        Directory.CreateDirectory("Temp/IonGateway");
        string directLive="Tools/Gateway/IonDirectIntegration/direct.result.json";
        if(File.Exists(directLive))
        {
            var actual=JsonUtility.FromJson<ProcessAnalysisView.Payload>(JObject.Parse(File.ReadAllText(directLive))["payload"].ToString());
            var old=JObject.Parse(File.ReadAllText("Tools/Gateway/IonDirectIntegration/gateway.request.json"));
            var provenance=old["input_payload"]["provenance"];
            var row=data.rows.First(r=>r.id==(string)provenance["sample_id"]);
            var choice=new JetsonTestDataProtocol.Selection{row=row.Snapshot(),measurement_source="TCAD",dataset_sha256=data.dataset_sha256,n_wafers=1};
            var s=new IonGatewayProtocol.Snapshot{inspection_id=(string)provenance["inspection_id"],lot_id=actual.lot_id,unit_id=(string)old["unit_id"],
                csv_sample_id=row.id,csv_sha256=data.dataset_sha256,dose_cm2=JetsonTestDataProtocol.Dose(7.7e12,row),completed_at=DateTimeOffset.FromUnixTimeMilliseconds(actual.generated_at_ms).ToString("O")};
            var reference=GatewayLotConditions.ForLot("LOT-001");reference.lot_id=actual.lot_id;
            var d=IonGatewayProtocol.DiagnoseCsv(s,choice,Guid.NewGuid().ToString(),(string)old["run_id"]);
            var liveCandidate=GatewayTcadProtocol.BuildIon(new GatewayInspectionBridge.Job{ion=s,inspectionId=s.inspection_id,condition=reference,diagnosisRequest=d,
                request=new GatewayInspectionProtocol.Request{request_id=d.request_id,run_id=d.run_id,lot_id=d.lot_id,unit_id=d.unit_id}},actual);
            File.WriteAllText("Temp/IonGateway/ion-candidate-live.request.json",JsonUtility.ToJson(liveCandidate,true));
        }
        File.WriteAllText("Temp/IonGateway/surrogate.request.json",JsonUtility.ToJson(request,true));
        File.WriteAllText("Temp/IonGateway/diagnosis.request.json",GatewayInspectionBridge.RequestJson(child));
        File.WriteAllText("Temp/IonGateway/diagnosis.event.json",body.ToString());
        File.WriteAllText("IonGatewayCheck.result","ION_GATEWAY_CONTRACT_OK\nIon candidate uses same film surrogate.requested and tcad_candidate_prediction / posterior ratios times physical reference then correction / no CSV truth scaling / cause, full direct result and units preserved / normal-uncertain review flags / request-run-inspection correlation / wrong units and correction factors rejected / existing film and diagnosis contracts retained\nOffline contract checks only; real DB result replay is a separate check");
        Debug.Log("ION_GATEWAY_CONTRACT_OK");
    }
}
#endif
