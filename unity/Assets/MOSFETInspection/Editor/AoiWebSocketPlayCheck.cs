#if UNITY_EDITOR
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using Debug=UnityEngine.Debug;

[InitializeOnLoad]
public static class AoiWebSocketPlayCheck
{
    const string Key="AOI_WS_PHASE";
    static AoiJetsonFeed feed;
    static AoiWebSocketClient client;
    static Process server,publisher;
    static int port;
    static double deadline,after;
    static string originalUrl;
    static bool retainedDuringSort;
    static AoiWebSocketPlayCheck(){EditorApplication.update+=Tick;}
    static void Check(bool value,string reason){if(!value)throw new Exception(reason);}
    static Process Python(string script,string arguments)
    {
        string runtime=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe");
        string path=Path.GetFullPath("Tools/FabSocket/"+script);
        var info=new ProcessStartInfo(runtime,"-u \""+path+"\" "+arguments){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,RedirectStandardOutput=true,RedirectStandardError=true};
        return Process.Start(info);
    }
    static void StartServer(){server=Python("server.py","--port "+port);}
    static void StopServer(){if(server!=null){if(!server.HasExited){server.Kill();server.WaitForExit(1000);}server.Dispose();server=null;}}
    static void Publish(string label)
    {if(publisher!=null){publisher.Dispose();publisher=null;}publisher=Python("send-aoi-test.py","--url ws://127.0.0.1:"+port+"/fab --label "+label);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                string request=File.Exists("AoiRetentionPlay.once")?"AoiRetentionPlay.once":"AoiWebSocketPlay.once";
                if(!File.Exists(request))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete(request);SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                feed=UnityEngine.Object.FindAnyObjectByType<AoiJetsonFeed>();client=feed.GetComponent<AoiWebSocketClient>();
                Check(client&&feed.useWebSocket&&!feed.demoMode,"WebSocket setup missing");
                originalUrl=client.serverUrl;client.enabled=false;retainedDuringSort=false;
                var socket=new TcpListener(IPAddress.Loopback,0);socket.Start();port=((IPEndPoint)socket.LocalEndpoint).Port;socket.Stop();
                StartServer();client.serverUrl="ws://127.0.0.1:"+port+"/fab";client.enabled=true;
                Application.runInBackground=true;Time.timeScale=6;deadline=EditorApplication.timeSinceStartup+100;
                foreach(var camera in Camera.allCameras)if(!camera.targetTexture)camera.enabled=false;feed.sorter.overview.enabled=true;
                feed.dashboard.ToggleWindow();SessionState.SetInt(Key,2);
            }
            else if(phase==2&&client.Connected)
            {
                Check(feed.current==null&&!feed.CanSort&&feed.transportReady,"Authenticated idle is not safe");
                Publish("scratch");SessionState.SetInt(Key,3);
            }
            else if(phase==3&&feed.current!=null)
            {
                Check(client.ReceivedResults==1&&feed.Verdict=="NG"&&feed.CanSort,"WebSocket scratch result not applied");
                Check(feed.current.data_source=="demo"&&feed.current.product_id=="WS-TEST-013"&&!feed.frame,"Test provenance/image state incorrect");
                Check(feed.dashboard.kind.text.Contains("scratch")&&feed.dashboard.confidence.text.Contains("96.8"),"AOI labels not updated");
                ScreenCapture.CaptureScreenshot("AoiWebSocket_NG.png");after=EditorApplication.timeSinceStartup+.5;SessionState.SetInt(Key,4);
            }
            else if(phase==4&&EditorApplication.timeSinceStartup>after)
            {Time.timeScale=1;feed.BeginSort();Check(feed.Busy,"NG did not start");SessionState.SetInt(Key,5);}
            else if(phase==5&&feed.Busy&&!feed.Fresh)
            {
                Check(feed.Verdict=="NG"&&feed.DisplayCurrent&&!feed.CanSort&&feed.dashboard.verdict.text=="NG","In-flight result expired");
                if(!retainedDuringSort)ScreenCapture.CaptureScreenshot("AoiWebSocket_SORTING_RETAINED.png");retainedDuringSort=true;
            }
            else if(phase==5&&!feed.Busy)
            {
                Check(feed.sorter.completed&&feed.sorter.ngCount==1&&Vector3.Distance(feed.sorter.product.position,feed.sorter.ngTray)<.001f,"NG tray not reached");
                Check(retainedDuringSort&&!feed.Fresh&&feed.SortCompleted&&feed.Verdict=="NG"&&!feed.CanSort,"Completed result not retained or re-sort enabled");
                ScreenCapture.CaptureScreenshot("AoiWebSocket_COMPLETED_RETAINED.png");Time.timeScale=6;after=EditorApplication.timeSinceStartup+.6;SessionState.SetInt(Key,50);
            }
            else if(phase==50&&EditorApplication.timeSinceStartup>after)
            {
                feed.Clear("서버 연결됨","두 번째 시험 대기");Publish("normal");SessionState.SetInt(Key,6);
            }
            else if(phase==6&&feed.current!=null&&feed.current.label=="normal")
            {feed.BeginSort();Check(feed.Busy,"Disconnect test did not start");StopServer();SessionState.SetInt(Key,7);}
            else if(phase==7&&!client.Connected&&!feed.Busy)
            {
                Check(feed.current==null&&!feed.CanSort&&!feed.sorter.Running&&!feed.sorter.completed&&feed.sorter.okCount==0,"Disconnect failed to clear pending result and stop motion");
                Check(feed.sorter.Status.Contains("CONNECTION LOST"),"Disconnect status missing");
                ScreenCapture.CaptureScreenshot("AoiWebSocket_DISCONNECTED.png");after=EditorApplication.timeSinceStartup+.6;SessionState.SetInt(Key,8);
            }
            else if(phase==8&&EditorApplication.timeSinceStartup>after)
            {StartServer();SessionState.SetInt(Key,9);}
            else if(phase==9&&client.Connected)
            {
                Check(feed.current==null&&!feed.CanSort,"Reconnect restored a stale result");Publish("normal");SessionState.SetInt(Key,10);
            }
            else if(phase==10&&feed.current!=null&&feed.current.label=="normal")
            {Check(feed.CanSort&&feed.Verdict=="OK","New normal result rejected");feed.BeginSort();SessionState.SetInt(Key,11);}
            else if(phase==11&&!feed.Busy)
            {
                Check(feed.sorter.completed&&feed.sorter.okCount==1&&Vector3.Distance(feed.sorter.product.position,feed.sorter.okTray)<.001f,"OK tray not reached after reconnect");
                client.enabled=false;StopServer();client.serverUrl=originalUrl;client.enabled=true;SessionState.SetInt(Key,12);
            }
            else if(phase==12&&client.Connected)
            {
                Check(feed.current==null&&!feed.CanSort&&feed.connection=="서버 연결됨","User server did not authenticate or restore safe idle");
                ScreenCapture.CaptureScreenshot("AoiWebSocket_CONNECTED.png");after=EditorApplication.timeSinceStartup+.7;SessionState.SetInt(Key,13);
            }
            else if(phase==13&&EditorApplication.timeSinceStartup>after)
            {Time.timeScale=1;SessionState.SetInt(Key,14);EditorApplication.isPlaying=false;}
            else if(phase==14&&!EditorApplication.isPlayingOrWillChangePlaymode)
            {
                File.WriteAllText("AoiWebSocketPlay.result","AOI_WEBSOCKET_PLAY_OK\nUnity ClientWebSocket authenticated with local key file.\nReal-time-speed NG sort: verdict retained beyond five-second freshness and after tray arrival; duplicate sorting blocked.\nServer loss stops motion, clears result, blocks classification.\nAutomatic reconnect requires a new result -> OK tray.\nUser server 127.0.0.1:8765 authentication verified.\nNo live camera or real Jetson inference tested.");
                EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene());SessionState.SetInt(Key,0);publisher?.Dispose();publisher=null;return;
            }
            if(phase>1&&phase<14&&EditorApplication.timeSinceStartup>deadline)throw new Exception("WebSocket integration timeout, phase="+phase+", state="+(feed?feed.connection:"missing feed"));
        }
        catch(Exception e)
        {
            StopServer();if(publisher!=null){if(!publisher.HasExited)publisher.Kill();publisher.Dispose();publisher=null;}
            File.WriteAllText("AoiWebSocketPlay.result",e.ToString());Debug.LogException(e);Time.timeScale=1;SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;
        }
    }
}
#endif
