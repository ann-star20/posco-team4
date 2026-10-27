#if UNITY_EDITOR
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;
using UnityEngine.UI;

public static class EllipsometerAnimationSetup
{
    const string Base="Assets/MOSFETInspection/";
    const string ScenePath=Base+"Scenes/MOSFETSmallFab_Corrected.unity";
    static EllipsometerCycle test;
    static Stack<IEnumerator> steps;
    static int ticks,pass,captureWait;
    static string last,captureName,backup;
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Requested;EditorApplication.update+=Requested;}
    static void Requested()
    {
        if(!File.Exists("EllipsometerAnimation.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("EllipsometerAnimation.once");
        try{Build();}catch(Exception e){Fail(e);}
    }
    static Transform Find(Transform root,string name)=>root.GetComponentsInChildren<Transform>(true).FirstOrDefault(t=>t.name==name)??throw new Exception("Missing node: "+name);
    static void MapMaterials(GameObject obj,Dictionary<string,Material> lookup)
    {
        foreach(var renderer in obj.GetComponentsInChildren<Renderer>())
            renderer.sharedMaterials=renderer.sharedMaterials.Select(m=>lookup.TryGetValue(m.name,out var mapped)?mapped:throw new Exception("Missing material: "+m.name)).ToArray();
    }
    [MenuItem("MOSFET Factory/Set Up Ellipsometer Animation")]
    public static void Build()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play first.");
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(current.isDirty&&!EditorSceneManager.SaveScene(current))throw new Exception("Current scene could not be saved.");
        EditorSceneManager.OpenScene(ScenePath);
        var previous=GameObject.Find("Ellipsometer_System");if(!previous)throw new Exception("Placed ellipsometer missing.");
        backup=AssetDatabase.GenerateUniqueAssetPath(Base+"Scenes/MOSFETSmallFab_BeforeEllipsometerAnimation.unity");
        if(!AssetDatabase.CopyAsset(ScenePath,backup))throw new Exception("Scene backup failed.");
        var model=(GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/FabEquipment/Ellipsometer_System.fbx"));
        PrefabUtility.UnpackPrefabInstance(model,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);
        model.transform.SetPositionAndRotation(previous.transform.position,previous.transform.rotation);model.transform.localScale=previous.transform.localScale;
        var materialMap=AssetDatabase.FindAssets("t:Material",new[]{Base+"Materials/Ellipsometer"}).Select(g=>AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(g))).ToDictionary(m=>m.name);
        MapMaterials(model,materialMap);
        UnityEngine.Object.DestroyImmediate(previous);model.name="Ellipsometer_System";
        var foup=(GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/OHT/FOUP_300mm_Concept.fbx"));
        PrefabUtility.UnpackPrefabInstance(foup,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);
        foup.name="Ellipsometer_FOUP_01";
        foup.transform.rotation=model.transform.rotation*Quaternion.AngleAxis(180,Vector3.forward);
        foup.transform.position+=Find(model.transform,"FOUP_Dock_01").position-Find(foup.transform,"LoadPort_Dock_Anchor").position;
        foup.transform.SetParent(model.transform,true);
        materialMap=AssetDatabase.FindAssets("t:Material",new[]{Base+"Materials/OHT"}).Select(g=>AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(g))).ToDictionary(m=>m.name);
        MapMaterials(foup,materialMap);
        var t=model.transform;test=model.AddComponent<EllipsometerCycle>();
        test.robot=Find(t,"Transfer_Robot");test.joint1=Find(t,"Joint_01_ANIM");test.joint2=Find(t,"Joint_02_ANIM");test.wrist=Find(t,"Wrist_ANIM");test.contact=Find(t,"Blade_Attach");
        test.wafer=Find(foup.transform,"Wafer_13");test.stage=Find(t,"Stage_Y_ANIM");test.stageTarget=Find(t,"Measurement_Position");
        test.equipmentDoor=Find(t,"LP1_Door_ANIM");test.carrierDoor=Find(foup.transform,"FOUP_Door_ANIM");
        test.armParts=new[]{"Arm_01","Arm_02","Wrist_Cap","Blade_Stem","Blade_Fork","Blade_Fork.001"}.Select(n=>Find(t,n).GetComponent<Renderer>()).ToArray();
        test.cutawayPanels=model.GetComponentsInChildren<Renderer>().Where(r=>r.name.StartsWith("Front_Upper")||r.name=="Roof"||r.name=="FOUP_Roof"||r.name=="FOUP_Back"||r.name.StartsWith("FOUP_Side")||EllipsometerCycle.InteriorTrim(r)).ToArray();
        test.overview=GameObject.Find("FAB_OVERVIEW_CAMERA").GetComponent<Camera>();
        foreach(var old in UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsSortMode.None).Where(c=>c.name=="ELLIPSOMETER_DETAIL_CAMERA").ToArray())UnityEngine.Object.DestroyImmediate(old.gameObject);
        var camera=new GameObject("ELLIPSOMETER_DETAIL_CAMERA").AddComponent<Camera>();
        var hd=camera.gameObject.AddComponent<HDAdditionalCameraData>();hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;
        var centre=model.transform.position+model.transform.TransformDirection(new Vector3(0,.25f,1.35f));var front=-model.transform.TransformDirection(Vector3.up);
        camera.transform.position=centre+front*4.0f+Vector3.up*2.3f+model.transform.TransformDirection(Vector3.right)*2;
        camera.transform.LookAt(centre);camera.fieldOfView=43;camera.nearClipPlane=.02f;camera.enabled=false;test.detail=camera;
        foreach(var renderer in model.GetComponentsInChildren<Renderer>().Where(r=>r.name.StartsWith("HMI_Title")||r.name.StartsWith("HMI_Thickness")||r.name.StartsWith("HMI_Ready")||r.name.StartsWith("HMI_Disclaimer")))renderer.enabled=false;
        var screen=Find(t,"HMI_Screen");
        var panel=new GameObject("Ellipsometer_Live_HMI",typeof(RectTransform),typeof(Canvas));panel.transform.SetParent(model.transform,true);
        var canvas=panel.GetComponent<Canvas>();canvas.renderMode=RenderMode.WorldSpace;
        panel.transform.position=screen.position+front*.012f;panel.transform.rotation=Quaternion.LookRotation(-front,Vector3.up);panel.transform.localScale=Vector3.one*(.001f/model.transform.lossyScale.x);
        var rect=panel.GetComponent<RectTransform>();rect.sizeDelta=new Vector2(480,340);
        var textObject=new GameObject("Result_Text",typeof(RectTransform),typeof(CanvasRenderer),typeof(Text));textObject.transform.SetParent(panel.transform,false);
        var text=textObject.GetComponent<Text>();text.font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");text.fontSize=35;text.alignment=TextAnchor.MiddleCenter;text.color=Color.white;
        text.horizontalOverflow=HorizontalWrapMode.Wrap;text.verticalOverflow=VerticalWrapMode.Overflow;
        text.rectTransform.anchorMin=Vector2.zero;text.rectTransform.anchorMax=Vector2.one;text.rectTransform.offsetMin=text.rectTransform.offsetMax=Vector2.zero;test.monitor=text;
        test.recipe=FilmDashboardSetup.LoadRecipe();FilmInspectionDashboard.Install(test);
        var downstream=GameObject.Find("Ion_Implanter").GetComponent<IonImplantCycle>();downstream.lotQualityGate=test;downstream.incomingLotId=test.lotId;
        var beamMat=new Material(Shader.Find("HDRP/Unlit"));beamMat.SetColor("_UnlitColor",new Color(.05f,.8f,1));
        var beamPath=Base+"Materials/Ellipsometer/Illustrative_Beam.mat";
        var existingBeam=AssetDatabase.LoadAssetAtPath<Material>(beamPath);
        if(existingBeam){UnityEngine.Object.DestroyImmediate(beamMat);beamMat=existingBeam;}else AssetDatabase.CreateAsset(beamMat,beamPath);
        test.beams=new[]{"Light_Source_Lens","Optical_Detector_Lens"}.Select(name=>
        {
            var line=new GameObject("Illustrative_Optical_Path").AddComponent<LineRenderer>();line.transform.SetParent(t,true);line.useWorldSpace=true;
            line.positionCount=2;line.SetPosition(0,Find(t,name).position);line.SetPosition(1,test.stageTarget.position);
            line.startWidth=line.endWidth=.002f;line.sharedMaterial=beamMat;line.enabled=false;return line;
        }).ToArray();
        test.Initialize();test.validationDelta=1f/30;test.demoHold=false;
        pass=ticks=captureWait=0;last="";steps=new Stack<IEnumerator>();steps.Push(test.Cycle());
        foreach(var renderer in test.cutawayPanels)renderer.enabled=false;
        File.WriteAllText("EllipsometerAnimation.progress","VALIDATING PASS, HOLD AND RESTART\n");
        EditorApplication.update-=TestStep;EditorApplication.update+=TestStep;
    }
    static void TestStep()
    {
        try
        {
            if(captureWait>0){if(--captureWait==0)Capture(test.detail,captureName);return;}
            for(int i=0;i<12;i++)
            {
                if(++ticks>15000)throw new Exception("Cycle validation timed out.");
                if(steps.Count==0)
                {
                    if(!test.completed||test.failed)throw new Exception("Cycle did not complete.");
                    string expected=pass==0?"PASS":"HOLD";
                    if(!test.result.Contains(expected))throw new Exception("Wrong demo verdict.");
                    if(pass==0){pass=1;test.demoHold=true;steps.Push(test.Cycle());last="";continue;}
                    Finish();return;
                }
                var step=steps.Peek();if(!step.MoveNext()){steps.Pop();continue;}
                if(step.Current is IEnumerator nested)steps.Push(nested);
                if(last!=test.status)
                {
                    last=test.status;File.AppendAllText("EllipsometerAnimation.progress",pass+" "+last+"\n");
                    if(pass==0&&(last=="WAFER ON STAGE"||last=="RESULT / DEMO DATA"))
                    {captureName=last.StartsWith("WAFER")?"Ellipsometer_WaferOnStage.png":"Ellipsometer_DemoResult.png";captureWait=2;return;}
                }
            }
            EditorApplication.QueuePlayerLoopUpdate();
        }
        catch(Exception e){Fail(new Exception("Ellipsometer validation failed at "+(test?test.status:"setup"),e));}
    }
    static void Finish()
    {
        EditorApplication.update-=TestStep;test.ResetDashboardDemo();test.validationDelta=0;test.demoHold=false;
        foreach(var renderer in test.cutawayPanels)renderer.enabled=true;
        AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene());
        File.WriteAllText("EllipsometerAnimation.result","ELLIPSOMETER_ANIMATION_OK\nPASS/HOLD cycles, restart, IK, panel-opening envelope and wafer return validated\nmanual start only; sample values are DEMO, no TCAD connection\nbackup="+backup);
        Selection.activeGameObject=test.gameObject;
        if(SceneView.lastActiveSceneView)SceneView.lastActiveSceneView.LookAt(test.stageTarget.position+Vector3.up*.2f,test.detail.transform.rotation,4f);
    }
    static void Fail(Exception e)
    {
        EditorApplication.update-=TestStep;
        File.WriteAllText("EllipsometerAnimation.result",e.ToString());Debug.LogException(e);
        if(test){try{Capture(test.detail,"Ellipsometer_Error.png");test.ResetPreview();test.validationDelta=0;}catch(Exception resetError){Debug.LogException(resetError);}}
    }
    static void Capture(Camera camera,string file)
    {
        var rt=new RenderTexture(1600,1200,24);rt.Create();var old=RenderTexture.active;
        for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});
        RenderTexture.active=rt;var image=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();
        File.WriteAllBytes(file,image.EncodeToPNG());RenderTexture.active=old;rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(image);
    }
}
#endif


