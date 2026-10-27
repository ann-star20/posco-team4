#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

[InitializeOnLoad]
public static class FilmSignalSetup
{
    static FilmSignalSetup(){EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(!File.Exists("FilmSignalInstall.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("FilmSignalInstall.once");
        try{Install();}catch(Exception e){File.WriteAllText("FilmSignalInstall.result",e.ToString());Debug.LogException(e);}
    }
    static void Check(bool ok,string reason){if(!ok)throw new InvalidOperationException(reason);}
    [MenuItem("MOSFET Factory/Apply Film Signal Dashboard")]
    public static void Install()
    {
        Check(!EditorApplication.isPlayingOrWillChangePlaymode,"Exit Play before installing the dashboard.");
        var cycle=UnityEngine.Object.FindAnyObjectByType<EllipsometerCycle>();Check(cycle&&cycle.monitor&&cycle.recipe,"Open the factory scene containing ELLIP-01 first.");
        var scene=cycle.gameObject.scene;
        string backup="Tools/Backups/FilmSignal-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(backup);
        string sceneBackup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeFilmSignal.unity");
        Check(EditorSceneManager.SaveScene(scene,sceneBackup,true),"Scene backup failed.");File.Copy(sceneBackup,backup+"/BeforeFilmSignal.unity",true);
        FilmInspectionDashboard.Install(cycle);var d=cycle.dashboard;
        Check(d.transform.Find("FilmSignalSurface"),"New dashboard surface missing.");
        var texts=d.GetComponentsInChildren<Text>(true);Check(texts.All(t=>t.font),"Missing UI font.");
        Check(texts.Single(t=>t.name=="StatValue0").fontSize==23,"Compact daily statistics changed.");
        Check(d.transform.Find("FilmSignalSurface/StatPanel0").GetComponent<Image>().color==FilmInspectionDashboard.Panel,"Preview surface color mismatch.");
        var originalStore=FilmInspectionHistory.Instance;var readings=cycle.readings;string verdict=cycle.verdict;bool held=cycle.lotHeld;
        try
        {
            FilmInspectionHistory.UseTestStore(new FilmInspectionHistory("Temp/FilmSignal/isolated-"+Guid.NewGuid().ToString("N")+".json"));
            texts.Single(t=>t.name=="ResultPanelTitle").text="검사 결과 / 두께";
            cycle.readings=new[]{108.6f,109.1f,109.3f};cycle.verdict="FAIL";cycle.lotHeld=true;d.Refresh();
            Check(d.average.text=="109.0 nm"&&d.judgement.text=="FAIL"&&d.judgement.color==FilmInspectionDashboard.Red&&d.lot.text.Contains("HOLD"),"NG / HOLD display failed.");
            Check(texts.Single(t=>t.name=="ResultPanelTitle").text=="검사 결과","Result header still includes thickness.");
            var frame=d.GetComponentsInChildren<Image>(true).Single(i=>i.name=="VerdictBorder");
            Check(frame.color==FilmInspectionDashboard.Red,"FAIL border color mismatch.");
            cycle.readings=new[]{99.6f,100.1f,100.3f};cycle.verdict="PASS";d.Refresh();
            Check(d.judgement.text=="PASS"&&frame.color==FilmInspectionDashboard.Green&&d.lot.text.Contains("HOLD"),"Remeasurement display bypassed HOLD.");
            cycle.readings=new[]{float.NaN,float.NaN,float.NaN};cycle.verdict="PENDING";cycle.lotHeld=false;d.Refresh();
            Check(d.average.text=="— nm"&&d.judgement.text=="검사 대기","Pending display failed.");
            d.SetView(1);Check(d.View==1&&texts.Single(t=>t.name=="HistoryTitle").gameObject.activeInHierarchy,"History navigation failed.");
            d.SetView(2);Check(d.View==2&&texts.Single(t=>t.name=="Criteria").text.Contains("양산 승인 규격 아님"),"Criteria / provenance display failed.");
        }
        finally{cycle.readings=readings;cycle.verdict=verdict;cycle.lotHeld=held;FilmInspectionHistory.UseTestStore(originalStore);d.SetView(0);}
        Check(EditorSceneManager.SaveScene(scene),"New dashboard scene save failed.");
        File.WriteAllText("FilmSignalInstall.result","FILM_SIGNAL_INSTALL_OK\nCompact statistics / approved palette / 3-point map / PASS-NG-pending / HOLD preserved / history and criteria tabs / isolated UI checks only\nBackup: "+backup);
        Debug.Log("FILM_SIGNAL_INSTALL_OK");
    }
}
#endif
