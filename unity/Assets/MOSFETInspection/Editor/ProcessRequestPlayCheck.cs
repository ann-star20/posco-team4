#if UNITY_EDITOR
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using UnityEditor;
using UnityEngine;

[InitializeOnLoad]
public static class ProcessRequestPlayCheck
{
    const string Key="PROCESS_REQUEST_PHASE",Mode="PROCESS_REQUEST_JETSON";
    static Process server,worker;
    static ProcessAnalysisView view;
    static AoiWebSocketClient client;
    static bool jetson,held,canSort;
    static string originalUrl,lastRequest;
    static float dose,thickness;
    static double deadline,after;
    static int index,startCount;
    [Serializable] class Tokens {public string process_ai;}
    [Serializable] class Config {public Tokens tokens;}
    [Serializable] class WorkerConfig {public string url,token;}
    static ProcessRequestPlayCheck(){EditorApplication.update+=Tick;}
    static void Require(bool ok,string message){if(!ok)throw new Exception(message);}
    static Process Python(string file,string args,bool stdin=false)
    {
        string python=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe");
        var p=new ProcessStartInfo(python,"-u \""+Path.GetFullPath("Tools/FabSocket/"+file)+"\" "+args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,RedirectStandardInput=stdin};
        p.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";
        return Process.Start(p);
    }
    static void Stop()
    {
        foreach(var p in new[]{server,worker})if(p!=null){if(!p.HasExited)p.Kill();p.Dispose();}
        server=worker=null;
    }
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase>=2&&!Application.isPlaying){Stop();SessionState.SetInt(Key,0);return;}
            if(phase==0)
            {
                string flag=File.Exists("ProcessRequestJetson.once")?"ProcessRequestJetson.once":"ProcessRequestLocal.once";
                if(!File.Exists(flag))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                jetson=flag.Contains("Jetson");SessionState.SetBool(Mode,jetson);File.Delete(flag);SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                jetson=SessionState.GetBool(Mode,false);client=UnityEngine.Object.FindAnyObjectByType<AoiWebSocketClient>();view=ProcessAnalysisView.Instance;
                Require(client&&view,"Shared socket/view missing");originalUrl=client.serverUrl;
                var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();
                dose=ion.targetDose;thickness=film.recipe.targetNm;held=film.lotHeld;canSort=client.feed.CanSort;
                index=0;startCount=view.AcceptedCount;
                if(!jetson)
                {
                    var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();int port=((IPEndPoint)listener.LocalEndpoint).Port;listener.Stop();
                    server=Python("server.py","--port "+port);
                    client.enabled=false;client.serverUrl="ws://127.0.0.1:"+port+"/fab";client.enabled=true;
                    worker=Python("process_worker.py","--root \""+Path.GetFullPath("Tools/JetsonML/VirtualFabML_a83130a42269")+"\" --config-stdin --basic-only",true);
                    var config=JsonUtility.FromJson<Config>(File.ReadAllText("Tools/FabSocket/server.local.json"));
                    worker.StandardInput.WriteLine(JsonUtility.ToJson(new WorkerConfig{url=client.serverUrl,token=config.tokens.process_ai}));worker.StandardInput.Close();
                }
                SessionState.SetInt(Key,2);
                File.WriteAllText("ProcessRequest"+(jetson?"Jetson":"Local")+".status","Waiting for Unity connection and diagnostic worker heartbeat");
            }
            else if(phase==2&&view.CanRequest)
            {
                deadline=EditorApplication.timeSinceStartup+220;
                lastRequest=view.LastCompletedRequest;_=view.RequestSample(index);view.Open();
                FactoryControlBar.Select(FactoryControlBar.Equipment.Ellipsometer);SessionState.SetInt(Key,3);
            }
            else if(phase==3)
            {
                if(view.LastCompletedRequest!=lastRequest)
                {
                    var p=view.Current;
                    Require(p!=null&&p.delivery=="computed"&&p.data_source=="synthetic"&&p.input!=null,"Not a freshly computed correlated result");
                    Require(p.request_id==view.LastCompletedRequest&&p.lot_id==p.input.lot_id,"Wrong LOT/request association");
                    Require(p.tcad_status=="not_run"&&!p.applied,"Fabricated TCAD/application state");
                    Require(jetson?p.mode=="gp_tabpfn":p.mode=="gp_only","Unexpected compute mode");
                    Require(index==0?p.decision=="normal":index==3?p.top_cause=="에피"&&p.decided:!p.decided,"Unexpected synthetic case decision");
                    File.AppendAllText("ProcessRequest"+(jetson?"Jetson":"Local")+".status",$"\n{p.request_id} {p.lot_id} {p.mode} {p.decision} {p.duration_seconds:F2}s");
                    index++;SessionState.SetInt(Key,index==4?4:2);after=EditorApplication.timeSinceStartup+1;
                }
                else if(!view.RequestPending)throw new Exception("Request failed: "+view.RequestState+" "+view.LastError);
                else if(EditorApplication.timeSinceStartup>deadline)throw new Exception("New compute request timed out");
            }
            else if(phase==4&&EditorApplication.timeSinceStartup>after)
            {
                Require(view.AcceptedCount==startCount+4,"Unexpected result count");
                int count=view.AcceptedCount;
                Require(!view.Accept(File.ReadAllText("Tools/FabSocket/process_computed_fixture.json"))&&view.AcceptedCount==count,"Accepted unrelated/stale result");
                var ion=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();var film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();
                Require(ion.targetDose==dose&&film.recipe.targetNm==thickness&&film.lotHeld==held&&client.feed.CanSort==canSort,"Analysis changed process/AOI state");
                ScreenCapture.CaptureScreenshot("ProcessRequest_"+(jetson?"Jetson":"Local")+"_Unity.png");
                File.WriteAllText("ProcessRequest"+(jetson?"Jetson":"Local")+".result","PROCESS_REQUEST_"+(jetson?"JETSON":"LOCAL")+"_PLAY_OK\nFour fresh calculations requested from Unity; input/LOT/request correlation checked.\nStale result rejected. No TCAD, approval, recipe, HOLD or AOI changes.");
                SessionState.SetInt(Key,0);
                if(!jetson){client.enabled=false;client.serverUrl=originalUrl;Stop();EditorApplication.isPlaying=false;}
            }
        }
        catch(Exception error)
        {
            Stop();File.WriteAllText("ProcessRequest"+(jetson?"Jetson":"Local")+".result",error.ToString());
            SessionState.SetInt(Key,0);if(client&&!jetson)client.serverUrl=originalUrl;EditorApplication.isPlaying=false;UnityEngine.Debug.LogException(error);
        }
    }
}
#endif
