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

// Editor-only exterior installation; the production motion controller remains unchanged.
[InitializeOnLoad] public static class RestyleOxidationExterior
{
    const string Request="RestyleOxidationExterior.once", Result="RestyleOxidationExterior.result";
    const string RootName="Oxidation_Exterior_WhiteTeal";
    static RestyleOxidationExterior(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new InvalidOperationException(message);}
    static void Tick()
    {
        if(!File.Exists(Request)||EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode)return;
        File.Delete(Request);
        try{Install();}catch(Exception e){File.WriteAllText(Result,"FAILED\n"+e);Debug.LogException(e);}
    }
    struct Pose
    {
        public Transform t,parent;public Vector3 position,scale;public Quaternion rotation;
        public Pose(Transform value){t=value;parent=t.parent;position=t.localPosition;scale=t.localScale;rotation=t.localRotation;}
        public void Verify(){Check(t&&t.parent==parent&&(t.localPosition-position).sqrMagnitude<1e-8f&&(t.localScale-scale).sqrMagnitude<1e-8f&&Quaternion.Angle(t.localRotation,rotation)<.01f,"Original transform changed: "+t.name);}
    }
    static Bounds Project(Renderer renderer,Quaternion basis)
    {
        var inverse=Quaternion.Inverse(basis);var mesh=renderer.GetComponent<MeshFilter>().sharedMesh.bounds;
        var b=new Bounds(inverse*renderer.transform.TransformPoint(mesh.center),Vector3.zero);
        for(int i=0;i<8;i++)b.Encapsulate(inverse*renderer.transform.TransformPoint(mesh.center+Vector3.Scale(mesh.extents,new Vector3((i&1)==0?-1:1,(i&2)==0?-1:1,(i&4)==0?-1:1))));
        return b;
    }
    static Material Material(string name,Color color,float smoothness)
    {
        const string folder="Assets/MOSFETInspection/Materials/OxidationExterior";
        Directory.CreateDirectory(folder);string path=folder+"/"+name+".mat";
        var m=AssetDatabase.LoadAssetAtPath<Material>(path);
        if(!m){m=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(m,path);}
        m.SetColor("_BaseColor",color);m.SetFloat("_Smoothness",smoothness);m.SetFloat("_Metallic",.12f);EditorUtility.SetDirty(m);return m;
    }
    static Renderer Box(Transform root,string name,Vector3 center,Vector3 size,Material material)
    {
        Check(size.x>0&&size.y>0&&size.z>0,"Invalid exterior dimensions: "+name);
        var obj=GameObject.CreatePrimitive(PrimitiveType.Cube);obj.name=name;obj.transform.SetParent(root,false);
        obj.transform.localPosition=center;obj.transform.localScale=size;
        UnityEngine.Object.DestroyImmediate(obj.GetComponent<Collider>());
        var renderer=obj.GetComponent<Renderer>();renderer.sharedMaterial=material;return renderer;
    }
    [MenuItem("MOSFET Factory/Restyle oxidation exterior (keep loader)")]
    public static void Install()
    {
        Check(!EditorApplication.isPlayingOrWillChangePlaymode,"Exit Play before changing the exterior.");
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        Check(scene.path=="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity","Open the corrected factory scene first.");
        var cycle=UnityEngine.Object.FindAnyObjectByType<IntegratedOxidationCycle>();Check(cycle,"Oxidation controller missing.");
        Check(!cycle.transform.Find(RootName),"Exterior already installed; restore the backup before reinstalling.");
        var original=cycle.GetComponentsInChildren<Transform>(true);
        Renderer Find(string name)=>original.Single(t=>t.name==name).GetComponent<Renderer>();
        var upper=Find("Furnace_Upper_Cabinet");var lower=Find("Furnace_Lower_Cabinet");
        Check(upper&&lower,"Furnace cabinet meshes missing.");
        cycle.Initialize();cycle.ResetPreview();
        var poses=original.Select(t=>new Pose(t)).ToArray();
        var loader=cycle.GetComponentsInChildren<Renderer>(true).Where(r=>!r.name.StartsWith("Furnace_",StringComparison.Ordinal)).ToArray();
        var loaderMaterials=loader.Select(r=>r.sharedMaterials).ToArray();
        var colliders=cycle.GetComponentsInChildren<Collider>(true);
        var controllerBefore=EditorJsonUtility.ToJson(cycle);
        Check(EditorSceneManager.SaveScene(scene),"Could not save the current scene before backup.");
        string backup="Tools/Backups/OxidationExterior-"+DateTime.Now.ToString("yyyyMMdd-HHmmss");Directory.CreateDirectory(backup);
        File.Copy(scene.path,backup+"/Before.unity");
        Directory.CreateDirectory("Tools/Previews");
        try
        {
            Vector3 front=cycle.equipmentDoors[1].position-cycle.robot.position;front.y=0;front.Normalize();
            var basis=Quaternion.LookRotation(front,Vector3.up);var u=Project(upper,basis);var l=Project(lower,basis);
            Check(u.size.x>.4f&&u.size.x<3&&u.size.y>.4f&&u.size.y<4,"Unexpected upper furnace envelope: "+u);
            Capture(cycle,basis,"Tools/Previews/Oxidation-Before.png");
            var white=Material("Cabinet_White",new Color(.82f,.85f,.87f),.32f);
            var trim=Material("Frame_Graphite",new Color(.035f,.055f,.065f),.4f);
            var glass=Material("Observation_Blue",new Color(.045f,.105f,.15f),.86f);
            var reflection=Material("Glass_Reflection",new Color(.12f,.23f,.29f),.85f);
            var teal=Material("Accent_Teal",new Color(.045f,.35f,.37f),.35f);
            // Swap only ivory cabinet slots on furnace renderers, never shared source materials.
            foreach(var r in cycle.GetComponentsInChildren<Renderer>(true).Where(r=>r.name.StartsWith("Furnace_",StringComparison.Ordinal)))
                r.sharedMaterials=r.sharedMaterials.Select(m=>m&&m.name.Contains("Ivory")?white:m).ToArray();
            var root=new GameObject(RootName).transform;root.SetPositionAndRotation(Vector3.zero,basis);
            // World-sized decoration child avoids imported FBX units and leaves all anchors untouched.
            root.SetParent(cycle.transform,true);
            float z=u.max.z+.009f,w=u.size.x,h=u.size.y;
            var window=new Vector3(u.center.x-.04f*w,u.center.y+.03f*h,z);
            Box(root,"Upper_Window_Bezel",window,new Vector3(.32f*w,.69f*h,.018f),trim);
            Box(root,"Upper_Window_Glass",window+Vector3.forward*.012f,new Vector3(.265f*w,.64f*h,.008f),glass);
            Box(root,"Upper_Window_Reflection",window+new Vector3(-.105f*w,0,.017f),new Vector3(.012f*w,.60f*h,.003f),reflection);
            Box(root,"Teal_Front_Band",new Vector3(u.center.x,u.min.y+.055f*h,z+.008f),new Vector3(.97f*w,.025f*h,.012f),teal);
            Box(root,"Teal_Right_Return",new Vector3(u.max.x+.009f,u.min.y+.055f*h,u.center.z),new Vector3(.012f,.025f*h,u.size.z),teal);
            // Keep the lower loading opening and the side robot passage completely unobstructed.
            for(int row=0;row<3;row++)for(int col=0;col<10;col++)
                Box(root,"Lower_Vent_"+row+"_"+col,new Vector3(l.center.x+((col-4.5f)/11f)*l.size.x,l.min.y+(.15f+row*.045f)*l.size.y,l.max.z+.008f),new Vector3(l.size.x*.048f,l.size.y*.015f,.008f),trim);
            cycle.cutawayPanels=cycle.cutawayPanels.Concat(root.GetComponentsInChildren<Renderer>()).Distinct().ToArray();
            foreach(var pose in poses)pose.Verify();
            for(int i=0;i<loader.Length;i++)Check(loader[i].sharedMaterials.SequenceEqual(loaderMaterials[i]),"Loader material changed: "+loader[i].name);
            Check(colliders.SequenceEqual(cycle.GetComponentsInChildren<Collider>(true)),"Physical colliders changed.");
            // Apart from cutaway display renderers the controller wiring must remain identical.
            var newPanels=cycle.cutawayPanels;cycle.cutawayPanels=newPanels.Where(r=>!r.transform.IsChildOf(root)).ToArray();
            Check(EditorJsonUtility.ToJson(cycle)==controllerBefore,"Motion or equipment wiring changed.");cycle.cutawayPanels=newPanels;
            cycle.validationDelta=1f/30;var stack=new Stack<IEnumerator>();stack.Push(cycle.Cycle());int ticks=0;
            while(stack.Count>0){Check(++ticks<30000,"Oxidation motion check timed out.");var task=stack.Peek();if(!task.MoveNext()){stack.Pop();continue;}if(task.Current is IEnumerator nested)stack.Push(nested);}
            Check(cycle.completed&&!cycle.failed,"Oxidation did not return the wafer to FOUP.");
            cycle.ResetPreview();foreach(var pose in poses)pose.Verify();
            // Check cutaway can hide and restore the new facade together with the original shell.
            foreach(var r in newPanels)r.enabled=false;Check(root.GetComponentsInChildren<Renderer>().All(r=>!r.enabled),"Cutaway facade stayed visible.");
            foreach(var r in newPanels)r.enabled=true;
            Capture(cycle,basis,"Tools/Previews/Oxidation-WhiteTeal.png");
            AssetDatabase.SaveAssets();EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Could not save restyled scene.");
            File.WriteAllText(Result,"OXIDATION_EXTERIOR_OK\n"+DateTime.UtcNow.ToString("O")+"\nbackup="+backup+"\nupper="+u+"\nlower="+l+"\nLoader original transforms and materials unchanged; original colliders and controller anchors unchanged; actual full oxidation coroutine completed including wafer pick, boat up/down and FOUP return; cutaway checked; no network requests.\npreview=Tools/Previews/Oxidation-WhiteTeal.png");
            Selection.activeGameObject=root.gameObject;
        }
        catch{EditorSceneManager.OpenScene(scene.path,OpenSceneMode.Single);throw;}
    }
    static void Capture(IntegratedOxidationCycle cycle,Quaternion basis,string path)
    {
        var obj=new GameObject("Oxidation exterior preview camera"){hideFlags=HideFlags.HideAndDontSave};
        var camera=obj.AddComponent<Camera>();obj.AddComponent<HDAdditionalCameraData>();camera.CopyFrom(cycle.detail);camera.enabled=false;
        var bounds=cycle.GetComponentsInChildren<Renderer>().Where(r=>r.enabled).Select(r=>r.bounds).Aggregate((a,b)=>{a.Encapsulate(b);return a;});
        camera.transform.position=bounds.center+(basis*Vector3.forward)*6.5f+(basis*Vector3.right)*4f+Vector3.up*3.2f;camera.transform.LookAt(bounds.center);camera.fieldOfView=43;
        var rt=new RenderTexture(1600,1000,24);rt.Create();var previous=RenderTexture.active;var texture=new Texture2D(1600,1000,TextureFormat.RGB24,false);
        try{for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});RenderTexture.active=rt;texture.ReadPixels(new Rect(0,0,1600,1000),0,0);texture.Apply();File.WriteAllBytes(path,texture.EncodeToPNG());}
        finally{RenderTexture.active=previous;rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(texture);UnityEngine.Object.DestroyImmediate(obj);}
    }
}
#endif
