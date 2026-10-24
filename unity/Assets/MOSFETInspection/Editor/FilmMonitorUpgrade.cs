#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

[InitializeOnLoad]
public static class FilmMonitorUpgrade
{
    const string Key="FILM_HISTORY_UPGRADE";
    static EllipsometerCycle film;
    static FilmInspectionHistory store;
    static string folder;
    static double deadline,after;
    static FilmMonitorUpgrade(){EditorApplication.update+=Tick;}
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static void Capture(string name)
    {
        var camera=GameObject.Find("ELLIPSOMETER_MONITOR_WINDOW_CAMERA").GetComponent<Camera>();var rt=camera.targetTexture;var previous=RenderTexture.active;
        try{RenderTexture.active=rt;var texture=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);texture.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);texture.Apply();File.WriteAllBytes("Tools/JetsonML/"+name+".png",texture.EncodeToPNG());UnityEngine.Object.Destroy(texture);}finally{RenderTexture.active=previous;}
    }
    static void Press(string name)
    {
        var camera=GameObject.Find("ELLIPSOMETER_MONITOR_WINDOW_CAMERA").GetComponent<Camera>();
        var button=Array.Find(film.dashboard.GetComponentsInChildren<Button>(false),b=>b.name==name);Check(button,"Button unavailable: "+name);
        var rect=(RectTransform)button.transform;var pixel=RectTransformUtility.WorldToScreenPoint(camera,rect.TransformPoint(rect.rect.center));Check(film.dashboard.HandlePointer(pixel,camera),"Monitor pointer failed: "+name);
    }
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        int phase=SessionState.GetInt(Key,0);
        if(phase==0&&!EditorApplication.isPlayingOrWillChangePlaymode&&SessionState.GetBool(Key+"-restore",false)){EditorSettings.enterPlayModeOptionsEnabled=SessionState.GetBool(Key+"-original",true);SessionState.SetBool(Key+"-restore",false);}
        try
        {
            if(phase==0)
            {
                if(!File.Exists("FilmMonitorUpgrade.once"))return;
                if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
                File.Delete("FilmMonitorUpgrade.once");folder="Temp/FilmHistoryChecks-"+Guid.NewGuid().ToString("N");Directory.CreateDirectory(folder);FilmHistoryChecks.Run(folder);
                var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();Check(scene.path=="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity","Open the original cleanroom scene first");
                string backup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeHistory_"+DateTime.Now.ToString("yyyyMMdd_HHmmss")+".unity");
                Check(EditorSceneManager.SaveScene(scene,backup,true),"Current scene backup failed");
                film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();Check(film&&film.recipe&&film.monitor,"Film monitor unavailable");
                FilmInspectionDashboard.Install(film);EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Updated scene save failed");
                File.WriteAllText("FilmMonitorUpgrade.status","History storage checks passed. Previous scene: "+backup+"\nNew film dashboard installed; runtime checks pending.");
                SessionState.SetString(Key+"-folder",folder);SessionState.SetBool(Key+"-original",EditorSettings.enterPlayModeOptionsEnabled);SessionState.SetBool(Key+"-restore",true);EditorSettings.enterPlayModeOptionsEnabled=false;SessionState.SetInt(Key,1);EditorApplication.isPlaying=true;return;
            }
            if(phase==1)
            {
                if(!EditorApplication.isPlayingOrWillChangePlaymode){SessionState.SetInt(Key,0);return;}
                if(!Application.isPlaying)return;
                film=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();if(!film||!film.dashboard)return;
                folder=SessionState.GetString(Key+"-folder","");store=new FilmInspectionHistory(Path.Combine(folder,"play.json"));FilmInspectionHistory.UseTestStore(store);
                if(LotProcessAnalysis.Instance)LotProcessAnalysis.Instance.enabled=false;
                film.transportControlled=false;film.lotId="HISTORY-TEST";film.validationDelta=.3f;film.ResetDashboardDemo();film.StartScan();deadline=EditorApplication.timeSinceStartup+150;SessionState.SetInt(Key,2);
            }
            else if(phase==2&&film.completed)
            {
                Check(film.verdict=="PASS"&&store.ForDay(DateTime.Today).pass==1,"PASS not archived");film.EvaluateInspection();Check(store.ForDay(DateTime.Today).total==1,"Double evaluation duplicated history");
                film.demoHold=true;film.StartScan();SessionState.SetInt(Key,3);
            }
            else if(phase==3&&film.completed)
            {
                var counts=store.ForDay(DateTime.Today);Check(film.verdict=="FAIL"&&film.lotHeld&&!film.CanProceed&&counts.total==2&&counts.pass==1&&counts.ng==1&&counts.normalPercent==50,"NG/HOLD/counts incorrect");
                Check(new FilmInspectionHistory(store.FilePath).ForDay(DateTime.Today).total==2,"History not durable");Check(film.dashboard.TodaySummary.Contains("50.0"),"Normal rate absent from display");
                film.ZoomMonitor();after=EditorApplication.timeSinceStartup+1;SessionState.SetInt(Key,4);
            }
            else if(phase==4&&EditorApplication.timeSinceStartup>after)
            {Capture("FilmMonitor_New_Overview");Press("TabHistory");Check(film.dashboard.View==1,"History tab failed");after=EditorApplication.timeSinceStartup+.6;SessionState.SetInt(Key,5);}
            else if(phase==5&&EditorApplication.timeSinceStartup>after)
            {
                Press("HistoryRow0");var detail=Array.Find(film.dashboard.GetComponentsInChildren<Text>(false),t=>t.name=="HistoryDetail");Check(detail&&detail.text.Contains(store.OnDay(DateTime.Today)[0].inspection_id),"Selected history row did not show full ID");after=EditorApplication.timeSinceStartup+.6;SessionState.SetInt(Key,7);
            }
            else if(phase==7&&EditorApplication.timeSinceStartup>after)
            {
                Capture("FilmMonitor_New_History");Press("HistoryFilter");Press("NextPage");Press("PreviousPage");Press("PreviousDay");Press("NextDay");Press("TabCriteria");Check(film.dashboard.View==2,"Criteria tab failed");after=EditorApplication.timeSinceStartup+.6;SessionState.SetInt(Key,6);
            }
            else if(phase==6&&EditorApplication.timeSinceStartup>after)
            {
                Capture("FilmMonitor_New_Criteria");
                File.WriteAllText("FilmMonitorUpgrade.result","FILM_MONITOR_HISTORY_OK\nStorage: persistence, de-duplication, daily isolation, reinspection, invalid/corrupt/unwritable handling passed.\nUnity: PASS/NG cycle, HOLD preserved, 50% normal rate, monitor pointer/tab/row/filter/date/page checks passed.\nRuntime checks used a separate test archive; production statistics were not seeded. No TCAD/approval/recipe application.");
                SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;
            }
            if(phase>=2&&phase<=3&&(film.failed||EditorApplication.timeSinceStartup>deadline))throw new Exception("Runtime inspection failed/timed out: "+film.status);
        }
        catch(Exception e){File.WriteAllText("FilmMonitorUpgrade.result","FAILED: "+e);SessionState.SetInt(Key,0);EditorApplication.isPlaying=false;Debug.LogException(e);}
    }
}
#endif
