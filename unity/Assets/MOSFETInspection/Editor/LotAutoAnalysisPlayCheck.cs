#if UNITY_EDITOR
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class LotAutoAnalysisPlayCheck
{
    const string Key="LOT_AUTO_ANALYSIS_PHASE",Mode="LOT_AUTO_ANALYSIS_JETSON";
    static Process server,worker;
    static ProcessAnalysisView view;
    static LotProcessAnalysis manager;
    static EllipsometerCycle film;
    static IonImplantCycle ion;
    static IntegratedOxidationCycle oxidation;
    static AoiWebSocketClient client;
    static bool jetson,canSort;
    static string originalUrl,firstInspection,missingInspection;
    static float dose,target;
    static double deadline,after;
    const string Lot="LOT-AUTO-OX-001";
    [Serializable] class Tokens {public string process_ai;}
    [Serializable] class Config {public Tokens tokens;}
    [Serializable] class WorkerConfig {public string url,token;}
    static LotAutoAnalysisPlayCheck(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static Process Python(string script,string args,bool stdin=false)
    {
        var p=new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"),"-u \""+Path.GetFullPath("Tools/FabSocket/"+script)+"\" "+args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,RedirectStandardInput=stdin};
        p.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";return Process.Start(p);
    }
    static void Stop(){foreach(var p in new[]{server,worker})if(p!=null){if(!p.HasExited)p.Kill();p.Dispose();}server=worker=null;}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase>=2&&!Application.isPlaying){Stop();SessionState.SetInt(Key,0);return;}
            if(phase==0)
            {
                string flag=File.Exists("LotAutoAnalysisFinal.once")?"LotAutoAnalysisFinal.once":File.Exists("LotAutoAnalysisJetson.once")?"LotAutoAnalysisJetson.once":"LotAutoAnalysisLocal.once";
                if(!File.Exists(flag))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                jetson=flag.Contains("Jetson")||flag.Contains("Final");SessionState.SetBool(Mode,jetson);File.Delete(flag);SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                jetson=SessionState.GetBool(Mode,false);view=ProcessAnalysisView.Instance;manager=LotProcessAnalysis.Instance;
                client=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();oxidation=UnityEngine.Object.FindAnyObjectByType<IntegratedOxidationCycle>();
                Check(view&&manager&&film&&client,"LOT analysis components missing");originalUrl=client.serverUrl;
                Check(Application.runInBackground,"Socket processing stops when Unity loses focus");film.transportControlled=false;film.lotId=ion.incomingLotId=oxidation.lotId=Lot;
                dose=ion.targetDose;target=film.recipe.targetNm;canSort=client.feed.CanSort;
                Check(manager.RequestsSent==0&&!film.Running,"Unexpected automatic process start");
                if(!jetson)
                {
                    var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();int port=((IPEndPoint)listener.LocalEndpoint).Port;listener.Stop();
                    server=Python("server.py","--port "+port);client.enabled=false;client.serverUrl="ws://127.0.0.1:"+port+"/fab";client.enabled=true;
                    worker=Python("process_worker.py","--root \""+Path.GetFullPath("Tools/JetsonML/VirtualFabML_a83130a42269")+"\" --config-stdin --basic-only",true);
                    var config=JsonUtility.FromJson<Config>(File.ReadAllText("Tools/FabSocket/server.local.json"));worker.StandardInput.WriteLine(JsonUtility.ToJson(new WorkerConfig{url=client.serverUrl,token=config.tokens.process_ai}));worker.StandardInput.Close();
                }
                File.WriteAllText("LotAutoAnalysis"+(jetson?"Jetson":"Local")+".status","Waiting for diagnostic worker");SessionState.SetInt(Key,2);
            }
            else if(phase==2&&view.CanRequest)
            {
                film.validationDelta=.25f;film.demoHold=film.demoLow=false;film.StartScan();firstInspection=film.InspectionId;
                deadline=EditorApplication.timeSinceStartup+250;SessionState.SetInt(Key,3);
            }
            else if(phase==3&&film.completed)
            {
                Check(film.verdict=="PASS"&&!film.lotHeld&&manager.RequestsSent==0,"PASS triggered diagnosis or HOLD");
                Check(manager.Latest(Lot).status==LotProcessAnalysis.Status.Pass,"PASS record missing");
                film.demoLow=true;film.StartScan();missingInspection=film.InspectionId;SessionState.SetInt(Key,4);
            }
            else if(phase==4&&film.completed)
            {
                Check(film.verdict=="FAIL"&&film.lotHeld&&!film.CanProceed,"FAIL failed to HOLD");
                Check(manager.Latest(Lot).status==LotProcessAnalysis.Status.WaitingData&&manager.RequestsSent==0,"Unpaired NG fabricated electrical data");
                film.demoLow=false;film.demoHold=true;film.StartScan();manager.Latest(Lot).gatewayManaged=true;SessionState.SetInt(Key,5);
            }
            else if(phase==5&&film.completed&&manager.Latest(Lot)?.result!=null)
            {
                var r=manager.Latest(Lot);var p=r.result;
                Check(r.status==LotProcessAnalysis.Status.Complete&&r.attempts==1&&manager.RequestsSent==1,"Gateway-managed inspection blocked or duplicated its separate diagnostic request");
                Check(r.inspectionId!=firstInspection&&r.inspectionId!=missingInspection&&p.lot_id==Lot&&p.request_id==r.requestId,"Inspection/LOT/request identity mismatch");
                Check(p.delivery=="computed"&&p.input.n_wafers==5&&Mathf.Abs(p.input.measurement.vth-manager.PairedScenario.measurement.vth)<.000001f,"Not a paired fresh electrical diagnosis");
                Check(jetson?p.mode=="gp_tabpfn":p.mode=="gp_only","Unexpected computation mode");
                Check(film.lotHeld&&!film.CanProceed&&!p.applied&&p.tcad_status=="not_run","Analysis bypassed HOLD/TCAD");
                film.EvaluateInspection();Check(manager.RequestsSent==1&&r.attempts==1,"Repeated evaluation duplicated the analysis");
                string before=LotProcessAnalysis.Summary(LotProcessAnalysis.Equipment.Oxidation,Lot);
                Check(view.Accept(File.ReadAllText("Tools/FabSocket/process_analysis_fixture.json")),"Replay fixture invalid");
                Check(LotProcessAnalysis.Summary(LotProcessAnalysis.Equipment.Oxidation,Lot)==before,"History selection contaminated equipment result");
                Check(LotProcessAnalysis.Summary(LotProcessAnalysis.Equipment.Implanter,"LOT-OTHER").Contains("분석 없음"),"Unrelated LOT received correction");
                ion.StartCycle();Check(!ion.Running&&ion.LotBlocked,"HOLD LOT entered implant");
                Check(ion.targetDose==dose&&film.recipe.targetNm==target&&client.feed.CanSort==canSort,"Recipe or AOI changed");
                view.OpenLot(Lot);manager.OpenMonitor(LotProcessAnalysis.Equipment.Oxidation,Lot);FactoryControlBar.Select(FactoryControlBar.Equipment.Oxidation);
                film.validationDelta=0;after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,6);
                File.AppendAllText("LotAutoAnalysis"+(jetson?"Jetson":"Local")+".status",$"\n{p.request_id} {p.lot_id} {p.mode} {p.decision} {p.duration_seconds:F2}s | oxide x{p.oxide_factor:F3}, dose x{p.dose_factor:F3}");
            }
            else if(phase==6&&EditorApplication.timeSinceStartup>after)
            {
                ScreenCapture.CaptureScreenshot("LotAutoAnalysis_"+(jetson?"Jetson":"Local")+"_Unity.png");
                after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,7);
            }
            else if(phase==7&&EditorApplication.timeSinceStartup>after)
            {
                File.WriteAllText("LotAutoAnalysis"+(jetson?"Jetson":"Local")+".result","LOT_AUTO_ANALYSIS_"+(jetson?"JETSON":"LOCAL")+"_PLAY_OK\nPASS: no request. Unpaired NG: HOLD/data waiting. Paired HIGH: one automatic fresh diagnosis.\nLOT/inspection correlation, history/other-LOT isolation, duplicate prevention, implant HOLD checked.\nNo TCAD, approval, recipe or AOI change.");
                SessionState.SetInt(Key,0);if(!jetson){client.enabled=false;client.serverUrl=originalUrl;Stop();EditorApplication.isPlaying=false;}
            }
            if(phase>=3&&phase<=5&&(film.failed||EditorApplication.timeSinceStartup>deadline))throw new Exception("LOT automatic test failed/timed out: "+film.status+" / "+manager.Latest(Lot)?.detail+" / "+view.LastError);
        }
        catch(Exception error){Stop();File.WriteAllText("LotAutoAnalysis"+(jetson?"Jetson":"Local")+".result",error.ToString());SessionState.SetInt(Key,0);if(client&&!jetson)client.serverUrl=originalUrl;EditorApplication.isPlaying=false;UnityEngine.Debug.LogException(error);}
    }
}
#endif
