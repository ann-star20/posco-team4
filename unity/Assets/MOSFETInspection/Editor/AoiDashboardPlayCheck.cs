#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class AoiDashboardPlayCheck
{
    const string Key="AOI_DASHBOARD_PHASE";
    static AoiJetsonFeed feed;
    static int sample;
    static double deadline,after;
    static readonly string[] Labels={"normal","crash","band","scratch"};
    static AoiDashboardPlayCheck(){EditorApplication.update+=Tick;}
    static void Check(bool b,string why){if(!b)throw new Exception(why);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                if(!File.Exists("AoiDashboardPlay.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("AoiDashboardPlay.once");SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                feed=UnityEngine.Object.FindFirstObjectByType<AoiJetsonFeed>();Check(feed&&!feed.CanSort&&!feed.demoMode&&feed.current==null&&feed.Verdict=="대기","Unexpected automatic classification or persisted result");
                var socketClient=feed.GetComponent<AoiWebSocketClient>();if(socketClient)socketClient.enabled=false;feed.useWebSocket=false;
                Application.runInBackground=true;Time.timeScale=6;
                foreach(var camera in Camera.allCameras)if(!camera.targetTexture)camera.enabled=false;feed.sorter.overview.enabled=true;
                feed.dashboard.ToggleWindow();sample=0;deadline=EditorApplication.timeSinceStartup+130;
                after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,2);
            }
            else if(phase==2&&EditorApplication.timeSinceStartup>after)
            {
                ScreenCapture.CaptureScreenshot("AoiDashboard_WAITING.png");
                after=EditorApplication.timeSinceStartup+.7;SessionState.SetInt(Key,20);
            }
            else if(phase==20&&EditorApplication.timeSinceStartup>after)
            {
                ContractChecks();feed.SetMode(true);feed.Demo(Labels[sample]);Check(feed.CanSort&&feed.Verdict=="OK","Normal must be OK");
                after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,3);
            }
            else if(phase==3&&EditorApplication.timeSinceStartup>after)
            {
                Check(feed.CanSort,"Sort gate unexpectedly blocked");
                ScreenCapture.CaptureScreenshot("AoiDashboard_"+Labels[sample]+".png");
                feed.BeginSort();Check(feed.Busy,"Sort did not start");SessionState.SetInt(Key,4);
            }
            else if(phase==4&&!feed.Busy)
            {
                Check(feed.sorter.completed&&!feed.CanSort,"Duplicate result could be sorted twice");
                Check(Vector3.Distance(feed.sorter.product.position,sample==0?feed.sorter.okTray:feed.sorter.ngTray)<.001f,"Wrong destination");
                if(++sample<4){feed.Demo(Labels[sample]);Check(feed.Verdict=="NG","Defect must be NG");after=EditorApplication.timeSinceStartup+.8;SessionState.SetInt(Key,3);}
                else
                {
                    Check(feed.sorter.okCount==1&&feed.sorter.ngCount==3,"Wrong sort totals");
                    feed.SetMode(false);Check(!feed.CanSort&&feed.current==null,"Mode switch retained demo result");
                    Time.timeScale=1;SessionState.SetInt(Key,5);EditorApplication.isPlaying=false;
                }
            }
            else if(phase==5&&!EditorApplication.isPlayingOrWillChangePlaymode)
            {
                File.WriteAllText("AoiDashboardPlay.result","AOI_DASHBOARD_PLAY_OK\nWAITING blocked; normal OK; crash/band/scratch NG; actual tray destinations; duplicate blocked; stale/unknown/invalid/low-confidence checks; monitor window.\nReal Jetson camera/model not tested.");
                EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene());SessionState.SetInt(Key,0);return;
            }
            if(phase>1&&phase<5&&EditorApplication.timeSinceStartup>deadline)throw new Exception("AOI runtime timeout");
        }
        catch(Exception e){File.WriteAllText("AoiDashboardPlay.result",e.ToString());Debug.LogException(e);Time.timeScale=1;SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;}
    }
    static void ContractChecks()
    {
        var image=new Texture2D(16,16);image.Apply();string jpg=Convert.ToBase64String(image.EncodeToJPG());UnityEngine.Object.Destroy(image);
        var p=new AoiJetsonFeed.Packet{result_id="test-1",product_id="TEST",label="normal",confidence=.99f,captured_at_ms=AoiJetsonFeed.Now,jpeg_base64=jpg};
        Check(feed.AcceptJson(JsonUtility.ToJson(p))&&feed.CanSort,"Valid packet rejected");
        Check(!feed.AcceptJson(JsonUtility.ToJson(p)),"Duplicate packet accepted");
        p.result_id="low";p.confidence=.4f;Check(feed.AcceptJson(JsonUtility.ToJson(p))&&!feed.CanSort&&feed.Verdict=="검토","Low confidence sorted");
        p.label="unknown";Reject(p,"Unknown accepted");p.label="normal";p.captured_at_ms-=10000;Reject(p,"Stale accepted");
        p.captured_at_ms=AoiJetsonFeed.Now;p.confidence=float.NaN;Reject(p,"NaN accepted");
        feed.Clear("연결 대기","테스트 종료");
    }
    static void Reject(AoiJetsonFeed.Packet p,string why)
    {bool rejected=false;try{AoiJetsonFeed.Validate(p,5);}catch(ArgumentException){rejected=true;}Check(rejected,why);}
}
#endif
