#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

public static class InstallMiniStocker
{
    const string Base="Assets/MOSFETInspection/";
    const string ScenePath=Base+"Scenes/MOSFETSmallFab_Corrected.unity";
    [Serializable]class Record {public string name;public float[] color;public float metallic,roughness;}
    [Serializable]class Records {public Record[] items;}
    static string backup;
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Requested;EditorApplication.update+=Requested;}
    static void Requested()
    {
        if(!File.Exists("InstallMiniStocker.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("InstallMiniStocker.once");
        try{Install();}catch(Exception e){File.WriteAllText("InstallMiniStocker.result",e.ToString());Debug.LogException(e);}
    }
    static void Check(bool condition,string message){if(!condition)throw new Exception(message);}
    static Transform Find(Transform root,string name)=>root.GetComponentsInChildren<Transform>(true).FirstOrDefault(t=>t.name==name)??throw new Exception("Missing stocker node: "+name);
    static Bounds BoundsOf(GameObject obj)
    {
        var rs=obj.GetComponentsInChildren<Renderer>().Where(r=>r.enabled&&r.gameObject.activeInHierarchy).ToArray();Check(rs.Length>0,"No geometry: "+obj.name);
        var b=rs[0].bounds;foreach(var r in rs)b.Encapsulate(r.bounds);return b;
    }
    static void SetWidth(Transform obj,float left,float right)
    {var p=obj.localPosition;p.x=(left+right)*.5f;obj.localPosition=p;var s=obj.localScale;s.x=right-left;obj.localScale=s;}
    [MenuItem("MOSFET Factory/Install Six Slot Stocker")]
    public static void Install()
    {
        Check(!EditorApplication.isPlaying,"Exit Play before installation.");
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(current.isDirty)Check(EditorSceneManager.SaveScene(current),"Current scene could not be saved.");
        var scene=EditorSceneManager.OpenScene(ScenePath);
        backup=AssetDatabase.GenerateUniqueAssetPath(Base+"Scenes/MOSFETSmallFab_BeforeMiniStocker.unity");Check(AssetDatabase.CopyAsset(ScenePath,backup),"Backup failed.");
        try
        {
            var asset=AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/Stocker/Mini_Stocker_6Slot.fbx");Check(asset,"Stocker FBX import pending.");
            var oxide=GameObject.Find("Oxidation_System_Integrated");Check(oxide,"Integrated oxidation system missing.");
            var existingEquipment=new[]{oxide,GameObject.Find("Ellipsometer_System"),GameObject.Find("Ion_Implanter"),GameObject.Find("Molding_Machine"),GameObject.Find("AOI_Inspection_Line")};Check(existingEquipment.All(o=>o),"Existing process equipment missing.");
            var originalPositions=existingEquipment.Select(o=>o.transform.position).ToArray();
            var previous=GameObject.Find("Mini_Stocker_6Slot");if(previous)UnityEngine.Object.DestroyImmediate(previous);
            var model=(GameObject)PrefabUtility.InstantiatePrefab(asset);model.name="Mini_Stocker_6Slot";
            PrefabUtility.UnpackPrefabInstance(model,PrefabUnpackMode.Completely,InteractionMode.AutomatedAction);
            var origin=Find(model.transform,"Stocker_Frame_Origin");var up=Find(model.transform,"Stocker_Frame_Up").position-origin.position;var front=Find(model.transform,"Stocker_Frame_Front").position-origin.position;
            model.transform.rotation=Quaternion.Inverse(Quaternion.LookRotation(-front,up))*model.transform.rotation;
            var materialRecords=JsonUtility.FromJson<Records>(File.ReadAllText(Base+"Models/Stocker/Stocker_materials.json")).items;
            var materialFolder=Base+"Materials/Stocker";Directory.CreateDirectory(materialFolder);AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            var shader=Shader.Find("HDRP/Lit");Check(shader,"HDRP/Lit missing.");
            foreach(var renderer in model.GetComponentsInChildren<Renderer>())
            {
                renderer.sharedMaterials=renderer.sharedMaterials.Select(original=>
                {
                    var record=materialRecords.FirstOrDefault(r=>original&&r.name==original.name);Check(record!=null,"Unmapped stocker material: "+original);
                    var path=materialFolder+"/"+record.name+".mat";var m=AssetDatabase.LoadAssetAtPath<Material>(path);
                    if(!m){m=new Material(shader);AssetDatabase.CreateAsset(m,path);}
                    var c=record.color;m.SetColor("_BaseColor",new Color(c[0],c[1],c[2],1).gamma);m.SetFloat("_Metallic",record.metallic);m.SetFloat("_Smoothness",1-record.roughness);EditorUtility.SetDirty(m);return m;
                }).ToArray();
            }
            var ob=BoundsOf(oxide);var b=BoundsOf(model);
            Check(b.size.y>3&&b.size.y<3.15f&&b.size.x>2.2f&&b.size.x<2.5f,"Stocker import scale/orientation incorrect: "+b);
            model.transform.position+=new Vector3(ob.min.x-.65f-b.max.x,-b.min.y,ob.min.z-b.min.z);
            b=BoundsOf(model);var dock=Find(model.transform,"FOUP_DockPoint");origin=Find(model.transform,"Stocker_Frame_Origin");
            up=(Find(model.transform,"Stocker_Frame_Up").position-origin.position).normalized;front=(Find(model.transform,"Stocker_Frame_Front").position-origin.position).normalized;
            Check(Vector3.Dot(up,Vector3.up)>.999f&&Vector3.Dot(front,Vector3.back)>.999f,"Stocker does not stand upright/facing corridor.");
            Check(Mathf.Abs(b.min.y)<.002f&&Mathf.Abs(dock.position.y-1.10f)<.003f,"Stocker feet or I/O height mismatch.");
            Check(model.GetComponentsInChildren<Transform>(true).Count(t=>System.Text.RegularExpressions.Regex.IsMatch(t.name,@"^Slot_\d\d_DockPoint$"))==6,"Six slots not imported.");
            var shell=scene.GetRootGameObjects().First(o=>o.name.StartsWith("SMALL_FAB_"));
            Check(shell.transform.rotation==Quaternion.identity&&shell.transform.lossyScale==Vector3.one,"Unexpected cleanroom transform.");
            var transforms=shell.GetComponentsInChildren<Transform>(true);var floor=transforms.First(t=>t.name.StartsWith("Floor_"));var floorBounds=floor.GetComponent<Renderer>().bounds;
            float oldLeft=floorBounds.min.x,right=floorBounds.max.x,left=Mathf.Min(oldLeft,Mathf.Floor(b.min.x-.75f));
            SetWidth(floor,left,right);floor.name="Floor_"+(right-left).ToString("0.#")+"x12m";
            foreach(var t in transforms)
            {
                if(t.name=="Rear_Wall"||t.name=="Front_Wall")SetWidth(t,left,right);
                if(t.name=="Left_Wall"){var p=t.localPosition;p.x=left;t.localPosition=p;}
                if(t.name=="Central_Aisle_Edge"||t.name=="Inspection_Zone_Edge")SetWidth(t,left+.5f,right-.5f);
            }
            shell.name="SMALL_FAB_"+(right-left).ToString("0.#")+"x12m";
            var joint=transforms.FirstOrDefault(t=>t.name=="Rear_Panel_Joint");
            if(joint)for(float x=oldLeft-.5f;x>left+.1f;x-=1)
            {
                var o=UnityEngine.Object.Instantiate(joint.gameObject,joint.parent);o.name="Stocker_Rear_Panel_Joint";var p=o.transform.localPosition;p.x=x;o.transform.localPosition=p;
            }
            floorBounds=floor.GetComponent<Renderer>().bounds;
            Check(b.min.x>floorBounds.min.x+.3f&&b.max.x<floorBounds.max.x-.3f&&b.max.z<floorBounds.max.z-.1f,"Stocker outside cleanroom.");
            foreach(var o in existingEquipment)
            {
                var other=BoundsOf(o);bool overlaps=b.min.x<other.max.x&&b.max.x>other.min.x&&b.min.z<other.max.z&&b.max.z>other.min.z;Check(!overlaps,"Stocker overlaps "+o.name);
            }
            for(int i=0;i<existingEquipment.Length;i++)Check(existingEquipment[i].transform.position==originalPositions[i],"Existing equipment moved.");
            var overview=GameObject.Find("FAB_OVERVIEW_CAMERA").GetComponent<Camera>();
            var all=BoundsOf(model);foreach(var o in existingEquipment)all.Encapsulate(BoundsOf(o));all.Encapsulate(floorBounds);
            var centre=all.center;var inv=Quaternion.Inverse(overview.transform.rotation);float tan=Mathf.Tan(overview.fieldOfView*Mathf.Deg2Rad*.5f),distance=1;
            for(int i=0;i<8;i++)
            {
                var corner=new Vector3((i&1)==0?all.min.x:all.max.x,(i&2)==0?all.min.y:all.max.y,(i&4)==0?all.min.z:all.max.z);var v=inv*(corner-centre);
                distance=Mathf.Max(distance,Mathf.Abs(v.y)/tan-v.z,Mathf.Abs(v.x)/(tan*1.6f)-v.z);
            }
            overview.transform.position=centre-overview.transform.forward*(distance*1.10f);overview.allowDynamicResolution=false;
            var oldDetail=GameObject.Find("STOCKER_DETAIL_CAMERA");if(oldDetail)UnityEngine.Object.DestroyImmediate(oldDetail);
            var detail=new GameObject("STOCKER_DETAIL_CAMERA").AddComponent<Camera>();detail.CopyFrom(overview);detail.enabled=false;detail.targetTexture=null;
            var hd=detail.gameObject.AddComponent<HDAdditionalCameraData>();hd.antialiasing=HDAdditionalCameraData.AntialiasingMode.SubpixelMorphologicalAntiAliasing;hd.SMAAQuality=HDAdditionalCameraData.SMAAQualityLevel.High;hd.allowDynamicResolution=false;
            detail.transform.position=b.center+new Vector3(4,2.6f,-5.5f);detail.transform.LookAt(b.center);detail.fieldOfView=43;detail.nearClipPlane=.02f;
            foreach(var c in Camera.allCameras)if(!c.targetTexture)c.enabled=c==overview;
            AssetDatabase.SaveAssets();EditorSceneManager.MarkSceneDirty(scene);Check(EditorSceneManager.SaveScene(scene,ScenePath),"Scene save failed.");
            Selection.activeGameObject=model;
            if(SceneView.lastActiveSceneView)SceneView.lastActiveSceneView.LookAt(b.center,Quaternion.LookRotation(new Vector3(-.6f,-.25f,1)),6);
            File.WriteAllText("InstallMiniStocker.result","STOCKER_PLACED_OK\nbackup="+backup+"\n"+b+"\ndock="+dock.position+"\nroom="+(right-left)+"x12m\nSix slots; upright; floor contact; front faces corridor; no equipment overlap; existing equipment positions unchanged.\nPlacement only; no stocker/OHT animation installed.");
            EditorApplication.QueuePlayerLoopUpdate();EditorApplication.delayCall+=()=>{try{Capture(overview,"Cleanroom_WithStocker.png");Capture(detail,"Stocker_Unity_Detail.png");File.WriteAllText("StockerCapture.result","STOCKER_CAPTURE_OK");}catch(Exception e){File.WriteAllText("StockerCapture.result",e.ToString());}};
        }
        catch {EditorSceneManager.OpenScene(ScenePath);throw;}
    }
    static void Capture(Camera camera,string path)
    {
        var rt=new RenderTexture(1600,1000,24);rt.Create();var old=RenderTexture.active;Texture2D image=null;
        try
        {
            for(int i=0;i<8;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});
            RenderTexture.active=rt;image=new Texture2D(rt.width,rt.height,TextureFormat.RGB24,false);image.ReadPixels(new Rect(0,0,rt.width,rt.height),0,0);image.Apply();File.WriteAllBytes(path,image.EncodeToPNG());
        }
        finally{RenderTexture.active=old;rt.Release();UnityEngine.Object.DestroyImmediate(rt);if(image)UnityEngine.Object.DestroyImmediate(image);}
    }
}
#endif
