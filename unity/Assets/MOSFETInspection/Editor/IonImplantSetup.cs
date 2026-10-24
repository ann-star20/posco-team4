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

public static class IonImplantSetup
{
    const string Base="Assets/MOSFETInspection/";
    const string ScenePath=Base+"Scenes/MOSFETSmallFab_Corrected.unity";
    [Serializable] class Record {public string name;public float[] color;public float metallic,roughness;}
    [Serializable] class Records {public Record[] items;}
    static IonImplantCycle test;
    static Stack<IEnumerator> steps;
    static int ticks,run,captureWait;
    static string last,backup,captureName;
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Requested;EditorApplication.update+=Requested;}
    static void Requested()
    {
        if(!File.Exists("IonAnimation.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("IonAnimation.once");try{Build();}catch(Exception e){Fail(e);}
    }
    static Transform Find(Transform t,string name)=>t.GetComponentsInChildren<Transform>(true).FirstOrDefault(o=>o.name==name)??throw new Exception("Missing "+name);
    static Renderer[] Parts(Transform root,string prefix)=>root.GetComponentsInChildren<Renderer>().Where(r=>r.name.StartsWith(prefix+"_Arm")||r.name.StartsWith(prefix+"_Blade")||r.name==prefix+"_WristCap").ToArray();
    static IonImplantCycle.Arm Arm(Transform t,string prefix)=>new IonImplantCycle.Arm{root=Find(t,prefix),elbowSign=prefix=="VAC"?1:-1,j1=Find(t,prefix+"_Joint1"),j2=Find(t,prefix+"_Joint2"),wrist=Find(t,prefix+"_Wrist"),contact=Find(t,prefix+"_Contact"),parts=Parts(t,prefix)};
    [MenuItem("MOSFET Factory/Set Up Ion Implant Animation")]
    public static void Build()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play first");
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();if(current.isDirty&&!EditorSceneManager.SaveScene(current))throw new Exception("Scene save failed");
        EditorSceneManager.OpenScene(ScenePath);backup=AssetDatabase.GenerateUniqueAssetPath(Base+"Scenes/MOSFETSmallFab_BeforeIonAnimation.unity");
        if(!AssetDatabase.CopyAsset(ScenePath,backup))throw new Exception("Scene backup failed");
        AssetDatabase.ImportAsset(Base+"Models/FabEquipment/Ion_Implanter_Animated.fbx",ImportAssetOptions.ForceSynchronousImport|ImportAssetOptions.ForceUpdate);
        var previous=GameObject.Find("Ion_Implanter");if(!previous)throw new Exception("Existing implanter missing");
        var model=(GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/FabEquipment/Ion_Implanter_Animated.fbx"));
        PrefabUtility.UnpackPrefabInstance(model,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);
        model.transform.SetPositionAndRotation(previous.transform.position,previous.transform.rotation);model.transform.localScale=previous.transform.localScale;
        var folder=Base+"Materials/IonAnimation";Directory.CreateDirectory(folder);
        var records=JsonUtility.FromJson<Records>(File.ReadAllText(Base+"Models/FabEquipment/Ion_Animation_materials.json")).items;
        foreach(var r in model.GetComponentsInChildren<Renderer>())r.sharedMaterials=r.sharedMaterials.Select(original=>
        {
            var rec=records.First(a=>a.name==original.name);string path=folder+"/"+rec.name+".mat";
            var m=AssetDatabase.LoadAssetAtPath<Material>(path);if(!m){m=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(m,path);}
            m.SetColor("_BaseColor",new Color(rec.color[0],rec.color[1],rec.color[2],1).gamma);m.SetFloat("_Metallic",rec.metallic);m.SetFloat("_Smoothness",1-rec.roughness);EditorUtility.SetDirty(m);return m;
        }).ToArray();
        UnityEngine.Object.DestroyImmediate(previous);model.name="Ion_Implanter";var t=model.transform;test=model.AddComponent<IonImplantCycle>();
        var metrology=GameObject.Find("Ellipsometer_System").GetComponent<EllipsometerCycle>();
        if(metrology.dashboard){test.lotQualityGate=metrology;test.incomingLotId=metrology.lotId;}
        for(int i=1;i<=4;i++)
        {
            var foup=(GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/OHT/FOUP_300mm_Concept.fbx"));
            PrefabUtility.UnpackPrefabInstance(foup,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);foup.name="Ion_FOUP_"+i.ToString("D2");
            foup.transform.rotation=t.rotation*Quaternion.AngleAxis(180,Vector3.forward);
            foup.transform.position+=Find(t,"FOUP_Dock_"+i.ToString("D2")).position-Find(foup.transform,"LoadPort_Dock_Anchor").position;
            foup.transform.SetParent(t,true);
            var map=AssetDatabase.FindAssets("t:Material",new[]{Base+"Materials/OHT"}).Select(g=>AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(g))).ToDictionary(m=>m.name);
            foreach(var r in foup.GetComponentsInChildren<Renderer>())r.sharedMaterials=r.sharedMaterials.Select(m=>map[m.name]).ToArray();
            if(i==2){test.carrier=foup.transform;test.carrierDoor=Find(foup.transform,"FOUP_Door_ANIM");test.wafer=Find(foup.transform,"Wafer_13");}
        }
        test.frameOrigin=Find(t,"Design_Origin");test.frameX=Find(t,"Design_X");test.frameY=Find(t,"Design_Y");
        test.carrier.position-=(test.frameY.position-test.frameOrigin.position).normalized*.06f;
        test.atmosphere=Arm(t,"ATM");test.vacuum=Arm(t,"VAC");
        test.portDoor=Find(t,"Port_02_Door_ANIM");test.outerDoor=Find(t,"LL_Outer_Door_ANIM");test.innerDoor=Find(t,"LL_Inner_Door_ANIM");test.processDoor=Find(t,"Process_Door_ANIM");
        test.alignTarget=Find(t,"Aligner_Target");test.lockTarget=Find(t,"LoadLock_Chuck_Target");test.stageTarget=Find(t,"Implant_Stage_Target");test.stage=Find(t,"Implant_Stage");test.tilt=Find(t,"Implant_Tilt_Pivot");
        test.cutawayPanels=t.GetComponentsInChildren<Renderer>().Where(r=>r.name.StartsWith("Cut_")||r.name=="Rear_Tall_Housing"||r.name.StartsWith("Rear_Service")||r.name=="FOUP_Roof"||r.name=="FOUP_Back"||r.name.StartsWith("FOUP_Side")||IonImplantCycle.InteriorTrim(r)).ToArray();
        test.overview=GameObject.Find("FAB_OVERVIEW_CAMERA").GetComponent<Camera>();
        foreach(var old in UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsSortMode.None).Where(c=>c.name.StartsWith("ION_")).ToArray())UnityEngine.Object.DestroyImmediate(old.gameObject);
        test.Initialize();
        test.detail=CameraAt("ION_DETAIL_CAMERA",test.World(5,-7,4.4f),test.World(-.3f,.2f,1.4f),43);
        test.internalView=CameraAt("ION_INTERNAL_CAMERA",test.World(3,-4,5.8f),test.World(-.35f,1.25f,1.4f),45);
        var screen=Find(t,"HMI_Screen");var front=-(test.frameY.position-test.frameOrigin.position).normalized;
        var panel=new GameObject("Ion_Live_HMI",typeof(RectTransform),typeof(Canvas));panel.transform.SetParent(t,true);
        panel.GetComponent<Canvas>().renderMode=RenderMode.WorldSpace;panel.transform.position=screen.position+front*.012f;panel.transform.rotation=Quaternion.LookRotation(-front,Vector3.up);panel.transform.localScale=Vector3.one*(.001f/t.lossyScale.x);panel.GetComponent<RectTransform>().sizeDelta=new Vector2(600,550);
        var textObj=new GameObject("Process_Text",typeof(RectTransform),typeof(CanvasRenderer),typeof(Text));textObj.transform.SetParent(panel.transform,false);
        var text=textObj.GetComponent<Text>();text.font=Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");text.fontSize=33;text.alignment=TextAnchor.MiddleCenter;text.color=Color.white;text.rectTransform.anchorMin=Vector2.zero;text.rectTransform.anchorMax=Vector2.one;text.rectTransform.offsetMin=text.rectTransform.offsetMax=Vector2.zero;test.monitor=text;IonImplantDashboard.Install(test);
        var matPath=folder+"/Beam_Illustration.mat";var beamMat=AssetDatabase.LoadAssetAtPath<Material>(matPath);
        if(!beamMat){beamMat=new Material(Shader.Find("HDRP/Unlit"));beamMat.SetColor("_UnlitColor",new Color(.1f,.65f,1));AssetDatabase.CreateAsset(beamMat,matPath);}
        var line=new GameObject("Ion_Beam_Illustration").AddComponent<LineRenderer>();line.transform.SetParent(t,true);line.useWorldSpace=true;line.positionCount=2;line.SetPosition(0,Find(t,"Beam_Start").position);line.SetPosition(1,Find(t,"Beam_End").position);line.startWidth=line.endWidth=.004f;line.sharedMaterial=beamMat;line.enabled=false;test.beam=line;
        test.ResetPreview();test.validationDelta=1f/30;steps=new Stack<IEnumerator>();steps.Push(test.Cycle());ticks=run=captureWait=0;last="";
        File.WriteAllText("IonAnimation.progress","VALIDATING TWO CYCLES / GATE INTERLOCKS / IK / WAFER RETURN\n");
        test.ShowInside();EditorApplication.update-=Tick;EditorApplication.update+=Tick;
    }
    static Camera CameraAt(string name,Vector3 eye,Vector3 target,float fov)
    {
        var c=new GameObject(name).AddComponent<Camera>();c.transform.position=eye;c.transform.LookAt(target);c.fieldOfView=fov;c.nearClipPlane=.02f;c.enabled=false;c.allowDynamicResolution=false;
        var hd=c.gameObject.AddComponent<HDAdditionalCameraData>();hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;hd.allowDynamicResolution=false;return c;
    }
    static void Tick()
    {
        try
        {
            if(captureWait>0){if(--captureWait==0)Capture(test.internalView,captureName);return;}
            for(int i=0;i<20;i++)
            {
                if(++ticks>24000)throw new Exception("Cycle test timeout");
                if(steps.Count==0)
                {
                    IonImplantCycle.Require(test.completed&&!test.failed,"Cycle incomplete");
                    if(run++==0){steps.Push(test.Cycle());last="";continue;}
                    EditorApplication.update-=Tick;test.ResetPreview();test.validationDelta=0;test.ShowInside();test.SelectCamera(test.detail);
                    AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene());
                    Capture(test.detail,"Ion_Exterior.png");
                    File.WriteAllText("IonAnimation.result","ION_ANIMATION_OK\n2 complete cycles; IK/envelope/interlocks/original slot return PASS\nmanual start; pressure/dose are simulated; TCAD offline\nbackup="+backup);Selection.activeGameObject=test.gameObject;return;
                }
                var e=steps.Peek();if(!e.MoveNext()){steps.Pop();continue;}if(e.Current is IEnumerator nested)steps.Push(nested);
                if(last!=test.status)
                {
                    last=test.status;File.AppendAllText("IonAnimation.progress",run+" "+last+"\n");
                    if(run==0&&(last=="PUMP DOWN / SIMULATION"||last=="IMPLANT / SIMULATION")){captureName=last.StartsWith("PUMP")?"Ion_LoadLock.png":"Ion_Implant.png";captureWait=2;return;}
                }
            }
            EditorApplication.QueuePlayerLoopUpdate();
        }
        catch(Exception e){Fail(new Exception("Ion cycle failed at "+(test?test.status:"setup"),e));}
    }
    static void Fail(Exception e)
    {
        EditorApplication.update-=Tick;File.WriteAllText("IonAnimation.result",e.ToString());Debug.LogException(e);
        if(test&&test.internalView){Capture(test.internalView,"Ion_Error.png");test.validationDelta=0;}
    }
    static void Capture(Camera c,string path)
    {
        var rt=new RenderTexture(1600,1200,24);rt.Create();var old=RenderTexture.active;
        for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(c,new RenderPipeline.StandardRequest{destination=rt});
        RenderTexture.active=rt;var image=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();File.WriteAllBytes(path,image.EncodeToPNG());
        RenderTexture.active=old;rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(image);
    }
}
#endif

