#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class FilmDashboardPlayCheck
{
    const string Key="FilmDashboard.PlayPhase";
    static EllipsometerCycle cycle;
    static double deadline,after;
    static FilmDashboardPlayCheck(){EditorApplication.update+=Tick;}
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        if(phase==0)
        {
            if(!File.Exists("FilmDashboardReleaseCheck.once"))return;
            File.Delete("FilmDashboardReleaseCheck.once");
            if(EditorApplication.isPlaying){File.WriteAllText("FilmDashboardPlay.result","Exit Play before test");return;}
            EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene());
            SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
        }
        try
        {
            if(phase==1)
            {
                if(!EditorApplication.isPlaying||EditorApplication.isPlayingOrWillChangePlaymode&&!Application.isPlaying)return;
                cycle=GameObject.Find("Ellipsometer_System").GetComponent<EllipsometerCycle>();
                Check(!cycle.Running&&cycle.verdict=="PENDING","Unexpected automatic start");
                Application.runInBackground=true;if(!cycle.detail.enabled)cycle.ShowDetail();
                cycle.ZoomMonitor();cycle.demoHold=true;cycle.StartScan();deadline=EditorApplication.timeSinceStartup+150;SessionState.SetInt(Key,2);
            }
            else if(phase==2&&cycle.completed)
            {
                Check(cycle.verdict=="FAIL"&&cycle.lotHeld&&!cycle.CanProceed,"Runtime FAIL did not HOLD");
                var implant=GameObject.Find("Ion_Implanter").GetComponent<IonImplantCycle>();implant.StartCycle();Check(!implant.Running,"Held implant started");
                ScreenCapture.CaptureScreenshot("FilmDashboard_Play_HOLD.png");after=EditorApplication.timeSinceStartup+.8;SessionState.SetInt(Key,3);
            }
            else if(phase==3&&EditorApplication.timeSinceStartup>after)
            {cycle.demoHold=cycle.demoLow=false;cycle.StartScan();SessionState.SetInt(Key,4);}
            else if(phase==4&&cycle.completed)
            {
                Check(cycle.verdict=="PASS"&&cycle.lotHeld&&!cycle.CanProceed,"Runtime remeasure bypassed review");
                Check(cycle.ApproveRelease()&&cycle.CanProceed,"Runtime review release failed");
                var implant=GameObject.Find("Ion_Implanter").GetComponent<IonImplantCycle>();
                implant.RefreshLotGate();Check(!implant.LotBlocked&&implant.status=="READY","Released implant still displays HOLD");
                ScreenCapture.CaptureScreenshot("FilmDashboard_Play_RELEASED.png");after=EditorApplication.timeSinceStartup+.8;SessionState.SetInt(Key,5);
            }
            else if(phase==5&&EditorApplication.timeSinceStartup>after)
            {
                cycle.ZoomMonitor();File.WriteAllText("FilmDashboardPlay.result","FILM_DASHBOARD_PLAY_OK\nmanual start / live monitor window / FAIL + HOLD / implant blocked / PASS remeasure + review release");
                SessionState.SetInt(Key,6);EditorApplication.isPlaying=false;return;
            }
            else if(phase==6&&!EditorApplication.isPlayingOrWillChangePlaymode)
            {
                cycle=GameObject.Find("Ellipsometer_System").GetComponent<EllipsometerCycle>();
                cycle.Initialize();cycle.ResetDashboardDemo();if(!cycle.detail.enabled)cycle.ShowDetail();
                EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene());SessionState.SetInt(Key,0);return;
            }
            if(phase>1&&phase<6&&(EditorApplication.timeSinceStartup>deadline||cycle.failed))throw new Exception("Runtime cycle failed or timed out: "+cycle.status);
        }
        catch(Exception e)
        {File.WriteAllText("FilmDashboardPlay.result",e.ToString());Debug.LogException(e);SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;}
    }
}
#endif
