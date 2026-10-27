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

public static class InstallIntegratedOxidation
{
    const string Folder="Assets/MOSFETInspection/";
    const string ScenePath=Folder+"Scenes/MOSFETSmallFab_Corrected.unity";
    [Serializable]class Record{public string name;public float[] color;public float metallic;public float roughness;}
    [Serializable]class Records{public Record[] items;}
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Requested;EditorApplication.update+=Requested;}
    static void Requested()
    {
        if(!File.Exists("InstallOxidation.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("InstallOxidation.once");
        try{Install();}catch(Exception e){File.WriteAllText("InstallOxidation.result",e.ToString());Debug.LogException(e);}
    }
    static Transform Find(Transform root,string name)
    {var t=root.GetComponentsInChildren<Transform>(true).FirstOrDefault(x=>x.name==name);if(!t)throw new Exception("Missing integrated model node: "+name);return t;}
    static Bounds Bounds(GameObject root)
    {var rs=root.GetComponentsInChildren<Renderer>();var b=rs[0].bounds;foreach(var r in rs)b.Encapsulate(r.bounds);return b;}
    static Material Material(Record record)
    {
        string folder=Folder+"Materials/IntegratedOxidation";Directory.CreateDirectory(folder);string path=folder+"/"+record.name+".mat";
        var m=AssetDatabase.LoadAssetAtPath<Material>(path);if(!m){m=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(m,path);}
        var c=record.color;m.SetColor("_BaseColor",new Color(c[0],c[1],c[2],1).gamma);m.SetFloat("_Metallic",record.metallic);m.SetFloat("_Smoothness",1-record.roughness);EditorUtility.SetDirty(m);return m;
    }
    [MenuItem("MOSFET Factory/Install Integrated Oxidation")]
    public static void Install()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play before installing.");
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(current.isDirty&&!EditorSceneManager.SaveScene(current))throw new Exception("Cannot save current scene.");
        EditorSceneManager.OpenScene(ScenePath,OpenSceneMode.Single);
        string backup=AssetDatabase.GenerateUniqueAssetPath(Folder+"Scenes/MOSFETSmallFab_BeforeOxidationIntegration.unity");
        if(!AssetDatabase.CopyAsset(ScenePath,backup))throw new Exception("Scene backup failed.");
        File.WriteAllText("InstallOxidation.progress","BACKUP "+backup);
        var oldLoader=GameObject.Find("EFEM");var oldFurnace=GameObject.Find("Oxidation_Furnace");
        var prior=GameObject.Find("Oxidation_System_Integrated");
        if(!oldLoader&&!prior)throw new Exception("Existing EFEM not found in cleanroom.");
        var reference=oldLoader?oldLoader:prior;var area=Bounds(reference);
        if(oldFurnace)area.Encapsulate(Bounds(oldFurnace));
        float front=oldLoader?Bounds(oldLoader).min.z:area.min.z;
        var asset=AssetDatabase.LoadAssetAtPath<GameObject>(Folder+"Models/FabEquipment/Oxidation_System.fbx");
        if(!asset)throw new Exception("Integrated FBX import pending.");
        var model=(GameObject)PrefabUtility.InstantiatePrefab(asset);model.name="Oxidation_System_Integrated";
        // The wafer changes parent between gripper, boat, and FOUP during validation and playback.
        PrefabUtility.UnpackPrefabInstance(model,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);
        model.transform.rotation=reference.transform.rotation;
        var b=Bounds(model);model.transform.position+=new Vector3(area.center.x-b.center.x,-b.min.y,front-b.min.z);
        var records=JsonUtility.FromJson<Records>(File.ReadAllText(Folder+"Models/FabEquipment/Oxidation_materials.json")).items;
        foreach(var r in model.GetComponentsInChildren<Renderer>())
            r.sharedMaterials=r.sharedMaterials.Select(m=>Material(records.FirstOrDefault(x=>x.name==m.name)??throw new Exception("Unmapped material "+m.name))).ToArray();
        var controller=model.AddComponent<IntegratedOxidationCycle>();var t=model.transform;
        controller.robot=Find(t,"Wafer_Robot_ROOT");controller.joint1=Find(t,"Robot_Joint_01_ANIM");controller.joint2=Find(t,"Robot_Joint_02_ANIM");controller.wrist=Find(t,"Robot_Wrist_ANIM");controller.contact=Find(t,"Unity_Blade_Contact");
        controller.wafer=Find(t,"Wafer_13");controller.boat=Find(t,"Furnace_Boat_Elevator");controller.boatTarget=Find(t,"Unity_Boat_Load_Contact");controller.boatUp=Find(t,"Boat_Up_Target");controller.carrierDoor=Find(t,"FOUP_Door_ANIM");
        controller.equipmentDoors=Enumerable.Range(1,3).Select(i=>Find(t,"REF_LP"+i+"_Door_ANIM")).ToArray();controller.wristLimit=Find(t,"Unity_Wrist_Limit");
        controller.armRenderers=new[]{"Robot_Arm_01","Robot_Arm_02","Robot_Wrist_Housing"}.Select(n=>Find(t,n).GetComponent<Renderer>()).ToArray();
        controller.cutawayPanels=model.GetComponentsInChildren<Renderer>().Where(r=>r.name.StartsWith("REF_Upper")||r.name.StartsWith("REF_Vent")||r.name=="Loader_Front_Enclosure_Three_Openings"||r.name=="REF_CenterFascia"||r.name=="EFEM_TopHeader"||r.name=="REF_SystemMark"||r.name=="Furnace_Upper_Cabinet"||r.name=="Furnace_Top_Cover"||r.name=="FOUP_Roof").ToArray();
        controller.overview=GameObject.Find("FAB_OVERVIEW_CAMERA").GetComponent<Camera>();
        foreach(var previous in UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsSortMode.None).Where(c=>c.name=="OXIDATION_DETAIL_CAMERA").ToArray())UnityEngine.Object.DestroyImmediate(previous.gameObject);
        var camera=new GameObject("OXIDATION_DETAIL_CAMERA").AddComponent<Camera>();camera.gameObject.AddComponent<HDAdditionalCameraData>();
        var centre=Bounds(model).center;var frontDir=Find(t,"LoadPort_02_Deck").position-controller.robot.position;frontDir.y=0;frontDir.Normalize();
        camera.transform.position=centre+frontDir*5.5f+Vector3.up*4f+Vector3.right*2;camera.transform.LookAt(centre);camera.fieldOfView=45;camera.nearClipPlane=.02f;camera.enabled=false;controller.detail=camera;
        b=Bounds(model);
        if(b.min.x< -7.9f||b.max.x>7.9f||b.max.z>5.9f||Mathf.Abs(b.min.y)>.005f)throw new Exception("Integrated assembly exceeds cleanroom or is not grounded: "+b);
        if(oldLoader)UnityEngine.Object.DestroyImmediate(oldLoader);if(oldFurnace)UnityEngine.Object.DestroyImmediate(oldFurnace);if(prior)UnityEngine.Object.DestroyImmediate(prior);
        File.WriteAllText("InstallOxidation.progress","VALIDATING "+b);
        controller.Initialize();controller.validationDelta=1f/30;
        int ticks=0;string last="";var stack=new Stack<IEnumerator>();stack.Push(controller.Cycle());
        try
        {
            while(stack.Count>0)
            {
                if(++ticks>30000)throw new Exception("Animation validation did not finish.");
                var task=stack.Peek();if(!task.MoveNext()){stack.Pop();continue;}
                if(task.Current is IEnumerator child)stack.Push(child);
                if(last!=controller.status)
                {
                    last=controller.status;File.AppendAllText("InstallOxidation.progress","\n"+last);
                    if(last=="WAFER ON BOAT"||last=="OXIDATION / SIMULATED")
                    {
                        foreach(var r in controller.cutawayPanels)r.enabled=false;
                        Capture(camera,last.StartsWith("WAFER")?"Oxidation_Loaded.png":"Oxidation_BoatUp.png");
                        foreach(var r in controller.cutawayPanels)r.enabled=true;
                    }
                }
            }
            if(!controller.completed)throw new Exception("Cycle did not reach complete state.");
        }
        catch(Exception e){Capture(camera,"Oxidation_ValidationError.png");throw new Exception("Cycle validation failed at "+controller.status,e);}
        controller.ResetPreview();
        foreach(var r in controller.cutawayPanels)r.enabled=true;
        AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),ScenePath);
        Capture(controller.overview,"Cleanroom_IntegratedOxidation.png");
        File.WriteAllText("InstallOxidation.result","INTEGRATED_OXIDATION_OK\n"+ScenePath+"\nbackup="+backup+"\ncycle=PASS / placement, IK, arm-wall envelope, wafer return checked\nmanual start only; oxidation is simulated");
        Selection.activeGameObject=model;
    }
    static void Capture(Camera camera,string file)
    {
        var rt=new RenderTexture(1300,950,24);rt.Create();var old=RenderTexture.active;
        for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});
        RenderTexture.active=rt;var image=new Texture2D(1300,950,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,1300,950),0,0);image.Apply();File.WriteAllBytes(file,image.EncodeToPNG());RenderTexture.active=old;rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(image);
    }
}
#endif

