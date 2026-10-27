#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.HighDefinition;

public static class WaferFeedSetup
{
    const string Model="Assets/MOSFETInspection/Models/FabEquipment/EFEM_WaferDemo.fbx";
    [InitializeOnLoadMethod] static void Request()
    {
        if(!File.Exists("BuildWaferDemo.once"))return;
        EditorApplication.update += TryBuild;
    }
    static void TryBuild()
    {
        if(EditorApplication.isPlayingOrWillChangePlaymode || EditorApplication.isCompiling || EditorApplication.isUpdating)return;
        EditorApplication.update -= TryBuild;
        if(!File.Exists("BuildWaferDemo.once"))return;
        File.Delete("BuildWaferDemo.once");
        try{Build();}catch(Exception e){File.WriteAllText("WaferDemo.result",e.ToString());Debug.LogException(e);}
    }
    [MenuItem("MOSFET Factory/Build Wafer Feed Test")]
    public static void Build()
    {
        if(EditorApplication.isPlaying)throw new Exception("Stop Play mode first.");
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(current.isDirty&&!EditorSceneManager.SaveScene(current))throw new Exception("Save current scene first.");
        var importer=AssetImporter.GetAtPath(Model) as ModelImporter;
        if(!importer)throw new Exception("Wafer FBX import pending");
        importer.animationType=ModelImporterAnimationType.Legacy;importer.importAnimation=true;
        importer.animationCompression=ModelImporterAnimationCompression.Off;importer.SaveAndReimport();
        EditorSceneManager.OpenScene("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity");
        var old=GameObject.Find("EFEM");if(!old)throw new Exception("EFEM missing");
        var materials=old.GetComponentsInChildren<Renderer>().SelectMany(r=>r.sharedMaterials).Where(m=>m).Distinct().ToArray();
        var instance=(GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Model));
        instance.name="EFEM_WaferFeed_Demo";instance.transform.SetPositionAndRotation(old.transform.position,old.transform.rotation);instance.transform.localScale=old.transform.localScale;
        foreach(var r in instance.GetComponentsInChildren<Renderer>())
        {
            r.sharedMaterials=r.sharedMaterials.Select(m=>{
                var match=materials.FirstOrDefault(x=>x.name=="EFEM_"+m.name||x.name==m.name);
                if(match)return match;
                string path="Assets/MOSFETInspection/Materials/SmallFab/WaferDemo_"+m.name+".mat";
                var n=AssetDatabase.LoadAssetAtPath<Material>(path);if(!n){n=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(n,path);}
                n.SetColor("_BaseColor",m.name.Contains("Amber")?new Color(.77f,.49f,.17f):new Color(.6f,.65f,.7f));n.SetFloat("_Smoothness",.4f);return n;
            }).ToArray();
        }
        UnityEngine.Object.DestroyImmediate(old);
        var anim=instance.GetComponent<Animation>();if(!anim)anim=instance.AddComponent<Animation>();
        var clip=AssetDatabase.LoadAllAssetsAtPath(Model).OfType<AnimationClip>().FirstOrDefault(c=>!c.name.StartsWith("__"));
        if(!clip||clip.length<10)throw new Exception("Missing or incomplete wafer animation");
                var cleaned=UnityEngine.Object.Instantiate(clip);cleaned.name="WaferCycle";
        string[] moving={"Robot_Joint_01_ANIM","Robot_Joint_02_ANIM","Robot_Wrist_ANIM","Robot_Wafer_Demo","Demo_FOUP_ROOT","Demo_FOUP_Door","REF_LP2_Door_ANIM"};
        foreach(var binding in AnimationUtility.GetCurveBindings(cleaned))
        {
            string leaf=binding.path.Split('/').Last();
            if(string.IsNullOrEmpty(binding.path)||!moving.Contains(leaf)) AnimationUtility.SetEditorCurve(cleaned,binding,null);
        }
        if(AnimationUtility.GetCurveBindings(cleaned).Any(b=>b.path==""))throw new Exception("Root animation must not change factory placement.");
        const string clipPath="Assets/MOSFETInspection/Models/FabEquipment/WaferCycle.anim";
        var savedClip=AssetDatabase.LoadAssetAtPath<AnimationClip>(clipPath);
        if(savedClip){EditorUtility.CopySerialized(cleaned,savedClip);UnityEngine.Object.DestroyImmediate(cleaned);clip=savedClip;}
        else{AssetDatabase.CreateAsset(cleaned,clipPath);clip=cleaned;}
        foreach(AnimationState state in anim.Cast<AnimationState>().ToArray())anim.RemoveClip(state.name);
        anim.AddClip(clip,"WaferCycle");anim.clip=clip;anim.playAutomatically=false;anim.wrapMode=WrapMode.ClampForever;
        var demo=instance.AddComponent<WaferFeedDemo>();demo.motion=anim;demo.clipName="WaferCycle";
        demo.cutawayPanels=instance.GetComponentsInChildren<Renderer>().Where(r=>r.name=="EFEM_RearCabinet"||r.name.StartsWith("REF_Upper")||r.name.Contains("Fascia")||r.name.Contains("DoorFrame")||r.name=="EFEM_TopHeader"||r.name.StartsWith("REF_Vent")||r.name.EndsWith("_Header")||r.name=="Demo_FOUP_Roof"||r.name=="Demo_FOUP_OuterWall").ToArray();
        foreach(var r in demo.cutawayPanels)r.enabled=false;
        foreach(var camera in UnityEngine.Object.FindObjectsByType<Camera>(FindObjectsSortMode.None))camera.enabled=false;
        var cam=new GameObject("WAFER_FEED_CAMERA").AddComponent<Camera>();cam.gameObject.AddComponent<HDAdditionalCameraData>();
        var point=instance.GetComponentsInChildren<Transform>().First(t=>t.name=="Robot_Joint_01_ANIM").position;
        var front=instance.transform.TransformDirection(Vector3.up);front.y=0;
        // Use the actual loadport direction to avoid FBX axis assumptions.
        var port=instance.GetComponentsInChildren<Transform>().First(t=>t.name=="LoadPort_02").position;
        front=port-point;front.y=0;front.Normalize();
        cam.transform.position=point+front*1.8f+Vector3.up*4.7f+Vector3.right*2.7f;cam.transform.LookAt(point+Vector3.up*.1f);cam.fieldOfView=48;cam.nearClipPlane=.02f;
        AssetDatabase.SaveAssets();
        const string output="Assets/MOSFETInspection/Scenes/MOSFET_WaferFeedTest.unity";
        EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),output);
        File.WriteAllText("WaferDemo.result","WAFER_SETUP_OK\n"+output+"\nclip_seconds="+clip.length+"\ncutaway_panels="+demo.cutawayPanels.Length);
        if(SceneView.lastActiveSceneView)SceneView.lastActiveSceneView.LookAt(point,cam.transform.rotation,6);
        Selection.activeGameObject=instance;
        EditorApplication.delayCall+=()=>EditorApplication.ExecuteMenuItem("MOSFET Factory/Audit Wafer Preview");
    }
}
#endif
