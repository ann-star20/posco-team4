#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

public static class FilmDashboardSetup
{
    const string Base="Assets/MOSFETInspection/";
    static EllipsometerCycle test;
    static IonImplantCycle implant;
    static Camera camera;
    static Stack<IEnumerator> steps;
    static int pass,ticks,captureWait;
    static string last,backup;
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Requested;EditorApplication.update+=Requested;}
    static void Requested()
    {
        if(!File.Exists("FilmDashboard.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("FilmDashboard.once");try{Build();}catch(Exception e){Fail(e);}
    }
    public static FilmInspectionRecipe LoadRecipe()
    {
        const string path=Base+"Settings/FilmInspectionDemo.asset";
        var recipe=AssetDatabase.LoadAssetAtPath<FilmInspectionRecipe>(path);
        if(!recipe){recipe=ScriptableObject.CreateInstance<FilmInspectionRecipe>();AssetDatabase.CreateAsset(recipe,path);}
        recipe.Validate();return recipe;
    }
    static void Check(bool condition,string message){if(!condition)throw new Exception(message);}
    static void UnitChecks(FilmInspectionRecipe r)
    {
        Check(r.Evaluate(new[]{r.lowerNm,r.targetNm,r.upperNm},out _) =="PASS","Inclusive specification boundaries failed");
        Check(r.Evaluate(new[]{r.lowerNm-1,r.targetNm,r.upperNm+1},out _) =="FAIL","Mean masked a bad site");
        bool rejected=false;try{r.Evaluate(new[]{float.NaN,100f,100f},out _);}catch(InvalidOperationException){rejected=true;}Check(rejected,"NaN accepted");
        rejected=false;try{r.Evaluate(new[]{100f},out _);}catch(InvalidOperationException){rejected=true;}Check(rejected,"Incomplete readings accepted");
        rejected=false;float original=r.upperNm;try{r.upperNm=r.lowerNm;r.Validate();}catch(InvalidOperationException){rejected=true;}finally{r.upperNm=original;}Check(rejected,"Invalid limits accepted");
    }
    [MenuItem("MOSFET Factory/Install Film Dashboard and HOLD Workflow")]
    public static void Build()
    {
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        bool failedTest=File.Exists("FilmDashboard.result")&&File.ReadAllText("FilmDashboard.result").StartsWith("System.Exception");
        if(current.isDirty&&!failedTest&&!EditorSceneManager.SaveScene(current))throw new Exception("Scene save failed");
        // Reload the saved scene rather than saving a failed test's transient robot pose.
        EditorSceneManager.OpenScene(Base+"Scenes/MOSFETSmallFab_Corrected.unity");
        backup=AssetDatabase.GenerateUniqueAssetPath(Base+"Scenes/MOSFETSmallFab_BeforeFilmDashboard.unity");
        if(!AssetDatabase.CopyAsset(Base+"Scenes/MOSFETSmallFab_Corrected.unity",backup))throw new Exception("Backup failed");
        test=GameObject.Find("Ellipsometer_System").GetComponent<EllipsometerCycle>();test.recipe=LoadRecipe();UnitChecks(test.recipe);
        FilmInspectionDashboard.Install(test);
        implant=GameObject.Find("Ion_Implanter").GetComponent<IonImplantCycle>();implant.lotQualityGate=test;implant.incomingLotId=test.lotId;implant.Initialize();
        test.Initialize();test.ResetDashboardDemo();test.validationDelta=1f/30;
        camera=new GameObject("DASHBOARD_REVIEW_CAMERA").AddComponent<Camera>();camera.orthographic=true;camera.orthographicSize=.178f;camera.nearClipPlane=.01f;camera.enabled=false;
        camera.transform.position=test.monitor.rectTransform.position-test.monitor.rectTransform.forward*.8f;camera.transform.LookAt(test.monitor.rectTransform.position,test.monitor.rectTransform.up);
        var hd=camera.gameObject.AddComponent<HDAdditionalCameraData>();hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;hd.allowDynamicResolution=false;
        pass=ticks=captureWait=0;last="";steps=new Stack<IEnumerator>();steps.Push(test.Cycle());
        File.WriteAllText("FilmDashboard.progress","VALIDATING PASS / HIGH FAIL / LOW FAIL / REMEASURE + APPROVAL\n");
        EditorApplication.update-=Tick;EditorApplication.update+=Tick;
    }
    static void Tick()
    {
        try
        {
            if(captureWait>0){if(--captureWait==0)Capture("FilmDashboard_"+(pass==0?"PASS":pass==1?"FAIL_HIGH":pass==2?"FAIL_LOW":"REVIEW")+".png");return;}
            for(int i=0;i<30;i++)
            {
                if(++ticks>30000)throw new Exception("Dashboard cycle timeout");
                if(steps.Count==0)
                {
                    Check(test.completed&&!test.failed,"Cycle did not complete");
                    if(pass==0){Check(test.CanProceed&&!test.lotHeld&&test.TryProceed(),"PASS dispatch gate failed");}
                    else if(pass<3)
                    {
                        Check(test.verdict=="FAIL"&&test.lotHeld&&!test.CanProceed&&!test.TryProceed()&&!test.ApproveRelease(),"FAIL was released");
                        Check(implant.LotBlocked,"Downstream implant HOLD gate missing");implant.StartCycle();Check(!implant.Running,"Held LOT started implantation");
                    }
                    else
                    {
                        Check(test.verdict=="PASS"&&test.lotHeld&&!test.CanProceed,"Remeasurement silently released HOLD");
                        Check(test.ApproveRelease()&&test.CanProceed&&!implant.LotBlocked&&test.TryProceed(),"Reviewed PASS could not be released");
                        Check(!test.result.Contains("HOLD"),"Released result retained stale HOLD label");
                        Capture("FilmDashboard_RELEASED.png");Finish();return;
                    }
                    pass++;test.demoHold=pass==1;test.demoLow=pass==2;steps.Push(test.Cycle());last="";continue;
                }
                var e=steps.Peek();if(!e.MoveNext()){steps.Pop();continue;}if(e.Current is IEnumerator nested)steps.Push(nested);
                if(last!=test.status)
                {
                    last=test.status;File.AppendAllText("FilmDashboard.progress",pass+" "+last+"\n");
                    if(last=="RESULT / DEMO DATA"){captureWait=2;return;}
                    if(last=="MEASURING 2 / 3 (DEMO)"&&pass==0){Capture("FilmDashboard_SCANNING.png");}
                }
            }
            EditorApplication.QueuePlayerLoopUpdate();
        }
        catch(Exception e){Fail(new Exception("Film dashboard failed at "+(test?test.status:"setup"),e));}
    }
    static void Finish()
    {
        EditorApplication.update-=Tick;test.ResetDashboardDemo();test.validationDelta=0;
        if(implant)implant.ResetPreview();
        UnityEngine.Object.DestroyImmediate(camera.gameObject);AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene());
        File.WriteAllText("FilmDashboard.result","FILM_DASHBOARD_OK\n3-site inclusive specification, outlier, NaN, incomplete data, invalid limits\nPASS / upper FAIL / lower FAIL / remeasure PASS on HOLD / review release\ndownstream implant start blocked for held LOT; original wafer slot return PASS\npressure/film values remain DEMO; no automatic rework or OHT dispatch\nbackup="+backup);
        Selection.activeGameObject=test.gameObject;
    }
    static void Fail(Exception e)
    {
        EditorApplication.update-=Tick;File.WriteAllText("FilmDashboard.result",e.ToString());Debug.LogException(e);
        if(camera)try{Capture("FilmDashboard_ERROR.png");}catch(Exception capture){Debug.LogException(capture);}
    }
    static void Capture(string path)
    {
        Canvas.ForceUpdateCanvases();
        Check(test.dashboard.waferPlot.canvasRenderer&&test.dashboard.trend.canvasRenderer,"Dashboard graphics renderer missing");
        Check(test.dashboard.waferPlot.drawnVertices>0&&test.dashboard.trend.drawnVertices>0,"Dashboard graph did not render");
        var rt=new RenderTexture(1440,1020,24);rt.Create();var old=RenderTexture.active;
        for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});
        RenderTexture.active=rt;var image=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();File.WriteAllBytes(path,image.EncodeToPNG());
        RenderTexture.active=old;rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(image);
    }
}
#endif
