#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
[InitializeOnLoad]
public static class IonDashboardSetup
{
    const string Key="IonDashboard.CheckPhase";
    static IonImplantCycle cycle;
    static double deadline,after;
    static float pausedDose;
    static IonDashboardSetup(){EditorApplication.update+=Tick;}
    [MenuItem("MOSFET Factory/Install Ion Dashboard")]
    public static void Install()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play before installation");
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(scene.path!="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity")throw new Exception("Open corrected cleanroom scene");
        cycle=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();if(!cycle||!cycle.monitor)throw new Exception("Ion monitor missing");
        if(!EditorSceneManager.SaveScene(scene))throw new Exception("Save cancelled");
        var backup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeIonDashboard.unity");
        if(!AssetDatabase.CopyAsset(scene.path,backup))throw new Exception("Backup failed");
        IonImplantDashboard.Install(cycle);EditorUtility.SetDirty(cycle);EditorSceneManager.MarkSceneDirty(scene);EditorSceneManager.SaveScene(scene);
        File.WriteAllText("IonDashboard.result","ION_DASHBOARD_INSTALLED\nbackup="+backup);File.WriteAllText("IonDashboardPlay.once","run");
    }
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                if(File.Exists("IonDashboard.once")){if(EditorApplication.isPlayingOrWillChangePlaymode)return;File.Delete("IonDashboard.once");Install();return;}
                if(!File.Exists("IonDashboardPlay.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode)return;
                File.Delete("IonDashboardPlay.once");SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                cycle=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();Check(cycle&&cycle.dashboard,"Missing dashboard");Check(!cycle.Running&&cycle.dose==0,"Unexpected automatic start");
                Application.runInBackground=true;cycle.SelectCamera(cycle.detail);cycle.dashboard.ToggleWindow();
                Check(cycle.lotQualityGate,"Missing quality gate");cycle.lotQualityGate.lotId=cycle.incomingLotId;cycle.lotQualityGate.lotHeld=true;cycle.StartCycle();
                cycle.dashboard.Refresh();Check(!cycle.Running&&cycle.dashboard.state.text.Contains("HOLD"),"LOT HOLD not enforced/displayed");
                ScreenCapture.CaptureScreenshot("IonDashboard_HOLD.png");after=EditorApplication.timeSinceStartup+1;deadline=EditorApplication.timeSinceStartup+180;SessionState.SetInt(Key,2);
            }
            else if(phase==2&&EditorApplication.timeSinceStartup>after)
            {cycle.lotQualityGate.lotHeld=false;cycle.RefreshLotGate();Time.timeScale=4;cycle.StartCycle();SessionState.SetInt(Key,3);}
            else if(phase==3&&cycle.progress>.15f&&cycle.progress<1)
            {
                cycle.TogglePause();pausedDose=cycle.dose;cycle.dashboard.Refresh();Check(cycle.dashboard.state.text.Contains("PAUSED"),"Pause display failed");
                ScreenCapture.CaptureScreenshot("IonDashboard_IMPLANT_PAUSED.png");after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,4);
            }
            else if(phase==4&&EditorApplication.timeSinceStartup>after)
            {Check(cycle.dose==pausedDose,"Dose changed while paused");cycle.TogglePause();SessionState.SetInt(Key,5);}
            else if(phase==5&&cycle.completed)
            {
                cycle.dashboard.Refresh();Check(Mathf.Approximately(cycle.dose,cycle.targetDose)&&cycle.progress==1,"Dose did not reach target");Check(!cycle.AnyGateOpen,"Gate left open");
                Check(cycle.dashboard.disposition.text.Contains("품질 PASS를 의미하지 않음"),"Completion mistaken for quality pass");
                ScreenCapture.CaptureScreenshot("IonDashboard_COMPLETE.png");after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,6);
            }
            else if(phase==6&&EditorApplication.timeSinceStartup>after)
            {
                Time.timeScale=1;File.WriteAllText("IonDashboardPlay.result","ION_DASHBOARD_PLAY_OK\nManual start; LOT HOLD blocked; pause freezes dose; target dose reached; wafer return and gate interlocks completed; process complete is not quality PASS; live monitor window.");
                SessionState.SetInt(Key,7);EditorApplication.isPlaying=false;return;
            }
            else if(phase==7&&!EditorApplication.isPlayingOrWillChangePlaymode){SessionState.SetInt(Key,0);return;}
            if(phase>=2&&phase<=6){Check(cycle,"Play interrupted");Check(!cycle.failed,"Cycle interlock failure: "+cycle.status);Check(EditorApplication.timeSinceStartup<deadline,"Runtime check timeout");}
        }
        catch(Exception e){File.WriteAllText("IonDashboardPlay.result",e.ToString());Debug.LogException(e);SessionState.SetInt(Key,0);if(Application.isPlaying)Time.timeScale=1;EditorApplication.isPlaying=false;}
    }
}
#endif
