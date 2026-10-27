#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;
public static class InstallOhtLoop
{
    const string Base="Assets/MOSFETInspection/";
    const string ScenePath=Base+"Scenes/MOSFETSmallFab_Corrected.unity";
    [Serializable]class Record{public string name;public float[] color;public float metallic,roughness;}
    [Serializable]class Records{public Record[] items;}
    [Serializable]class Port{public string id,equipment,node;public Vector3 position;}
    [Serializable]class Layout{public float railHeight,supportTop,vehicleLowest,clearanceOverHighestEquipment,rightStraightEnd,rightRailEnd;public Vector3[] supportColumns;public bool closed;public Vector3[] points;public Port[] ports;}
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Tick;EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(!File.Exists("InstallOhtLoop.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("InstallOhtLoop.once");try{Install();}catch(Exception e){File.WriteAllText("InstallOhtLoop.result",e.ToString());Debug.LogException(e);}
    }
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static Transform Find(Transform root,string name)=>root.GetComponentsInChildren<Transform>(true).FirstOrDefault(t=>t.name==name)??throw new Exception("Missing node "+name);
    static void Map(GameObject model)
    {
        var records=JsonUtility.FromJson<Records>(File.ReadAllText(Base+"Models/OHTLoop/OHT_Loop_materials.json")).items;
        string folder=Base+"Materials/OHTLoop";Directory.CreateDirectory(folder);AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        foreach(var r in model.GetComponentsInChildren<Renderer>())r.sharedMaterials=r.sharedMaterials.Select(original=>
        {
            var record=records.FirstOrDefault(x=>original&&x.name==original.name);Check(record!=null,"Unmapped OHT material "+original);
            string path=folder+"/"+record.name+".mat";var m=AssetDatabase.LoadAssetAtPath<Material>(path);
            if(!m){m=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(m,path);}
            var c=record.color;m.SetColor("_BaseColor",new Color(c[0],c[1],c[2],1).gamma);m.SetFloat("_Metallic",record.metallic);m.SetFloat("_Smoothness",1-record.roughness);EditorUtility.SetDirty(m);return m;
        }).ToArray();
    }
    [MenuItem("MOSFET Factory/Install Cleanroom OHT Loop")]
    public static void Install()
    {
        Check(!EditorApplication.isPlaying,"Exit Play first.");var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();if(current.isDirty)Check(EditorSceneManager.SaveScene(current),"Save cancelled.");
        var scene=EditorSceneManager.OpenScene(ScenePath);
        string backup=AssetDatabase.GenerateUniqueAssetPath(Base+"Scenes/MOSFETSmallFab_BeforeOhtLoop.unity");Check(AssetDatabase.CopyAsset(ScenePath,backup),"Backup failed.");
        try
        {
            var layout=JsonUtility.FromJson<Layout>(File.ReadAllText(Base+"Models/OHTLoop/OHT_Loop_layout.json"));Check(layout.closed&&layout.points.Length>100&&layout.ports.Length==4,"Invalid loop layout.");
            var equipment=layout.ports.Select(p=>GameObject.Find(p.equipment)).ToArray();Check(equipment.All(o=>o),"Equipment missing.");var positions=equipment.Select(o=>o.transform.position).ToArray();
            for(int i=0;i<4;i++)Check(Vector3.Distance(Find(equipment[i].transform,layout.ports[i].node).position,layout.ports[i].position)<.002f,"Dock moved since Blender survey: "+layout.ports[i].id);
            var old=GameObject.Find("OHT_Cleanroom_Loop");if(old)UnityEngine.Object.DestroyImmediate(old);old=GameObject.Find("OHT_FOUP_01");if(old)UnityEngine.Object.DestroyImmediate(old);
            var asset=AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/OHTLoop/OHT_Cleanroom_Loop.fbx");Check(asset,"OHT model import pending.");
            var model=(GameObject)PrefabUtility.InstantiatePrefab(asset);PrefabUtility.UnpackPrefabInstance(model,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);model.name="OHT_Cleanroom_Loop";
            var origin=Find(model.transform,"OHT_Frame_Origin");var up=Find(model.transform,"OHT_Frame_Up").position-origin.position;var front=Find(model.transform,"OHT_Frame_Front").position-origin.position;
            model.transform.rotation=Quaternion.Inverse(Quaternion.LookRotation(-front,up))*model.transform.rotation;model.transform.position-=origin.position;
            // The surveyed Z-up route uses +Y as aisle front; FBX import reflects its X axis.
            var modelScale=model.transform.localScale;modelScale.x*=-1;model.transform.localScale=modelScale;
            foreach(var t in model.GetComponentsInChildren<Transform>())if(t.name.EndsWith("_Export")&&(t.name.StartsWith("Station_Label")||t.name.StartsWith("Vehicle_ID"))){var scale=t.localScale;scale.x*=-1;t.localScale=scale;}
            Map(model);
            for(int i=0;i<4;i++)
            {
                var stop=Find(model.transform,layout.ports[i].id+"_STOP").position;var target=layout.ports[i].position;target.y=layout.railHeight;
                Check(Vector3.Distance(stop,target)<.002f,"Stop/dock alignment failed: "+layout.ports[i].id+" actual="+stop.ToString("F4")+" expected="+target.ToString("F4")+" origin="+origin.position.ToString("F4"));
                Check(layout.points.Min(p=>Vector3.Distance(p,target))<.002f,"Stop not on rail centreline.");
            }
            var geometry=Find(model.transform,"Rail_ClosedLoop").GetComponent<Renderer>().bounds;Check(Mathf.Abs(geometry.center.y-layout.railHeight)<.01f,"Rail height mismatch.");
            Check(layout.vehicleLowest-equipment.Max(o=>OhtRailSurvey.BoundsOf(o).max.y)>.60f,"Insufficient raised-carrier clearance.");
            var foupAsset=AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/OHT/FOUP_300mm_Concept.fbx");Check(foupAsset,"FOUP asset missing.");
            var foup=(GameObject)PrefabUtility.InstantiatePrefab(foupAsset);PrefabUtility.UnpackPrefabInstance(foup,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);foup.name="OHT_FOUP_01";
            var dock=Find(foup.transform,"LoadPort_Dock_Anchor");var grip=Find(foup.transform,"OHT_Grip_Anchor");up=(grip.position-dock.position).normalized;front=Vector3.ProjectOnPlane(Find(foup.transform,"FOUP_Door_ANIM").position-dock.position,up).normalized;
            foup.transform.rotation=Quaternion.Inverse(Quaternion.LookRotation(-front,up))*foup.transform.rotation;
            var attach=Find(model.transform,"OHT_FOUP_AttachPoint");foup.transform.position+=attach.position-grip.position;
            var existingMats=AssetDatabase.FindAssets("t:Material",new[]{Base+"Materials/OHT"}).Select(g=>AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(g))).ToDictionary(m=>m.name);
            foreach(var renderer in foup.GetComponentsInChildren<Renderer>())renderer.sharedMaterials=renderer.sharedMaterials.Select(m=>existingMats[m.name]).ToArray();
            Check(Vector3.Distance(attach.position,grip.position)<.002f,"FOUP grip alignment failed.");
            var fb=OhtRailSurvey.BoundsOf(foup);Check(fb.min.y>equipment.Max(o=>OhtRailSurvey.BoundsOf(o).max.y)+.60f,"Payload too low.");
            var shell=scene.GetRootGameObjects().First(o=>o.name.StartsWith("SMALL_FAB_"));var parts=shell.GetComponentsInChildren<Transform>(true);var floor=parts.First(t=>t.name.StartsWith("Floor_")).GetComponent<Renderer>().bounds;
            Check(geometry.min.x>floor.min.x&&geometry.max.x<floor.max.x&&geometry.min.z>floor.min.z&&geometry.max.z<floor.max.z,"Rail exceeds floor footprint.");
            // All four ion loadports must remain on the delivery straight with room for the carrier.
            var ionPorts=equipment[3].GetComponentsInChildren<Transform>(true).Where(t=>System.Text.RegularExpressions.Regex.IsMatch(t.name,@"^FOUP_Dock_0[1-4]$")).ToArray();
            Check(ionPorts.Length==4,"Expected four ion loadports.");
            foreach(var port in ionPorts)Check(port.position.x+.50f<layout.rightStraightEnd&&Mathf.Abs(port.position.z-layout.ports[3].position.z)<.01f,"Ion port is too close to rail bend: "+port.name);
            Check(layout.rightRailEnd>OhtRailSurvey.BoundsOf(equipment[3]).max.x,"Rail does not span full ion implanter.");
            Check(layout.supportColumns!=null&&layout.supportColumns.Length==7,"Grounded rear support frame missing.");
            foreach(var position in layout.supportColumns)
            {
                Check(position.x-.19f>floor.min.x&&position.x+.19f<floor.max.x&&position.z+.18f<floor.max.z,"Support base outside room.");
                foreach(var tool in equipment){var envelope=OhtRailSurvey.BoundsOf(tool);Check(!(position.x+.19f>envelope.min.x&&position.x-.19f<envelope.max.x&&position.z+.18f>envelope.min.z&&position.z-.18f<envelope.max.z),"Support base overlaps "+tool.name);}
            }
            foreach(var t in model.GetComponentsInChildren<Transform>().Where(t=>t.name.StartsWith("Rear_Column_Base_")))Check(Mathf.Abs(t.GetComponent<Renderer>().bounds.min.y-floor.max.y)<.003f,"Support foot not grounded.");
            float wallHeight=Mathf.Ceil((layout.supportTop+.20f)*2)/2;
            foreach(var t in parts)
            {
                if(new[]{"Rear_Wall","Left_Wall","Right_Wall","Front_Wall"}.Contains(t.name))
                {var s=t.localScale;s.y=Mathf.Max(s.y,wallHeight);t.localScale=s;var p=t.localPosition;p.y=s.y*.5f;t.localPosition=p;}
                if(t.name=="Rear_Panel_Joint"||t.name=="Stocker_Rear_Panel_Joint")
                {var s=t.localScale;s.y=wallHeight-.15f;t.localScale=s;var p=t.localPosition;p.y=wallHeight*.5f;t.localPosition=p;}
                if(t.name=="Ceiling_Filter_Panel"||t.name=="FFU_Filter")
                {var p=t.localPosition;p.y=wallHeight-(t.name=="FFU_Filter"?.08f:.03f);t.localPosition=p;}
            }
            for(int i=0;i<4;i++)Check(equipment[i].transform.position==positions[i],"Existing equipment moved.");
            var overview=GameObject.Find("FAB_OVERVIEW_CAMERA").GetComponent<Camera>();var bounds=OhtRailSurvey.BoundsOf(model);bounds.Encapsulate(floor);foreach(var o in equipment)bounds.Encapsulate(OhtRailSurvey.BoundsOf(o));
            var centre=bounds.center;var inv=Quaternion.Inverse(overview.transform.rotation);float tangent=Mathf.Tan(overview.fieldOfView*Mathf.Deg2Rad/2),distance=1;
            for(int i=0;i<8;i++){var c=new Vector3((i&1)==0?bounds.min.x:bounds.max.x,(i&2)==0?bounds.min.y:bounds.max.y,(i&4)==0?bounds.min.z:bounds.max.z);var v=inv*(c-centre);distance=Mathf.Max(distance,Mathf.Abs(v.y)/tangent-v.z,Mathf.Abs(v.x)/(tangent*1.6f)-v.z);}
            overview.transform.position=centre-overview.transform.forward*(distance*1.10f);overview.allowDynamicResolution=false;
            old=GameObject.Find("OHT_LOOP_DETAIL_CAMERA");if(old)UnityEngine.Object.DestroyImmediate(old);
            var detail=new GameObject("OHT_LOOP_DETAIL_CAMERA").AddComponent<Camera>();detail.CopyFrom(overview);detail.enabled=false;detail.targetTexture=null;
            var hd=detail.gameObject.AddComponent<HDAdditionalCameraData>();hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;hd.allowDynamicResolution=false;
            var railCentre=geometry.center;detail.transform.position=railCentre+new Vector3(10,8,-13);detail.transform.LookAt(railCentre+Vector3.down*1.6f);detail.fieldOfView=55;
            foreach(var c in Camera.allCameras)if(!c.targetTexture)c.enabled=c==overview;
            AssetDatabase.SaveAssets();EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene),"Scene save failed.");Selection.activeGameObject=model;
            if(SceneView.lastActiveSceneView)SceneView.lastActiveSceneView.AlignViewToObject(overview.transform);
            File.WriteAllText("InstallOhtLoop.result","OHT_LOOP_INSTALLED_OK\nbackup="+backup+"\nrailHeight="+layout.railHeight+" m; wallHeight="+wallHeight+" m\n4 surveyed stops align within 2mm; all 4 ion ports under delivery straight; rail spans full implanter; 7 grounded braced rear columns; closed slotted rail; upright underhung carrier; separate FOUP grip aligned; payload >0.60m above tallest tool; equipment unchanged.\nStatic installation; transport and process handoff not connected.");
            EditorApplication.delayCall+=()=>{try{Capture(overview,"Cleanroom_WithOhtLoop.png");Capture(detail,"OHT_Loop_Unity_Detail.png");File.WriteAllText("OhtLoopCapture.result","OHT_LOOP_CAPTURE_OK");}catch(Exception e){File.WriteAllText("OhtLoopCapture.result",e.ToString());}};
        }
        catch{EditorSceneManager.OpenScene(ScenePath);throw;}
    }
    static void Capture(Camera camera,string file)
    {
        var rt=new RenderTexture(1600,1050,24);rt.Create();var previous=RenderTexture.active;Texture2D texture=null;
        try{for(int i=0;i<8;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});RenderTexture.active=rt;texture=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);texture.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);texture.Apply();File.WriteAllBytes(file,texture.EncodeToPNG());}
        finally{RenderTexture.active=previous;rt.Release();UnityEngine.Object.DestroyImmediate(rt);if(texture)UnityEngine.Object.DestroyImmediate(texture);}
    }
}
#endif
