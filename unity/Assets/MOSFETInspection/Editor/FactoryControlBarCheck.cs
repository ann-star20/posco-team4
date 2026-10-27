#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
[InitializeOnLoad]
public static class FactoryControlBarCheck
{
    const string Key="FactoryControls.Check";
    static double after,deadline;
    static IonImplantCycle implant;
    static OhtFabCycle oht;
    static Vector3 carrierStart;
    static int selected;
    static FactoryControlBarCheck(){EditorApplication.update+=Tick;}
    [MenuItem("MOSFET Factory/Install Equipment Control Bar")]
    static void Install()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play first");
        const string scenePath="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity";
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        Check(scene.path==scenePath,"Open corrected cleanroom scene");
        // Reload the saved scene to discard state left by hot reload during Play.
        scene=EditorSceneManager.OpenScene(scenePath);
        var backup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeControlBar.unity");
        Check(AssetDatabase.CopyAsset(scenePath,backup),"Scene backup failed");
        if(!UnityEngine.Object.FindAnyObjectByType<FactoryControlBar>())new GameObject("Factory_Control_Bar").AddComponent<FactoryControlBar>();
        EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Scene save failed");
        File.WriteAllText("FactoryControlsInstall.result","CONTROL_BAR_INSTALLED\nbackup="+backup);File.WriteAllText("FactoryControlsPlay.once","run");
    }
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    [MenuItem("MOSFET Factory/Test Equipment Control Bar")]
    static void Request(){File.WriteAllText("FactoryControlsPlay.once","run");}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        try
        {
            if(phase==0)
            {
                if(File.Exists("FactoryControlsInstall.once")&&!EditorApplication.isPlaying&&!EditorApplication.isPlayingOrWillChangePlaymode){File.Delete("FactoryControlsInstall.once");Install();return;}
                if(!File.Exists("FactoryControlsPlay.once")||EditorApplication.isPlaying||EditorApplication.isPlayingOrWillChangePlaymode)return;
                File.Delete("FactoryControlsPlay.once");EditorSceneManager.OpenScene("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity");SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!Application.isPlaying)return;
                Application.runInBackground=true;implant=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();Check(implant,"Implanter missing");Check(UnityEngine.Object.FindAnyObjectByType<FactoryControlBar>(),"Control bar missing");
                Check(FactoryControlBar.Selected==FactoryControlBar.Equipment.Overview,"Default is not overview");
                FactoryControlBar.Select(FactoryControlBar.Equipment.Overview);
                Check(!implant.Running,"Unexpected automatic implant start");
                ScreenCapture.CaptureScreenshot("FactoryControls_OVERVIEW.png");selected=0;after=EditorApplication.timeSinceStartup+.8;deadline=after+60;SessionState.SetInt(Key,2);
            }
            else if(phase==2&&EditorApplication.timeSinceStartup>after)
            {
                if(++selected<Enum.GetValues(typeof(FactoryControlBar.Equipment)).Length)
                {
                    FactoryControlBar.Select((FactoryControlBar.Equipment)selected);int count=0;
                    for(int i=1;i<Enum.GetValues(typeof(FactoryControlBar.Equipment)).Length;i++)if(FactoryControlBar.Visible((FactoryControlBar.Equipment)i))count++;
                    Check(count==1,"More than one control panel visible");
                    var rect=FactoryControlBar.PanelRect(550,253);float scale=Mathf.Min(Screen.width/1280f,Screen.height/720f);
                    Check(rect.x>=0&&rect.y>=0&&rect.yMax<Screen.height/scale-64,"Panel overlaps toolbar or viewport");
                    ScreenCapture.CaptureScreenshot("FactoryControls_"+((FactoryControlBar.Equipment)selected)+".png");after=EditorApplication.timeSinceStartup+.8;
                }
                else
                {
                    FactoryControlBar.ToggleCollapsed();Check(!FactoryControlBar.Visible(FactoryControlBar.Equipment.AOI),"Collapse failed");
                    FactoryControlBar.Select(FactoryControlBar.Equipment.Implanter);Check(!FactoryControlBar.Collapsed,"Selection did not expand panel");
                    Check(!implant.LotBlocked,"Demo LOT unexpectedly held");oht=UnityEngine.Object.FindAnyObjectByType<OhtFabCycle>();
                    if(oht){Check(implant.TransportAvailable,"Idle OHT locked individual implant start");oht.StartCycle();Check(oht.Running,"OHT manual start failed");implant.StartCycle();Check(!implant.Running,"Undocked implant started during OHT sequence");carrierStart=oht.stocker?oht.stocker.fork.position:oht.lift.position;}
                    else{implant.StartCycle();Check(implant.Running,"Manual start failed");carrierStart=implant.carrier.position;}
                    implant.dashboard.ToggleWindow();FactoryControlBar.Select(FactoryControlBar.Equipment.AOI);Check(oht?oht.Running:implant.Running,"Switch stopped animation");
                    after=EditorApplication.timeSinceStartup+1.5;SessionState.SetInt(Key,3);
                }
            }
            else if(phase==3&&EditorApplication.timeSinceStartup>after)
            {
                Check(oht?oht.Running&&!oht.failed:implant.Running&&!implant.failed,"Animation did not keep running");Check(Vector3.Distance(carrierStart,oht?(oht.stocker?oht.stocker.fork.position:oht.lift.position):implant.carrier.position)>.0001f,"Hidden equipment stopped moving");
                Check(GameObject.Find("ION_MONITOR_WINDOW_CAMERA").GetComponent<Camera>().enabled,"Selection closed monitor window");
                ScreenCapture.CaptureScreenshot("FactoryControls_SWITCH_RUNNING.png");after=EditorApplication.timeSinceStartup+.8;SessionState.SetInt(Key,4);
            }
            else if(phase==4&&EditorApplication.timeSinceStartup>after)
            {
                File.WriteAllText("FactoryControlsPlay.result","FACTORY_CONTROLS_PLAY_OK\nDefault overview; one selected panel; bottom layout; collapse/expand; selection preserves running animation and open monitor window.\nScreenshots: overview, all equipment panels including OHT, switch while running.");SessionState.SetInt(Key,5);EditorApplication.isPlaying=false;return;
            }
            else if(phase==5&&!EditorApplication.isPlayingOrWillChangePlaymode){EditorSceneManager.OpenScene("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity");SessionState.SetInt(Key,0);return;}
            if(phase>=2&&phase<=4)Check(EditorApplication.timeSinceStartup<deadline,"Runtime test timeout");
        }
        catch(Exception e){File.WriteAllText("FactoryControlsPlay.result",e.ToString());Debug.LogException(e);SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;}
    }
}
#endif
