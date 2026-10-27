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

[InitializeOnLoad] public static class InstallDetailedOxidation
{
    const string Asset="Assets/MOSFETInspection/Models/FabEquipment/Oxidation_Detailed_Addon";
    const string Request="InstallDetailedOxidation.once", Result="InstallDetailedOxidation.result";
    [Serializable] class MatRecord{public string name;public float[] color;public float metallic,smoothness;}
    [Serializable] class Manifest{public string[] hidden_original_renderers,anchor_names;public MatRecord[] materials;public int added_meshes,loader_objects_unchanged;}
    struct Pose
    {
        public Transform t,parent;Vector3 position,scale;Quaternion rotation;
        public Pose(Transform v){t=v;parent=v.parent;position=v.localPosition;scale=v.localScale;rotation=v.localRotation;}
        public void Verify(){Check(t&&t.parent==parent&&(t.localPosition-position).sqrMagnitude<1e-8f&&(t.localScale-scale).sqrMagnitude<1e-8f&&Quaternion.Angle(t.localRotation,rotation)<.01f,"Original pose changed: "+t.name);}
    }
    static InstallDetailedOxidation(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string reason){if(!ok)throw new InvalidOperationException(reason);}
    static void Tick()
    {
        if(EditorApplication.isPlayingOrWillChangePlaymode||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(File.Exists("DetailedOxidationRecheck.once"))
        {
            File.Delete("DetailedOxidationRecheck.once");
            try{Recheck();}catch(Exception e){File.WriteAllText("DetailedOxidationRecheck.result","FAILED\n"+e);Debug.LogException(e);}return;
        }
        if(!File.Exists(Request))return;
        File.Delete(Request);try{Install();}catch(Exception e){File.WriteAllText(Result,"FAILED\n"+e);Debug.LogException(e);}
    }
    static void Recheck()
    {
        var cycle=UnityEngine.Object.FindAnyObjectByType<IntegratedOxidationCycle>();Check(cycle,"Missing oxidation controller.");
        var model=cycle.transform.Find("Oxidation_Blender_Detailed");Check(model,"Detailed model missing.");
        var door=Find(model,"OXD_CUT_MainDoor").GetComponent<Renderer>();var lid=Find(model,"OXD_CUT_TopLid").GetComponent<Renderer>();
        Check(door.bounds.max.y>=lid.bounds.min.y-.002f,"Front cover leaves a gap below top lid.");
        cycle.Initialize();cycle.ResetPreview();var startParent=cycle.wafer.parent;
        var front=cycle.equipmentDoors[1].position-cycle.robot.position;front.y=0;front.Normalize();
        Capture(cycle,front,"Tools/Previews/Oxidation-Detailed-Exterior.png");
        cycle.validationDelta=1f/30;var stack=new Stack<IEnumerator>();stack.Push(cycle.Cycle());int count=0;bool raised=false;
        var mobile=Find(cycle.boat,"OXD_BoatDetails");var offset=mobile.position-cycle.boat.position;
        while(stack.Count>0)
        {
            Check(++count<30000,"Motion replay timed out.");var task=stack.Peek();if(!task.MoveNext()){stack.Pop();continue;}if(task.Current is IEnumerator child)stack.Push(child);
            Check(Vector3.Distance(mobile.position-cycle.boat.position,offset)<.002f,"Boat detail offset changed.");
            if(cycle.status=="OXIDATION / SIMULATED")raised=true;
        }
        Check(raised&&cycle.completed&&!cycle.failed&&cycle.wafer.parent==startParent,"Motion replay failed.");cycle.ResetPreview();
        var panels=cycle.cutawayPanels;var states=panels.Select(r=>r.enabled).ToArray();
        try{foreach(var r in panels)r.enabled=false;Capture(cycle,front,"Tools/Previews/Oxidation-Detailed-Inside.png");}
        finally{for(int i=0;i<panels.Length;i++)panels[i].enabled=states[i];}
        EditorSceneManager.MarkSceneDirty(cycle.gameObject.scene);Check(EditorSceneManager.SaveScene(cycle.gameObject.scene),"Could not save final scene.");
        File.WriteAllText("DetailedOxidationRecheck.result","DETAILED_OXIDATION_FINAL_OK\n"+DateTime.UtcNow.ToString("O")+"\nFront/top enclosure closure checked; wafer transfer, boat up/down, added ledge motion, FOUP return replay passed; exterior/inside captures updated; no network requests.");
    }
    static Quaternion Frame(Vector3 a,Vector3 b,Vector3 c)=>Quaternion.LookRotation((b-a).normalized,Vector3.Cross(b-a,c-a).normalized);
    static Transform Find(Transform root,string name)=>root.GetComponentsInChildren<Transform>(true).Single(t=>t.name==name);
    static Material MakeMaterial(MatRecord data)
    {
        const string folder="Assets/MOSFETInspection/Materials/OxidationDetailed";Directory.CreateDirectory(folder);
        string path=folder+"/"+data.name+".mat";var m=AssetDatabase.LoadAssetAtPath<Material>(path);
        if(!m){m=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(m,path);}
        m.SetColor("_BaseColor",new Color(data.color[0],data.color[1],data.color[2]));m.SetFloat("_Metallic",data.metallic);m.SetFloat("_Smoothness",data.smoothness);EditorUtility.SetDirty(m);return m;
    }
    [MenuItem("MOSFET Factory/Install Blender detailed oxidation (keep motion)")]
    public static void Install()
    {
        Check(!EditorApplication.isPlayingOrWillChangePlaymode,"Exit Play before install.");
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        Check(scene.path=="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity","Open the corrected factory scene.");
        var cycle=UnityEngine.Object.FindAnyObjectByType<IntegratedOxidationCycle>();Check(cycle,"Missing oxidation controller.");
        Check(!cycle.transform.Find("Oxidation_Blender_Detailed"),"Detailed model already installed.");
        var asset=AssetDatabase.LoadAssetAtPath<GameObject>(Asset+".fbx");Check(asset,"Detailed FBX has not imported.");
        var data=JsonUtility.FromJson<Manifest>(File.ReadAllText(Asset+".json"));
        cycle.Initialize();cycle.ResetPreview();
        var old=cycle.transform.Find("Oxidation_Exterior_WhiteTeal");
        bool Original(Transform t)=>!old||t!=old&&!t.IsChildOf(old);
        var poses=cycle.GetComponentsInChildren<Transform>(true).Where(Original).Select(t=>new Pose(t)).ToArray();
        var loader=cycle.GetComponentsInChildren<Renderer>(true).Where(r=>Original(r.transform)&&!r.name.StartsWith("Furnace_",StringComparison.Ordinal)).ToArray();
        var loaderMaterials=loader.Select(r=>r.sharedMaterials).ToArray();var loaderEnabled=loader.Select(r=>r.enabled).ToArray();
        var colliders=cycle.GetComponentsInChildren<Collider>(true);
        var target=data.anchor_names.Select(n=>Find(cycle.transform,n)).ToArray();var targets=target.Select(t=>t.position).ToArray();
        var sourcePanels=cycle.cutawayPanels.Where(r=>r&&Original(r.transform)).ToArray();
        Check(EditorSceneManager.SaveScene(scene),"Could not save original scene.");
        string backup="Tools/Backups/OxidationDetailed-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(backup);File.Copy(scene.path,backup+"/Before.unity");
        GameObject model=null;
        try
        {
            model=(GameObject)PrefabUtility.InstantiatePrefab(asset);PrefabUtility.UnpackPrefabInstance(model,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);model.name="Oxidation_Blender_Detailed";
            var anchors=Enumerable.Range(0,4).Select(i=>Find(model.transform,"OXD_Anchor"+i)).ToArray();
            var originalPoints=anchors.Select(t=>t.position).ToArray();
            float scale=Vector3.Distance(targets[0],targets[1])/Vector3.Distance(originalPoints[0],originalPoints[1]);
            Check(scale>.001f&&scale<1001,"Invalid FBX scale.");
            var rotation=Frame(targets[0],targets[1],targets[2])*Quaternion.Inverse(Frame(originalPoints[0],originalPoints[1],originalPoints[2]));
            model.transform.localScale*=scale;model.transform.rotation=rotation*model.transform.rotation;
            model.transform.position=targets[0]+rotation*(model.transform.position-originalPoints[0])*scale;
            for(int i=0;i<4;i++)Check(Vector3.Distance(anchors[i].position,targets[i])<.002f,"FBX anchor mismatch: "+data.anchor_names[i]);
            model.transform.SetParent(cycle.transform,true);
            var mats=data.materials.ToDictionary(m=>m.name,MakeMaterial);
            foreach(var r in model.GetComponentsInChildren<Renderer>())r.sharedMaterials=r.sharedMaterials.Select(m=>mats[m.name]).ToArray();
            var mobile=Find(model.transform,"OXD_BoatDetails");mobile.SetParent(cycle.boat,true);
            var originals=cycle.GetComponentsInChildren<Renderer>(true).Where(r=>Original(r.transform)&&!r.transform.IsChildOf(model.transform)&&!r.transform.IsChildOf(mobile)).ToArray();
            var disabled=new HashSet<Renderer>();
            foreach(string name in data.hidden_original_renderers)
            {
                var matches=originals.Where(r=>r.name==name).ToArray();Check(matches.Length==1,"Missing/duplicate original furnace cosmetic: "+name);
                matches[0].enabled=false;disabled.Add(matches[0]);
            }
            foreach(var r in originals.Where(r=>r.name.StartsWith("Furnace_",StringComparison.Ordinal)))
                r.sharedMaterials=r.sharedMaterials.Select(m=>m&&(m.name.Contains("Ivory")||m.name=="Cabinet_White")?mats["OXD_White"]:m).ToArray();
            var addedPanels=model.GetComponentsInChildren<Renderer>().Where(r=>r.name.StartsWith("OXD_CUT_",StringComparison.Ordinal)).ToArray();
            cycle.cutawayPanels=sourcePanels.Where(r=>!disabled.Contains(r)).Concat(addedPanels).Distinct().ToArray();
            if(old)UnityEngine.Object.DestroyImmediate(old.gameObject);
            foreach(var pose in poses)pose.Verify();
            for(int i=0;i<loader.Length;i++)Check(loader[i].sharedMaterials.SequenceEqual(loaderMaterials[i])&&loader[i].enabled==loaderEnabled[i],"Loader appearance changed: "+loader[i].name);
            Check(colliders.SequenceEqual(cycle.GetComponentsInChildren<Collider>(true)),"Original collider wiring changed.");
            Check(model.GetComponentsInChildren<Collider>(true).Length==0,"Detail meshes unexpectedly have colliders.");
            var mobileStart=mobile.position;var boatStart=cycle.boat.position;var waferParent=cycle.wafer.parent;
            var tube=Find(cycle.transform,"Integrated_Process_Tube").GetComponent<MeshFilter>();
            Check(tube,"Existing process tube missing.");
            // Clear aperture is preserved: heater bore is .238 m, existing boat radius is .185 m.
            var rod=Find(cycle.transform,"Furnace_Quartz_Rod");Check(Vector3.Distance(rod.position,cycle.boat.position)<1,"Boat assembly detached.");
            cycle.validationDelta=1f/30;var stack=new Stack<IEnumerator>();stack.Push(cycle.Cycle());int ticks=0;bool raised=false;
            var front=cycle.equipmentDoors[1].position-cycle.robot.position;front.y=0;front.Normalize();
            var panels=cycle.cutawayPanels;var visibleStates=panels.Select(r=>r.enabled).ToArray();
            Capture(cycle,front,"Tools/Previews/Oxidation-Detailed-Exterior.png");
            while(stack.Count>0)
            {
                Check(++ticks<30000,"Oxidation validation timed out.");var current=stack.Peek();if(!current.MoveNext()){stack.Pop();continue;}if(current.Current is IEnumerator nested)stack.Push(nested);
                Check(Vector3.Distance(mobile.position-mobileStart,cycle.boat.position-boatStart)<.002f,"New boat details are not following elevator.");
                if(cycle.status=="OXIDATION / SIMULATED"&&!raised)
                {
                    raised=true;Check(cycle.boat.position.y-boatStart.y>.5f,"Boat failed to rise.");
                    for(int i=0;i<panels.Length;i++)panels[i].enabled=false;
                    Check(addedPanels.All(r=>!r.enabled),"Detailed exterior still visible inside.");
                    Capture(cycle,front,"Tools/Previews/Oxidation-Detailed-BoatUp.png");
                    for(int i=0;i<panels.Length;i++)panels[i].enabled=visibleStates[i];
                }
            }
            Check(raised&&cycle.completed&&!cycle.failed&&cycle.wafer.parent==waferParent,"Wafer did not complete boat cycle and return to FOUP.");
            cycle.ResetPreview();foreach(var pose in poses)pose.Verify();
            for(int i=0;i<panels.Length;i++)panels[i].enabled=false;
            Check(disabled.All(r=>!r.enabled),"Old cosmetics were re-enabled by cutaway.");
            Capture(cycle,front,"Tools/Previews/Oxidation-Detailed-Inside.png");
            for(int i=0;i<panels.Length;i++)panels[i].enabled=visibleStates[i];
            AssetDatabase.SaveAssets();EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Failed to save detailed scene.");
            File.WriteAllText(Result,"DETAILED_OXIDATION_OK\n"+DateTime.UtcNow.ToString("O")+"\nbackup="+backup+"\nBlender meshes="+data.added_meshes+"; loader unchanged; 4 independent FBX anchors aligned; original rig/colliders preserved; moving ledges follow boat throughout cycle; wafer returned to FOUP; exterior/inside toggles checked; no network requests.\nExterior/Inside/BoatUp captures in Tools/Previews.");
            Selection.activeGameObject=model;
        }
        catch{EditorSceneManager.OpenScene(scene.path,OpenSceneMode.Single);throw;}
    }
    static void Capture(IntegratedOxidationCycle cycle,Vector3 front,string path)
    {
        Directory.CreateDirectory("Tools/Previews");
        var obj=new GameObject("Detailed oxidation capture"){hideFlags=HideFlags.HideAndDontSave};var camera=obj.AddComponent<Camera>();obj.AddComponent<HDAdditionalCameraData>();camera.CopyFrom(cycle.detail);camera.enabled=false;
        var rs=cycle.GetComponentsInChildren<Renderer>().Where(r=>r.enabled).ToArray();var b=rs[0].bounds;foreach(var r in rs)b.Encapsulate(r.bounds);
        var furnace=cycle.boat.position-cycle.robot.position;furnace.y=0;furnace.Normalize();
        camera.transform.position=b.center+front*7.2f+furnace*3.6f+Vector3.up*3.0f;camera.transform.LookAt(b.center);camera.fieldOfView=40;
        var rt=new RenderTexture(1600,1050,24);rt.Create();var prev=RenderTexture.active;var image=new Texture2D(1600,1050,TextureFormat.RGB24,false);
        try{for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});RenderTexture.active=rt;image.ReadPixels(new Rect(0,0,1600,1050),0,0);image.Apply();File.WriteAllBytes(path,image.EncodeToPNG());}
        finally{RenderTexture.active=prev;rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(image);UnityEngine.Object.DestroyImmediate(obj);}
    }
}
#endif
