#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class AoiWebSocketSetup
{
    [InitializeOnLoadMethod]static void Watch(){EditorApplication.update-=Tick;EditorApplication.update+=Tick;}
    static void Tick()
    {
        if(!File.Exists("AoiWebSocket.once")||EditorApplication.isCompiling||EditorApplication.isUpdating)return;
        if(EditorApplication.isPlayingOrWillChangePlaymode){EditorApplication.isPlaying=false;return;}
        File.Delete("AoiWebSocket.once");try{Install();}catch(Exception e){File.WriteAllText("AoiWebSocket.result",e.ToString());Debug.LogException(e);}
    }
    [MenuItem("MOSFET Factory/Connect AOI to WebSocket")]
    public static void Install()
    {
        if(EditorApplication.isPlaying)throw new Exception("Exit Play first");
        var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if(scene.path!="Assets/MOSFETInspection/Scenes/MOSFETSmallFab_Corrected.unity")throw new Exception("Open corrected cleanroom scene");
        if(scene.isDirty&&!EditorSceneManager.SaveScene(scene))throw new Exception("Save cancelled");
        string backup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeAoiWebSocket.unity");
        if(!AssetDatabase.CopyAsset(scene.path,backup))throw new Exception("Backup failed");
        var feed=UnityEngine.Object.FindAnyObjectByType<AoiJetsonFeed>();if(!feed)throw new Exception("AOI dashboard missing");
        var client=feed.GetComponent<AoiWebSocketClient>();if(!client)client=feed.gameObject.AddComponent<AoiWebSocketClient>();
        client.feed=feed;feed.useWebSocket=true;feed.demoMode=false;
        EditorUtility.SetDirty(feed);EditorUtility.SetDirty(client);EditorSceneManager.SaveScene(scene);
        File.WriteAllText("AoiWebSocket.result","AOI_WEBSOCKET_INSTALLED\nLocal key file referenced; key not stored in scene.\nbackup="+backup);
        File.WriteAllText("AoiWebSocketPlay.once","run");
    }
}
#endif
