#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

[InitializeOnLoad]
public static class IonClassicSetup
{
    static IonClassicSetup(){EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(File.Exists("IonFixedDisplayInstall.once")&&!EditorApplication.isCompiling&&!EditorApplication.isUpdating&&!EditorApplication.isPlayingOrWillChangePlaymode)
        {
            File.Delete("IonFixedDisplayInstall.once");
            try{ApplyFixedDisplay();}catch(Exception e){File.WriteAllText("IonFixedDisplayInstall.result",e.ToString());Debug.LogException(e);}
        }
        if(File.Exists("IonMlDoseInstall.once")&&!EditorApplication.isCompiling&&!EditorApplication.isUpdating&&!EditorApplication.isPlayingOrWillChangePlaymode)
        {
            File.Delete("IonMlDoseInstall.once");
            try{ApplyMlDose();}catch(Exception e){File.WriteAllText("IonMlDoseInstall.result",e.ToString());Debug.LogException(e);}
        }
        if(!File.Exists("IonClassicInstall.once")||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete("IonClassicInstall.once");
        try{Install();}catch(Exception e){File.WriteAllText("IonClassicInstall.result",e.ToString());Debug.LogException(e);}
    }
    [MenuItem("MOSFET Factory/Apply Ion Fixed Preview Display")]
    public static void ApplyFixedDisplay()
    {
        Check(!EditorApplication.isPlayingOrWillChangePlaymode,"Exit Play before checking display");
        var c=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();Check(c&&c.dashboard,"Open the IMP-01 scene");
        var d=c.dashboard;float target=c.targetDose,dose=c.dose;double lo=d.doseLower,hi=d.doseUpper;
        bool complete=c.completed,fault=c.failed;float progress=c.progress;int view=d.View;
        var texts=d.GetComponentsInChildren<Text>(true);
        int historyCount=IonImplantHistory.Instance.Today().Count;
        try
        {
            d.ToggleWindow();var overlay=GameObject.Find("ION_CLASSIC_SCREEN_OVERLAY").GetComponent<Canvas>();
            Check(overlay.renderMode==RenderMode.ScreenSpaceOverlay&&overlay.worldCamera==null,"Display still uses scene camera");
            var clone=overlay.GetComponentInChildren<RectTransform>().GetChild(0).GetComponent<RectTransform>();
            Check(clone.anchorMin==new Vector2(.5f,.5f)&&clone.anchorMax==clone.anchorMin,"Display not centered");
            d.SendMessage("LateUpdate");var position=clone.anchoredPosition;
            d.SendMessage("LateUpdate");Check(clone.anchoredPosition==position,"Display position drifted");
            var copies=overlay.GetComponentsInChildren<Graphic>(true);var originals=d.transform.Find("IonClassicSurface").GetComponentsInChildren<Graphic>(true);
            Check(copies.Length==originals.Length,"Incomplete overlay clone");
            for(int i=0;i<copies.Length;i++)Check(copies[i].color==originals[i].color,"Preview RGB changed: "+originals[i].name);
            Check(overlay.GetComponentsInChildren<Text>(true).Single(t=>t.name=="Title").color==(Color)new Color32(32,37,32,255),"Preview ink mismatch");
            foreach(int tab in new[]{1,2,0}){d.SetView(tab);d.SendMessage("LateUpdate");Check(overlay.transform.GetChild(0).Find(new[]{"LiveView","HistoryView","RecipeView"}[tab]).gameObject.activeSelf,"Tab not synchronized");}
            c.progress=.5f;d.Refresh();d.SendMessage("LateUpdate");
            Check(overlay.GetComponentsInChildren<Image>(true).Single(i=>i.name=="Progress").rectTransform.sizeDelta.x==149.5f,"Progress width not synchronized");
            d.ToggleWindow();Check(!overlay.enabled,"Close failed");d.ToggleWindow();Check(overlay.enabled,"Reopen failed");
            Check(UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsInactive.Include).Count(x=>x.name=="ION_CLASSIC_SCREEN_OVERLAY")==1,"Reopen duplicated canvas");
            d.ToggleWindow();d.enabled=false;Check(!overlay,"Overlay leaked after disable");d.enabled=true;
        }
        finally
        {
            c.completed=complete;c.failed=fault;c.dose=dose;c.progress=progress;d.SetView(view);
            var leftover=GameObject.Find("ION_CLASSIC_SCREEN_OVERLAY");if(leftover)UnityEngine.Object.DestroyImmediate(leftover);
        }
        Check(c.targetDose==target&&d.doseLower==lo&&d.doseUpper==hi,"Dose recipe changed during display update");
        Check(IonImplantHistory.Instance.Today().Count==historyCount,"Display tests changed process history");
        File.WriteAllText("IonFixedDisplayInstall.result","ION_FIXED_DISPLAY_OK\nFixed centered ScreenSpaceOverlay / preview RGB retained / tabs / progress sync / close-reopen / cleanup / dose preset and history preserved");
        Debug.Log("ION_FIXED_DISPLAY_OK");
    }
    [MenuItem("MOSFET Factory/Apply Ion TCAD ML Dose")]
    public static void ApplyMlDose()
    {
        Check(!EditorApplication.isPlayingOrWillChangePlaymode,"Exit Play before changing dose");
        var c=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();Check(c&&c.dashboard,"Open the IMP-01 scene");
        var scene=c.gameObject.scene;
        string copy=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeIonMlDose.unity");
        Check(EditorSceneManager.SaveScene(scene,copy,true),"Scene backup failed");
        var d=c.dashboard;
        c.targetDose=(float)IonDoseAssessment.MlTarget;
        d.doseLower=IonDoseAssessment.MlLower;d.doseUpper=IonDoseAssessment.MlUpper;
        d.Refresh();
        Check(d.recipeText.text.Contains("7.70E+12"),"Target display incorrect");
        Check(d.GetComponentsInChildren<Text>(true).Single(t=>t.name=="ConditionValue5").text.Contains("7.315E+12"),"Lower limit display incorrect");
        Check(IonDoseAssessment.Evaluate((float)d.doseLower,d.doseLower,d.doseUpper,true,false)=="OK","Lower boundary failed");
        Check(IonDoseAssessment.Evaluate((float)d.doseUpper,d.doseLower,d.doseUpper,true,false)=="OK","Upper boundary failed");
        EditorUtility.SetDirty(c);EditorUtility.SetDirty(d);EditorSceneManager.MarkSceneDirty(scene);
        Check(EditorSceneManager.SaveScene(scene),"Scene save failed");
        File.WriteAllText("IonMlDoseInstall.result","ION_ML_DOSE_INSTALL_OK\nTarget 7.70E+12; inclusive limits 7.315E+12..8.085E+12 cm^-2; simulation only\nBackup: "+copy);
        Debug.Log("ION_ML_DOSE_INSTALL_OK");
    }
    static void Check(bool ok,string message){if(!ok)throw new InvalidOperationException(message);}
    [MenuItem("MOSFET Factory/Apply Ion Windows Dashboard")]
    public static void Install()
    {
        Check(!EditorApplication.isPlayingOrWillChangePlaymode,"Exit Play before installing the dashboard");
        var c=UnityEngine.Object.FindAnyObjectByType<IonImplantCycle>();Check(c&&c.monitor,"Open the cleanroom scene containing IMP-01");
        string backup="Tools/Backups/IonClassicScene-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(backup);
        string sceneBackup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeIonClassic.unity");
        Check(EditorSceneManager.SaveScene(c.gameObject.scene,sceneBackup,true),"Scene backup failed");File.Copy(sceneBackup,backup+"/BeforeIonClassic.unity");
        IonImplantDashboard.Install(c);var d=c.dashboard;
        Check(d.transform.Find("IonClassicSurface"),"Classic surface missing");
        Check(!d.transform.Find("BeamSource")&&!d.transform.Find("BeamLabel"),"Old beam diagram remains");
        Check(d.GetComponentsInChildren<Text>(true).All(t=>t.font),"Missing font");
        Check(d.GetComponentsInChildren<Text>(true).Count(t=>t.name.StartsWith("ConditionValue"))==7,"Condition field count mismatch");
        var oldStore=IonImplantHistory.Instance;var priorDose=c.dose;bool complete=c.completed,fault=c.failed;int count=c.completedRuns;
        double lo=d.doseLower,hi=d.doseUpper;string recipe=d.recipeId,oldGateLot=c.lotQualityGate?c.lotQualityGate.lotId:null;bool held=c.lotQualityGate&&c.lotQualityGate.lotHeld;
        var store=new IonImplantHistory("Temp/IonClassic/"+Guid.NewGuid().ToString("N")+".json");
        try
        {
            IonImplantHistory.UseTestStore(store);if(c.lotQualityGate)c.lotQualityGate.lotHeld=false;
            c.completed=true;c.failed=false;c.dose=1e13f;d.doseLower=d.doseUpper=0;d.Refresh();
            Check(d.DoseVerdict=="미판정","Absent specification invented OK");
            d.doseLower=9e12;d.doseUpper=11e12;d.Refresh();Check(d.DoseVerdict=="OK","OK display failed");
            c.dose=8.7e12f;d.Refresh();Check(d.DoseVerdict=="FAIL","FAIL display failed");
            var text=d.GetComponentsInChildren<Text>(true).Single(t=>t.name=="ConditionValue6");Check(text.text=="-13.0%","Deviation mismatch: "+text.text);
            if(c.lotQualityGate){c.lotQualityGate.lotId=c.incomingLotId;c.lotQualityGate.lotHeld=true;d.Refresh();Check(d.state.text.Contains("HOLD")&&d.DoseVerdict=="보류","HOLD bypassed");c.lotQualityGate.lotHeld=false;}
            c.failed=true;d.Refresh();Check(d.DoseVerdict=="정지","Interlock mistaken for FAIL");c.failed=false;
            string now=DateTimeOffset.Now.ToString("O");
            var first=new IonImplantHistory.Entry{id="ui-test-ok",completed_at=now,lot_id="TEST",dose=1e13,verdict="OK"};
            Check(store.Add(first)&&!store.Add(first),"History duplicate not rejected");
            store.Add(new IonImplantHistory.Entry{id="ui-test-ng",completed_at=now,lot_id="TEST",dose=8.7e12,verdict="FAIL"});
            store.Add(new IonImplantHistory.Entry{id="ui-test-pending",completed_at=now,lot_id="TEST",dose=1e13,verdict="미판정"});d.Refresh();
            Check(d.GetComponentsInChildren<Text>(true).Single(t=>t.name=="StatValue3").text=="50.0 %","Unjudged history polluted yield");
            d.SetView(1);Check(d.View==1&&d.transform.Find("IonClassicSurface/HistoryView").gameObject.activeSelf,"History tab failed");
            d.SetView(2);Check(d.View==2&&d.transform.Find("IonClassicSurface/RecipeView").gameObject.activeSelf,"Recipe tab failed");
            Check(d.disposition.text.Contains("품질 PASS를 의미하지 않음"),"Process completion reclassified electrical quality");
        }
        finally
        {
            c.dose=priorDose;c.completed=complete;c.failed=fault;c.completedRuns=count;d.doseLower=lo;d.doseUpper=hi;d.recipeId=recipe;
            if(c.lotQualityGate){c.lotQualityGate.lotHeld=held;c.lotQualityGate.lotId=oldGateLot;}IonImplantHistory.UseTestStore(oldStore);d.SetView(0);
        }
        EditorUtility.SetDirty(c);EditorUtility.SetDirty(d);EditorSceneManager.MarkSceneDirty(c.gameObject.scene);
        Check(EditorSceneManager.SaveScene(c.gameObject.scene),"Scene save failed");
        File.WriteAllText("IonClassicInstall.result","ION_CLASSIC_INSTALL_OK\nClassic surface / 7 conditions / absent limits pending / OK and FAIL / -13% deviation / HOLD and interlock / local duplicate protection / unjudged excluded from yield / tabs / original state restored\nBackup: "+backup);
        Debug.Log("ION_CLASSIC_INSTALL_OK");
    }
}
#endif
