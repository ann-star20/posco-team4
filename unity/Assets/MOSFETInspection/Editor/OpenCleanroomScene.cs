#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
public static class OpenCleanroomScene
{
    const string Request="OpenCleanroom.once";
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Check;EditorApplication.update+=Check;}
    static void Check()
    {
        if(!File.Exists(Request)||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete(Request);
        try{Open();}catch(Exception e){File.WriteAllText("OpenCleanroom.result",e.ToString());Debug.LogException(e);}
    }
    [MenuItem("MOSFET Factory/Open Cleanroom Scene")]
    public static void Open()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play mode first.");
        for(int i=0;i<UnityEngine.SceneManagement.SceneManager.sceneCount;i++)
        {
            var scene=UnityEngine.SceneManagement.SceneManager.GetSceneAt(i);
            if(!scene.isDirty)continue;
            string path=scene.path;
            if(string.IsNullOrEmpty(path))path=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/BeforeCleanroomSwitch.unity");
            if(!EditorSceneManager.SaveScene(scene,path))throw new Exception("Current scene could not be saved; switch cancelled.");
        }
        const string target="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity";
        EditorSceneManager.OpenScene(target,OpenSceneMode.Single);
        var camera=GameObject.Find("FAB_OVERVIEW_CAMERA")?.GetComponent<Camera>();
        if(SceneView.lastActiveSceneView&&camera)
        {
            SceneView.lastActiveSceneView.LookAt(new Vector3(0,1,0),camera.transform.rotation,18);
            SceneView.lastActiveSceneView.Repaint();
        }
        Selection.activeObject=null;
        File.WriteAllText("OpenCleanroom.result","OPEN_CLEANROOM_OK\n"+UnityEngine.SceneManagement.SceneManager.GetActiveScene().path);
    }
}
#endif
