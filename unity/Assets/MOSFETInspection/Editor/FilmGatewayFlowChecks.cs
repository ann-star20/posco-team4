#if UNITY_EDITOR
using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using Unity.Plastic.Newtonsoft.Json.Linq;

[InitializeOnLoad]
public static class FilmGatewayFlowChecks
{
    const string Key="FILM_GATEWAY_FLOW_CHECK";
    static FilmGatewayFlowChecks(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string why){if(!ok)throw new Exception(why);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(SessionState.GetInt(Key,0)==2)
        {
            if(EditorApplication.isPlayingOrWillChangePlaymode)return;
            EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Key+"Options",false);
            EditorSettings.enterPlayModeOptions=(EnterPlayModeOptions)SessionState.GetInt(Key+"Flags",0);
            SessionState.SetInt(Key,0);return;
        }
        if(SessionState.GetInt(Key,0)==0)
        {
            if(!File.Exists("FilmGatewayFlowCheck.once")||EditorApplication.isPlayingOrWillChangePlaymode)return;
            File.Delete("FilmGatewayFlowCheck.once");
            SessionState.SetBool(Key+"Options",EditorSettings.enterPlayModeOptionsEnabled);
            SessionState.SetInt(Key+"Flags",(int)EditorSettings.enterPlayModeOptions);
            EditorSettings.enterPlayModeOptionsEnabled=false;
            SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
        }
        if(!Application.isPlaying)return;
        var bridge=GatewayInspectionBridge.Instance;var manager=LotProcessAnalysis.Instance;var view=ProcessAnalysisView.Instance;
        var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();
        if(!bridge||!manager||!view||!film)return;
        var original=FilmInspectionHistory.Instance;
        try
        {
            manager.enabled=false;bridge.Disarm();bridge.enabled=false;bridge.EnsureSession();
            bridge.Token="offline-test-not-a-real-token";Check(bridge.Arm(),"Could not arm offline bridge");
            var socket=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();if(socket)socket.enabled=false;
            FilmInspectionHistory.UseTestStore(new FilmInspectionHistory("Temp/FilmGateway/"+Guid.NewGuid().ToString("N")+".json"));
            Directory.CreateDirectory("Temp/FilmGateway");
            var data=JsonUtility.FromJson<JetsonTestDataProtocol.Dataset>(File.ReadAllText("Temp/ion-dataset-offline.json"));
            var ids=new[]{"B001","B132","B081","B038"};
            for(int i=0;i<ids.Length;i++)
            {
                film.lotId="LOT-001";film.waferId="OFFLINE-FILM-"+ids[i];film.ResetDashboardDemo();
                Check(film.SetCsvTest(new JetsonTestDataProtocol.Selection{row=Array.Find(data.rows,r=>r.id==ids[i]).Snapshot(),
                    measurement_source="TCAD",dataset_sha256=data.dataset_sha256,n_wafers=1,reference_target_nm=60}),"CSV rejected");
                film.ResetPreview();bridge.Capture(film);film.readings=film.DemoReadings();film.EvaluateInspection();
                var r=manager.Latest(film.lotId);var job=System.Linq.Enumerable.First(bridge.Jobs,j=>j.inspectionId==film.InspectionId);
                Check(job.kind=="gateway_full_cycle"&&job.cycle!=null&&job.filmRecordRequest!=null,"Full cycle original film record not queued");
                var wire=JObject.Parse(GatewayInspectionBridge.RequestJson(job));
                Check(wire["input_payload"]?["provenance"]?["tcad"]==null,"Original record contains phantom candidate");
                var saved=job.filmRecordRequest.input_payload.provenance.inspection_result;
                Check(saved.thickness_points_nm.Length==3&&Math.Abs(saved.thickness_mean_nm-film.Mean)<.001&&saved.electrical.has_bv,"Original values missing");
                Check(Math.Abs(saved.electrical.gm_us_per_um-r.electrical.measurement.gm*1e6)<1e-5,"Micro conversion changed");
                Check(manager.RequestsSent==0&&r.attempts==0,"Test sent a real diagnosis");
                if(i==0)
                {
                    Check(r.status==LotProcessAnalysis.Status.Pass&&LotProcessAnalysis.IsNormal(r)&&!LotProcessAnalysis.NeedsDiagnosis(r),"Both OK queued diagnosis");
                    Check(saved.verdict=="OK"&&!saved.diagnosis_requested&&!saved.correction_candidate,"Normal record has diagnosis or bad verdict");
                    bool blocked=false;try{bridge.QueueTcadCandidate(r);}catch(ArgumentException){blocked=true;}Check(blocked,"Normal allowed manual candidate");
                    wire["lot_id"]="LOT-UNITY-FILM-NORMAL-TEST";
                    File.WriteAllText("Temp/FilmGateway/film-normal-live.request.json",wire.ToString());
                }
                else
                {
                    Check(r.status==LotProcessAnalysis.Status.Queued&&LotProcessAnalysis.NeedsDiagnosis(r)&&saved.verdict=="NG"&&saved.diagnosis_requested,"NG not queued");
                    Check((film.verdict=="FAIL")== (i==1||i==3),"Thickness case mismatch");
                    Check((r.electricalVerdict==ElectricalSpec.Verdict.NG)==(i==2||i==3),"Electrical case mismatch");
                    var m=r.electrical.measurement;
                    job.cycle.Accept(GatewayFullCycleChecks.Prediction(job.cycle,m.vth,m.gm*1e6,m.id4v*1e6,m.bv).ToString());
                    Check(job.cycle.PendingDiagnosis,"Either NG must request Gateway diagnosis");
                    var body=JObject.Parse(job.cycle.DiagnosisJson());
                    Check((string)body["run_id"]==job.request.run_id&&(double)body["input_payload"]["measurements"]["gm"]==job.cycle.Electrical.gm,"Diagnosis did not use same RUN/predicted micro units");
                    job.cycle.Accept(GatewayFullCycleChecks.Diagnosis(job.cycle,"tcad_verify").ToString());
                    Check(job.cycle.WaitingTcad&&job.directDiagnosis==null,"Gateway route/direct diagnosis duplicate");
                    int count=bridge.Jobs.Count;bool blocked=false;try{bridge.QueueTcadCandidate(r);}catch(ArgumentException){blocked=true;}
                    Check(blocked&&bridge.Jobs.Count==count,"Separate legacy candidate was queued");
                }
            }
            Check(bridge.Jobs.Count==4,"Unexpected duplicate full-cycle job count");
            File.WriteAllText("FilmGatewayFlowCheck.result","FILM_GATEWAY_FLOW_OK\nOriginal records preserved / equipment-only, electrical-only and combined NG use prediction -> Gateway diagnosis -> conditional TCAD / no direct worker or separate candidate request / same RUN and micro units / no phantom TCAD field\nOffline fixtures only; no server requests sent");
        }
        catch(Exception e){File.WriteAllText("FilmGatewayFlowCheck.result","FAILED: "+e);Debug.LogException(e);}
        finally
        {
            FilmInspectionHistory.UseTestStore(original);bridge.Disarm();
            foreach(var j in bridge.Jobs)File.Delete("Tools/Gateway/Requests/"+j.request.request_id+".json");
            SessionState.SetInt(Key,2);EditorApplication.isPlaying=false;
        }
    }
}
#endif
