#if UNITY_EDITOR
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

public static class AoiDashboardSetup
{
    const string Scene="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity";
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Tick;EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(!File.Exists("AoiDashboard.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("AoiDashboard.once");try{Build();}catch(Exception e){File.WriteAllText("AoiDashboard.result",e.ToString());Debug.LogException(e);}
    }
    [MenuItem("MOSFET Factory/Install AOI Jetson Dashboard")]
    public static void Build()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play first.");
        if(UnityEngine.SceneManagement.SceneManager.GetActiveScene().isDirty&&!EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene()))throw new Exception("Save cancelled.");
        var backup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeAoiDashboard.unity");
        if(!AssetDatabase.CopyAsset(Scene,backup))throw new Exception("Backup failed");
        AoiDemoSetup.Build(true);
        var sorter=UnityEngine.Object.FindFirstObjectByType<AoiCycleDemo>();
        var feed=sorter.gameObject.AddComponent<AoiJetsonFeed>();feed.sorter=sorter;
        var screen=GameObject.Find("AOI_Inspection_Line").GetComponentsInChildren<Transform>(true).First(t=>t.name=="AOI_HMI_Screen");
        var mesh=screen.GetComponent<MeshFilter>();var vertices=mesh.sharedMesh.vertices.Select(v=>screen.TransformPoint(v)).ToArray();
        var normal=-sorter.monitor.transform.forward;var right=sorter.monitor.transform.right;var up=sorter.monitor.transform.up;
        float width=vertices.Max(v=>Vector3.Dot(v,right))-vertices.Min(v=>Vector3.Dot(v,right));
        float height=vertices.Max(v=>Vector3.Dot(v,up))-vertices.Min(v=>Vector3.Dot(v,up));
        var obj=new GameObject("AOI_DASHBOARD",typeof(RectTransform),typeof(Canvas));var r=obj.GetComponent<RectTransform>();
        r.sizeDelta=new Vector2(960,680);r.position=sorter.monitor.transform.position+normal*.004f;r.rotation=sorter.monitor.transform.rotation;
        float scale=Mathf.Min(width/960,height/680)*.96f;r.localScale=Vector3.one*scale;
        obj.GetComponent<Canvas>().renderMode=RenderMode.WorldSpace;
        var dashboard=obj.AddComponent<AoiDashboard>();feed.dashboard=dashboard;dashboard.Build(feed);sorter.monitor.GetComponent<Renderer>().enabled=false;
        sorter.product.gameObject.SetActive(false);
        EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(),Scene);AssetDatabase.SaveAssets();
        File.WriteAllText("AoiDashboard.result","AOI_DASHBOARD_INSTALLED\nbackup="+backup+"\nJetson endpoint not deployed. Default waiting, no automatic sort.");
        File.WriteAllText("AoiDashboardPlay.once","run");
    }
}
#endif
