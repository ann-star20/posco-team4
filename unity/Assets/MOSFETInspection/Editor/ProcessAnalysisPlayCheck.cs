#if UNITY_EDITOR
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using UnityEditor;
using UnityEngine;
using Debug=UnityEngine.Debug;

[InitializeOnLoad]
public static class ProcessAnalysisPlayCheck
{
    const string Key="PROCESS_ANALYSIS_PHASE",Mode="PROCESS_ANALYSIS_REAL_JETSON";
    static Process server,publisher;
    static AoiWebSocketClient client;
    static ProcessAnalysisView view;
    static string originalUrl;
    static double deadline,after;
    static float dose,thickness;
    static bool held;
    static int port;
    static bool jetson;
    static ProcessAnalysisPlayCheck(){EditorApplication.update+=Tick;}
    static void Require(bool condition,string reason){if(!condition)throw new Exception(reason);}
    static Process Python(string script,string args)
    {
        string runtime=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe");
        var info=new ProcessStartInfo(runtime,"-u \""+Path.GetFullPath("Tools/FabSocket/"+script)+"\" "+args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,RedirectStandardOutput=true,RedirectStandardError=true};
        return Process.Start(info);
    }
    static void StopProcesses()
    {
        foreach(var process in new[]{server,publisher})if(process!=null){if(!process.HasExited)process.Kill();process.Dispose();}
        server=publisher=null;
    }
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                string flag=File.Exists("ProcessAnalysisJetson.once")?"ProcessAnalysisJetson.once":"ProcessAnalysisPlay.once";
                if(!File.Exists(flag))return;
                if(EditorApplication.isPlaying||EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                jetson=flag.Contains("Jetson");SessionState.SetBool(Mode,jetson);
                File.Delete(flag);SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                jetson=SessionState.GetBool(Mode,false);
                client=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();view=ProcessAnalysisView.Instance;
                Require(client&&view,"Analysis view or shared socket missing");
                var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();
                dose=ion.targetDose;thickness=film.recipe.targetNm;held=film.lotHeld;
                originalUrl=client.serverUrl;
                if(!jetson)
                {
                    var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();port=((IPEndPoint)listener.LocalEndpoint).Port;listener.Stop();
                    server=Python("server.py","--port "+port);
                    client.enabled=false;client.serverUrl="ws://127.0.0.1:"+port+"/fab";client.enabled=true;
                }
                deadline=EditorApplication.timeSinceStartup+(jetson?300:45);SessionState.SetInt(Key,2);
            }
            else if(phase==2&&client.Connected)
            {
                Require(view.AcceptedCount==0,"Stale analysis on first connection");
                if(!jetson)
                {
                    string root=Path.GetFullPath("Tools/JetsonML/");
                    publisher=Python("publish_process_results.py","--url ws://127.0.0.1:"+port+"/fab --root \""+root+"VirtualFabML_a83130a42269\" --config \""+root+"process-ai.local.json\" --result \""+root+"agent-high-precision-jetson-result.json\" --reference \""+root+"agent_reference.json\"");
                }
                SessionState.SetInt(Key,3);
            }
            else if(phase==3&&view.AcceptedCount>=4)
            {
                Require(view.History.Count==4,"Analysis history not preserved");
                var oxide=view.History.Find(p=>p.lot_id=="JETSON-TEST-oxide_plus15");
                var epi=view.History.Find(p=>p.lot_id=="JETSON-TEST-epi_minus40_with_bv");
                Require(oxide!=null&&!oxide.decided&&oxide.decision=="ambiguous"&&Mathf.Abs(oxide.oxide_factor-.88f)<.0001f,"Ambiguous oxide result altered");
                Require(epi!=null&&epi.decided&&epi.top_cause=="에피"&&epi.top_probability>.8f,"High precision epi result missing");
                foreach(var p in view.History)Require(p.data_source=="synthetic"&&p.delivery=="replay"&&!p.applied&&p.tcad_status=="not_run","Incorrect provenance or fabricated TCAD/application state");
                int accepted=view.AcceptedCount;
                string invalid=File.ReadAllText("Tools/FabSocket/process_analysis_fixture.json").Replace("\"applied\": false","\"applied\": true");
                Require(!view.Accept(invalid)&&view.AcceptedCount==accepted,"Unity accepted an applied/unsafe payload");
                var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();
                Require(ion.targetDose==dose&&film.recipe.targetNm==thickness&&film.lotHeld==held,"Analysis changed equipment recipes or HOLD state");
                Require(client.feed.current==null&&!client.feed.CanSort,"Process analysis incorrectly triggered AOI classification");
                view.SelectResult(view.History.IndexOf(oxide));view.Open();FactoryControlBar.Select(FactoryControlBar.Equipment.Ellipsometer);
                after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,4);
            }
            else if(phase==4&&EditorApplication.timeSinceStartup>after)
            {
                ScreenCapture.CaptureScreenshot(jetson?"ProcessAnalysis_Jetson_Unity.png":"ProcessAnalysis_Unity.png");
                string result="PROCESS_ANALYSIS_"+(jetson?"JETSON":"LOCAL")+"_PLAY_OK\nFour LOTs retained; high-precision final probabilities; ambiguous remains ambiguous; synthetic replay labelled.\nNo TCAD verification, recipe application, HOLD release, or AOI classification triggered.\n";
                File.WriteAllText(jetson?"ProcessAnalysisJetson.result":"ProcessAnalysisPlay.result",result);
                SessionState.SetInt(Key,0);
                if(!jetson){client.enabled=false;StopProcesses();client.serverUrl=originalUrl;EditorApplication.isPlaying=false;}
                return;
            }
            if(phase>=2&&EditorApplication.timeSinceStartup>deadline)throw new Exception("Process analysis timeout, phase="+phase+", count="+(view?view.AcceptedCount:0));
        }
        catch(Exception error)
        {
            StopProcesses();if(client&&!jetson)client.serverUrl=originalUrl;
            File.WriteAllText(jetson?"ProcessAnalysisJetson.result":"ProcessAnalysisPlay.result",error.ToString());Debug.LogException(error);
            SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;
        }
    }
}
#endif
