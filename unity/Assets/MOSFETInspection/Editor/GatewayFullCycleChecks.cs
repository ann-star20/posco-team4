#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEngine;
using Unity.Plastic.Newtonsoft.Json.Linq;

[InitializeOnLoad]
public static class GatewayFullCycleChecks
{
    static GatewayFullCycleChecks(){EditorApplication.update+=Tick;}
    static void Require(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Tick()
    {
        if(!File.Exists("GatewayFullCycleCheck.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("GatewayFullCycleCheck.once");
        try{Run();File.WriteAllText("GatewayFullCycleCheck.result","FULL_CYCLE_UNITY_JSON_OK\n"+DateTime.UtcNow.ToString("O")+"\nActual Unity JsonUtility / prediction -> diagnosis -> route -> TCAD batch / original NG gate / micro units / no auto apply / no server requests");new GatewayFullCycleSocketCheck();}
        catch(Exception e){File.WriteAllText("GatewayFullCycleCheck.result","FAILED: "+e);Debug.LogException(e);}
    }
    public static JObject Prediction(GatewayFullCycleProtocol.State s,double vth,double gm,double id,double bv)
    {
        return new JObject{["sequence"]=1,["event_id"]=Guid.NewGuid().ToString(),["run_id"]=s.Run,["event_type"]="surrogate.completed",
            ["payload"]=new JObject{["request_id"]=s.PredictionId,["job_id"]=Guid.NewGuid().ToString(),["response"]=new JObject{
                ["status"]="succeeded",["result_origin"]="prod",["result_payload"]=new JObject{["vth"]=vth,["gm"]=gm,["id_on"]=id,["bv"]=bv},
                ["metadata"]=new JObject{["units"]=new JObject{["vth"]="V",["gm"]="uS/um",["id_on"]="uA/um",["bv"]="V"}}}}};
    }
    public static JObject Diagnosis(GatewayFullCycleProtocol.State s,string route)
    {
        return new JObject{["sequence"]=2,["event_id"]=Guid.NewGuid().ToString(),["run_id"]=s.Run,["event_type"]="diagnosis.completed",
            ["payload"]=new JObject{["request_id"]=s.DiagnosisId,["job_id"]=Guid.NewGuid().ToString(),["response"]=new JObject{
                ["status"]="succeeded",["result_origin"]="prod",["result_payload"]=new JObject{
                    ["decision"]=new JObject{["top_category"]="oxide",["decided"]=true,["top_probability"]=.95},
                    ["compensation"]=new JObject{["route"]=route,["target_process_parameters"]=new JObject{["body_dose"]=7.7e12,["epi_doping"]=1.7e16,["oxide_thickness"]=.06}}}}}};
    }
    [MenuItem("MOSFET/Gateway/Check full cycle (offline)")]
    public static void Run()
    {
        foreach(bool equipmentOk in new[]{true,false})foreach(bool originalOk in new[]{true,false})
        {
            var s=new GatewayFullCycleProtocol.State(Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),"LOT-TEST","W-1",equipmentOk,originalOk);
            Require(s.Accept(Prediction(s,2.2,4.5,5.2,41.1).ToString()),"Prediction not accepted");
            if(equipmentOk&&originalOk){Require(s.Done&&!s.PendingDiagnosis,"Normal did not skip diagnosis");continue;}
            var body=JObject.Parse(s.DiagnosisJson());
            Require((double)body["input_payload"]["measurements"]["gm"]==4.5&&body["task_type"]==null,"Gateway units/schema");
            Require((string)body["run_id"]==s.Run&&(string)body["request_id"]!=s.PredictionId,"Same RUN/new request");
            Require(s.Accept(Diagnosis(s,"tcad_verify").ToString())&&s.WaitingTcad&&!s.Done,"TCAD wait premature completion");
            var proposal=Guid.NewGuid().ToString();var candidate=Guid.NewGuid().ToString();
            JObject E(long sequence,string type,JObject payload)=>new JObject{["sequence"]=sequence,["event_id"]=Guid.NewGuid().ToString(),["run_id"]=s.Run,["event_type"]=type,["payload"]=payload};
            var p=new JObject{["request_id"]=s.DiagnosisId,["job_id"]=s.DiagnosisJob,["proposal_id"]=proposal,["tcad_request_id"]=candidate,["candidate_index"]=0,["status"]="succeeded",
                ["result_payload"]=new JObject{["vth"]=2.4,["gm"]=4.5,["id_on"]=5.2,["bv"]=42.0}};
            s.Accept(E(3,"tcad.verification.candidate_succeeded",p).ToString());
            Require(!s.Done&&s.Candidates[candidate].result_payload.hasBv,"Single candidate mistaken for batch");
            s.Accept(E(4,"tcad.verification.batch_completed",new JObject{["request_id"]=s.DiagnosisId,["job_id"]=s.DiagnosisJob,["proposal_id"]=proposal}).ToString());
            Require(s.Done&&s.BatchReceived,"Batch not complete");
        }
        foreach(string route in new[]{"apply","no_action","manual"})
        {
            var s=new GatewayFullCycleProtocol.State(Guid.NewGuid().ToString(),Guid.NewGuid().ToString(),"LOT-T","W-1",false,true);
            s.Accept(Prediction(s,2.2,4.5,5.2,41.1).ToString());s.DiagnosisJson();s.Accept(Diagnosis(s,route).ToString());
            Require(s.Done&&!s.WaitingTcad&&s.Candidates.Count==0,"Non-TCAD route queued a candidate");
        }
        Debug.Log("FULL_CYCLE_UNITY_JSON_OK (offline)");
    }
}
#endif
