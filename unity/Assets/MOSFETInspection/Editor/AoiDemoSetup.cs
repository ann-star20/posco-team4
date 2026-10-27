#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.HighDefinition;

public static class AoiDemoSetup
{
    const string Output="Assets/MOSFETInspection/Scenes/MOSFET_AOI_FunctionTest.unity";
    [InitializeOnLoadMethod] static void Request()
    {
        EditorApplication.update+=WatchTest;
        if(!File.Exists("BuildAoiDemo.once")) return;
        EditorApplication.delayCall+=()=>{if(!File.Exists("BuildAoiDemo.once"))return;File.Delete("BuildAoiDemo.once");try{Build();}catch(Exception e){File.WriteAllText("AoiDemo.result",e.ToString());Debug.LogException(e);}};
    }
    static void WatchTest()
    {
        if(!SessionState.GetBool("AOI_AUTOTEST",false)||!EditorApplication.isPlaying)return;
        var demo=UnityEngine.Object.FindFirstObjectByType<AoiCycleDemo>();
        if(demo&&demo.completed)
        {
            File.WriteAllText("AoiDemoTest.result",demo.okCount==1&&demo.ngCount==1?"AOI_CYCLE_PASS OK=1 NG=1":"AOI_CYCLE_FAIL");
            SessionState.SetBool("AOI_AUTOTEST",false);EditorApplication.isPlaying=false;
        }
    }
    static Transform Find(Transform root,string name)
    {
        var t=root.GetComponentsInChildren<Transform>(true).FirstOrDefault(x=>x.name==name);
        if(!t)throw new Exception("Missing AOI part: "+name);return t;
    }
    static Bounds Bounds(Transform t)
    {
        var rs=t.GetComponentsInChildren<Renderer>();if(rs.Length==0)throw new Exception("No renderer: "+t.name);
        var b=rs[0].bounds;foreach(var r in rs)b.Encapsulate(r.bounds);return b;
    }
    [MenuItem("MOSFET Factory/Build AOI Function Test")]
    public static void Build()
    {Build(false);}
    public static void Build(bool installMain)
    {
        if(EditorApplication.isPlaying)throw new Exception("Stop Play mode before setup.");
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(current.isDirty&&!EditorSceneManager.SaveScene(current))throw new Exception("Save scene first.");
        EditorSceneManager.OpenScene("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity");
        foreach(var name in new[]{"AOI_FUNCTION_TEST","Demo_MOSFET_8x_VisualScale","AOI_Live_Status","AOI_TEST_CAMERA","AOI_INSPECTION_CAMERA","AOI_DASHBOARD"})
        {var previous=GameObject.Find(name);if(previous)UnityEngine.Object.DestroyImmediate(previous);}
        var aoi=GameObject.Find("AOI_Inspection_Line").transform;
        var demo=new GameObject("AOI_FUNCTION_TEST").AddComponent<AoiCycleDemo>();
        var asset=AssetDatabase.LoadAssetAtPath<GameObject>("Assets/MOSFETInspection/Models/MOSFET/MOSFET_D4184.fbx");
        if(!asset)throw new Exception("MOSFET FBX import pending.");
        var product=(GameObject)PrefabUtility.InstantiatePrefab(asset);product.name="Demo_MOSFET_8x_VisualScale";
        product.transform.localScale*=8;
        // Match the imported equipment coordinate axes without guessing FBX handedness.
        product.transform.rotation=aoi.rotation;
        product.transform.SetParent(demo.transform,true);
        const string matFolder="Assets/MOSFETInspection/Materials/AoiDemo";
        Directory.CreateDirectory(matFolder);
        foreach(var renderer in product.GetComponentsInChildren<Renderer>())
        {
            renderer.sharedMaterials=renderer.sharedMaterials.Select(m=>{
                var path=matFolder+"/Demo_"+m.name+".mat";
                var n=AssetDatabase.LoadAssetAtPath<Material>(path);
                if(!n){n=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(n,path);}
                bool metal=m.name.Contains("Metal");bool ink=m.name.Contains("Marking");
                n.SetColor("_BaseColor",metal?new Color(.78f,.8f,.82f):ink?new Color(.4f,.4f,.4f):new Color(.12f,.13f,.15f));
                n.SetFloat("_Metallic",metal?.8f:0);n.SetFloat("_Smoothness",metal?.65f:.3f);return n;
            }).ToArray();
        }
        demo.product=product.transform;
        var infeed=Bounds(Find(aoi,"Buffer_Output_Belt"));
        var stage=Bounds(Find(aoi,"Inspection_Stage"));
        var sorter=Bounds(Find(aoi,"Conveyor_Belt.002"));
        demo.stopper=Find(aoi,"Inspection_Stopper");demo.pusher=Find(aoi,"Pusher_Head");demo.rod=Find(aoi,"Pusher_Rod");
        Vector3 axis=(sorter.center-stage.center);axis.y=0;axis.Normalize();
        float beltY=infeed.max.y;
        Vector3 Surface(Vector3 p){p.y=beltY;return p;}
        demo.start=Surface(infeed.center-axis*(infeed.size.x+infeed.size.z)*.3f);
        demo.inspection=Surface(stage.center);
        demo.sorting=Surface(demo.pusher.position);
        demo.okTray=Bounds(Find(aoi,"OK_Tray_Base")).center+Vector3.up*.04f;
        demo.ngTray=Bounds(Find(aoi,"NG_Tray_Base")).center+Vector3.up*.04f;
        void Chute(string name,out Vector3 entry,out Vector3 exit)
        {
            var r=Find(aoi,name).GetComponent<MeshFilter>();
            var vertices=r.sharedMesh.vertices.Select(v=>r.transform.TransformPoint(v)).ToArray();
            float high=vertices.Max(v=>v.y),low=vertices.Min(v=>v.y);
            var top=vertices.Where(v=>v.y>high-.04f).ToArray();var bottom=vertices.Where(v=>v.y<low+.04f).ToArray();
            entry=top.Aggregate(Vector3.zero,(s,v)=>s+v)/top.Length+Vector3.up*.02f;
            exit=bottom.Aggregate(Vector3.zero,(s,v)=>s+v)/bottom.Length+Vector3.up*.02f;
        }
        Chute("OK_End_Discharge_Chute",out demo.okEntry,out demo.okExit);
        Chute("NG_Push_Discharge_Chute",out demo.ngEntry,out demo.ngExit);
        demo.pushDirection=demo.ngEntry-demo.sorting;demo.pushDirection.y=0;
        product.transform.position=demo.start;
        var pb=Bounds(product.transform);product.transform.position+=Vector3.up*(beltY-pb.min.y);
        float offset=product.transform.position.y-demo.start.y;
        demo.start.y+=offset;demo.inspection.y+=offset;demo.sorting.y+=offset;
        var screen=Find(aoi,"AOI_HMI_Screen");
        var display=new GameObject("AOI_Live_Status").AddComponent<TextMesh>();
        display.transform.position=Bounds(screen).center;
        var forward=(screen.position-Find(aoi,"AOI_HMI_Bezel").position).normalized;
        display.transform.position+=forward*.012f;display.transform.rotation=Quaternion.LookRotation(-forward,Vector3.up);
        display.anchor=TextAnchor.MiddleCenter;display.alignment=TextAlignment.Center;display.characterSize=.016f;display.fontSize=48;
        display.text="AOI | SIMULATION\nREADY\nOK 0   NG 0";demo.monitor=display;
        demo.inspectionLeds=aoi.GetComponentsInChildren<Renderer>().Where(r=>r.name.StartsWith("LED_Diffuser")).ToArray();
        var cam=new GameObject("AOI_TEST_CAMERA").AddComponent<Camera>();cam.gameObject.AddComponent<HDAdditionalCameraData>();
        var center=Bounds(aoi).center;var front=forward;front.y=0;front.Normalize();
        cam.transform.position=center+front*5.5f+Vector3.up*3.1f-axis*2;
        cam.transform.LookAt(center);cam.fieldOfView=48;cam.nearClipPlane=.01f;
        demo.overview=cam;
        var close=new GameObject("AOI_INSPECTION_CAMERA").AddComponent<Camera>();close.gameObject.AddComponent<HDAdditionalCameraData>();
        close.transform.position=demo.inspection+Vector3.up*.65f;close.transform.LookAt(demo.inspection,axis);close.nearClipPlane=.01f;close.enabled=false;demo.inspectionView=close;
        if(installMain)
        {
            var h=close.gameObject.GetComponent<HDAdditionalCameraData>();h.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;h.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;
            var h2=cam.gameObject.GetComponent<HDAdditionalCameraData>();h2.antialiasing=h.antialiasing;h2.SMAAQuality=h.SMAAQuality;
            cam.enabled=false;demo.dashboardControlled=true;return;
        }
        var old=GameObject.Find("FAB_OVERVIEW_CAMERA");if(old)old.GetComponent<Camera>().enabled=false;
        AssetDatabase.SaveAssets();
        EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),Output);
        File.WriteAllText("AoiDemo.result","AOI_SETUP_OK\n"+Output);
        Debug.Log("AOI_SETUP_OK "+Output);
        Selection.activeGameObject=demo.gameObject;
        if(SceneView.lastActiveSceneView)SceneView.lastActiveSceneView.LookAt(center,cam.transform.rotation,6);
        SessionState.SetBool("AOI_AUTOTEST",false);
        // Run only when the user presses Play and then Start.
    }
}
#endif
