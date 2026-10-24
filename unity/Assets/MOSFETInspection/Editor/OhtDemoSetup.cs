#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering.HighDefinition;
using UnityEngine.Rendering;
public static class OhtDemoSetup
{
    const string Models="Assets/MOSFETInspection/Models/OHT/";
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Requested;EditorApplication.update+=Requested;}
    static void Requested()
    {
        if(EditorApplication.isPlayingOrWillChangePlaymode||EditorApplication.isCompiling||EditorApplication.isUpdating||!File.Exists("BuildOhtDemo.once"))return;
        File.Delete("BuildOhtDemo.once");try{Build();}catch(Exception e){File.WriteAllText("OhtDemo.result",e.ToString());Debug.LogException(e);}
    }
    static Transform Find(Transform root,string name)
    {var t=root.GetComponentsInChildren<Transform>().FirstOrDefault(o=>o.name==name);if(!t)throw new Exception("Missing OHT node: "+name);return t;}
    static Material Mat(string name,Color color,float metal=0)
    {
        string folder="Assets/MOSFETInspection/Materials/OHT";Directory.CreateDirectory(folder);string path=folder+"/"+name+".mat";
        var m=AssetDatabase.LoadAssetAtPath<Material>(path);if(!m){m=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(m,path);}
        m.SetColor("_BaseColor",color);m.SetFloat("_Metallic",metal);m.SetFloat("_Smoothness",.5f);EditorUtility.SetDirty(m);return m;
    }
    [MenuItem("MOSFET Factory/Build OHT Transport Test")]
    public static void Build()
    {
        if(EditorApplication.isPlaying)throw new Exception("Stop Play mode first.");
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(current.isDirty&&!EditorSceneManager.SaveScene(current))throw new Exception("Save current scene first.");
        var scene=EditorSceneManager.NewScene(NewSceneSetup.EmptyScene,NewSceneMode.Single);
        GameObject Model(string name)
        {var asset=AssetDatabase.LoadAssetAtPath<GameObject>(Models+name+".fbx");if(!asset)throw new Exception("Model import pending: "+name);return (GameObject)PrefabUtility.InstantiatePrefab(asset);}
        var oht=Model("OHT_System");var foup=Model("FOUP_300mm_Concept");
        foreach(var renderer in oht.GetComponentsInChildren<Renderer>().Concat(foup.GetComponentsInChildren<Renderer>()))
        {
            renderer.sharedMaterials=renderer.sharedMaterials.Select(m=>{
                string n=m.name;Color c=new Color(.83f,.86f,.89f);float metal=0;
                if(n.Contains("Amber"))c=new Color(.83f,.52f,.23f);
                else if(n.Contains("Silicon")) {c=new Color(.2f,.35f,.47f);metal=.5f;}
                else if(n.Contains("Red"))c=new Color(.75f,.08f,.1f);
                else if(n.Contains("Green"))c=new Color(.12f,.8f,.3f);
                else if(n.Contains("Graphite")||n.Contains("Slot")||n.Contains("Door"))c=new Color(.19f,.22f,.25f);
                else if(n.Contains("Aluminum")||n.Contains("Metal")){c=new Color(.7f,.76f,.8f);metal=.65f;}
                return Mat(n,c,metal);
            }).ToArray();
        }
        var demo=new GameObject("OHT_TRANSPORT_CONTROLLER").AddComponent<OhtTransportDemo>();
        demo.carrier=Find(oht.transform,"OHT_Carrier");demo.lift=Find(oht.transform,"Lift_Frame");demo.attachPoint=Find(oht.transform,"FOUP_AttachPoint");demo.gripper=Find(oht.transform,"Gripper");
        demo.leftJaw=Find(oht.transform,"Gripper_Left");demo.rightJaw=Find(oht.transform,"Gripper_Right");
        demo.docks=new[]{"SOURCE_PORT_Dock","OX_LOADPORT_01_Dock","IMP_LOADPORT_01_Dock"}.Select(n=>Find(oht.transform,n)).ToArray();
        demo.beltTops=oht.GetComponentsInChildren<Transform>().Where(t=>t.name.StartsWith("Belt_Top")).OrderBy(t=>t.name).ToArray();
        demo.beltBottoms=oht.GetComponentsInChildren<Transform>().Where(t=>t.name.StartsWith("Belt_Bottom")).OrderBy(t=>t.name).ToArray();
        if(demo.beltTops.Length!=4||demo.beltBottoms.Length!=4)throw new Exception("Four hoist belts required.");
        foreach(var r in oht.GetComponentsInChildren<Renderer>().Where(r=>r.name.StartsWith("Hoist_Belt")))r.enabled=false;
        demo.beltMaterial=Mat("Animated_Belt",new Color(.1f,.12f,.14f));
        demo.travelGripHeight=Find(oht.transform,"Travel_Grip_Height").position.y;
        demo.foup=foup.transform;demo.foupGrip=Find(foup.transform,"OHT_Grip_Anchor");demo.foupDock=Find(foup.transform,"LoadPort_Dock_Anchor");
        foup.transform.position+=demo.docks[0].position-demo.foupDock.position;foup.transform.SetParent(demo.docks[0],true);
        if(Vector3.Distance(demo.attachPoint.position,demo.foupGrip.position)>.003f)throw new Exception("Initial gripper alignment does not match FOUP.");
        var floor=GameObject.CreatePrimitive(PrimitiveType.Cube);floor.name="OHT_TEST_FLOOR";floor.transform.position=new Vector3(0,-.08f,0);floor.transform.localScale=new Vector3(8,.16f,4);floor.GetComponent<Renderer>().sharedMaterial=Mat("CleanroomFloor",new Color(.65f,.72f,.75f));
        var volume=new GameObject("OHT_Lighting").AddComponent<UnityEngine.Rendering.Volume>();volume.isGlobal=true;
        volume.sharedProfile=AssetDatabase.LoadAssetAtPath<UnityEngine.Rendering.VolumeProfile>("Assets/MOSFETInspection/Materials/SmallFab/CleanroomVolume.asset");
        if(!volume.sharedProfile)throw new Exception("Cleanroom lighting profile missing.");
        foreach(var yaw in new[]{-30f,135f}){var light=new GameObject("OHT_StudioLight").AddComponent<Light>();light.type=LightType.Directional;light.gameObject.AddComponent<HDAdditionalLightData>();light.lightUnit=LightUnit.Lux;light.intensity=yaw<0?1100:700;light.transform.rotation=Quaternion.Euler(50,yaw,0);}
        var camera=new GameObject("OHT_DEMO_CAMERA").AddComponent<Camera>();camera.gameObject.AddComponent<HDAdditionalCameraData>();camera.transform.position=new Vector3(7,6,-9);camera.transform.LookAt(new Vector3(0,2,0));camera.fieldOfView=45;
        AssetDatabase.SaveAssets();const string output="Assets/MOSFETInspection/Scenes/MOSFET_OHT_TransportTest.unity";EditorSceneManager.SaveScene(scene,output);
        File.WriteAllText("OhtDemo.result","OHT_SETUP_OK\n"+output+"\nFOUP anchor alignment <3mm; four belts; manual start only");
        Selection.activeGameObject=demo.gameObject;if(SceneView.lastActiveSceneView)SceneView.lastActiveSceneView.LookAt(new Vector3(0,2,0),camera.transform.rotation,7);
    }
}
#endif
