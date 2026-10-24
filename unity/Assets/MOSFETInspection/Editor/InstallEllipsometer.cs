#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;

public static class InstallEllipsometer
{
    const string Base="Assets/MOSFETInspection/";
    const string ScenePath=Base+"Scenes/MOSFETSmallFab_Corrected.unity";
    [Serializable] class Record {public string name;public float[] color;public float metallic,roughness;}
    [Serializable] class Records {public Record[] items;}
    [InitializeOnLoadMethod] static void Watch(){EditorApplication.update-=Requested;EditorApplication.update+=Requested;}
    static void Requested()
    {
        if(!File.Exists("InstallEllipsometer.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("InstallEllipsometer.once");
        try{Install();}catch(Exception e){File.WriteAllText("InstallEllipsometer.result",e.ToString());Debug.LogException(e);}
    }
    static Bounds BoundsOf(GameObject obj)
    {
        var rs=obj.GetComponentsInChildren<Renderer>().Where(r=>r.enabled).ToArray();
        if(rs.Length==0)throw new Exception("No equipment geometry: "+obj.name);
        var b=rs[0].bounds;foreach(var r in rs)b.Encapsulate(r.bounds);return b;
    }
    static void PlaceLeft(GameObject obj,float left,float front)
    {var b=BoundsOf(obj);obj.transform.position+=new Vector3(left-b.min.x,-b.min.y,front-b.min.z);}
    [MenuItem("MOSFET Factory/Install Ellipsometer Between Furnace and Implant")]
    public static void Install()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play before installing.");
        var current=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(current.isDirty&&!EditorSceneManager.SaveScene(current))throw new Exception("Current scene could not be saved.");
        var scene=EditorSceneManager.OpenScene(ScenePath);
        var asset=AssetDatabase.LoadAssetAtPath<GameObject>(Base+"Models/FabEquipment/Ellipsometer_System.fbx");
        if(!asset)throw new Exception("Ellipsometer FBX import pending.");
        var oxide=GameObject.Find("Oxidation_System_Integrated");var ion=GameObject.Find("Ion_Implanter");
        if(!oxide||!ion)throw new Exception("Expected integrated furnace and ion implanter in cleanroom.");
        var backup=AssetDatabase.GenerateUniqueAssetPath(Base+"Scenes/MOSFETSmallFab_BeforeEllipsometer.unity");
        if(!AssetDatabase.CopyAsset(ScenePath,backup))throw new Exception("Scene backup failed.");
        var previous=GameObject.Find("Ellipsometer_System");if(previous)UnityEngine.Object.DestroyImmediate(previous);
        var model=(GameObject)PrefabUtility.InstantiatePrefab(asset);model.name="Ellipsometer_System";
        model.transform.rotation=oxide.transform.rotation;
        var records=JsonUtility.FromJson<Records>(File.ReadAllText(Base+"Models/FabEquipment/Ellipsometer_materials.json")).items;
        var folder=Base+"Materials/Ellipsometer";Directory.CreateDirectory(folder);
        foreach(var renderer in model.GetComponentsInChildren<Renderer>())
            renderer.sharedMaterials=renderer.sharedMaterials.Select(original=>
            {
                var record=records.FirstOrDefault(r=>r.name==original.name)??throw new Exception("Unmapped material "+original.name);
                var path=folder+"/"+record.name+".mat";var mat=AssetDatabase.LoadAssetAtPath<Material>(path);
                if(!mat){mat=new Material(Shader.Find("HDRP/Lit"));AssetDatabase.CreateAsset(mat,path);}
                var c=record.color;mat.SetColor("_BaseColor",new Color(c[0],c[1],c[2],1).gamma);
                mat.SetFloat("_Metallic",record.metallic);mat.SetFloat("_Smoothness",1-record.roughness);EditorUtility.SetDirty(mat);return mat;
            }).ToArray();
        float front=BoundsOf(oxide).min.z;
        var row=new[]{oxide,model,ion};float total=row.Sum(o=>BoundsOf(o).size.x)+1.05f;
        float roomWidth=Mathf.Max(16,Mathf.Ceil((total+1.2f)/2)*2);
        if(roomWidth>20)throw new Exception("Unexpected row width: "+total);
        var oldOxidePosition=oxide.transform.position;
        float left=-total/2;
        for(int i=0;i<row.Length;i++){PlaceLeft(row[i],left,front);left=BoundsOf(row[i]).max.x+(i==0?.45f:.60f);}
        var detail=GameObject.Find("OXIDATION_DETAIL_CAMERA");if(detail)detail.transform.position+=oxide.transform.position-oldOxidePosition;
        var shell=scene.GetRootGameObjects().First(o=>o.name.StartsWith("SMALL_FAB_"));
        var floor=shell.GetComponentsInChildren<Transform>(true).First(t=>t.name.StartsWith("Floor_"));
        float oldWidth=floor.localScale.x;float ratio=roomWidth/oldWidth;
        foreach(var t in shell.GetComponentsInChildren<Transform>(true))
        {
            if(t.name.StartsWith("Floor_")||t.name=="Rear_Wall"||t.name=="Front_Wall"||t.name=="Central_Aisle_Edge"||t.name=="Inspection_Zone_Edge")
            {var v=t.localScale;v.x=t.name.Contains("Edge")?roomWidth-1:roomWidth;t.localScale=v;}
            if(t.name=="Left_Wall"||t.name=="Right_Wall")
            {var v=t.localPosition;v.x=(t.name=="Left_Wall"?-1:1)*roomWidth/2;t.localPosition=v;}
            if(t.name=="Rear_Panel_Joint"||t.name=="Ceiling_Filter_Panel"||t.name=="FFU_Filter")
            {var v=t.localPosition;v.x*=ratio;t.localPosition=v;}
        }
        floor.name="Floor_"+roomWidth+"x12m";shell.name="SMALL_FAB_"+roomWidth+"x12m";
        var transforms=model.GetComponentsInChildren<Transform>();
        var dock=(transforms.First(t=>t.name=="LP1_Deck").position+transforms.First(t=>t.name=="LP2_Deck").position)/2;
        var face=dock-transforms.First(t=>t.name=="Transfer_Robot").position;face.y=0;
        if(Vector3.Dot(face.normalized,Vector3.back)<.99f)throw new Exception("Ellipsometer does not face aisle.");
        for(int i=0;i<row.Length;i++)
        {
            var b=BoundsOf(row[i]);
            if(Mathf.Abs(b.min.y)>.005f||b.min.x< -roomWidth/2+.3f||b.max.x>roomWidth/2-.3f||b.max.z>5.85f||b.min.z<-.55f)
                throw new Exception("Ground, wall or aisle clearance failed: "+row[i].name+" "+b);
            if(i>0&&b.min.x-BoundsOf(row[i-1]).max.x<.44f)throw new Exception("Equipment spacing failed.");
        }
        AssetDatabase.SaveAssets();EditorSceneManager.SaveScene(scene,ScenePath);
        File.WriteAllText("InstallEllipsometer.result","ELLIPSOMETER_PLACED_OK\nroom="+roomWidth+"x12m; aisle unchanged\nbackup="+backup+"\n"+string.Join("\n",row.Select(o=>o.name+" "+BoundsOf(o)))+"\nfront=-Z; floor and spacing checks PASS; no FOUP added");
        Selection.activeGameObject=model;
        EditorApplication.QueuePlayerLoopUpdate();
        EditorApplication.delayCall+=()=>Capture(GameObject.Find("FAB_OVERVIEW_CAMERA").GetComponent<Camera>());
    }
    static void Capture(Camera camera)
    {
        var rt=new RenderTexture(1600,1050,24);rt.Create();var old=RenderTexture.active;
        for(int i=0;i<4;i++)RenderPipeline.SubmitRenderRequest(camera,new RenderPipeline.StandardRequest{destination=rt});
        RenderTexture.active=rt;var image=new Texture2D(1600,1050,TextureFormat.RGB24,false);
        image.ReadPixels(new Rect(0,0,1600,1050),0,0);image.Apply();File.WriteAllBytes("Cleanroom_WithEllipsometer.png",image.EncodeToPNG());
        RenderTexture.active=old;rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(image);
    }
}
#endif
