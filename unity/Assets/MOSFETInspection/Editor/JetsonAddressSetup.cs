#if UNITY_EDITOR
using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

[InitializeOnLoad]
public static class JetsonAddressSetup
{
    static JetsonAddressSetup(){EditorApplication.update+=Tick;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Tick()
    {
        if(EditorApplication.isCompiling||EditorApplication.isUpdating||EditorApplication.isPlayingOrWillChangePlaymode||!File.Exists("JetsonAddressInstall.once"))return;
        File.Delete("JetsonAddressInstall.once");
        try
        {
            var feeds=UnityEngine.Object.FindObjectsByType<AoiJetsonFeed>(FindObjectsInactive.Include);
            Check(feeds.Length>0,"Open the factory scene before applying Jetson settings");
            string backup=AssetDatabase.GenerateUniqueAssetPath("Assets/MOSFETInspection/Scenes/MOSFETSmallFab_BeforeJetsonAddress.unity");
            Check(EditorSceneManager.SaveScene(feeds[0].gameObject.scene,backup,true),"Scene backup failed");
            foreach(var feed in feeds)
            {
                feed.resultUrl="http://192.168.213.167:8080/aoi/latest";
                EditorUtility.SetDirty(feed);EditorSceneManager.MarkSceneDirty(feed.gameObject.scene);
            }
            foreach(var stream in UnityEngine.Object.FindObjectsByType<GatewayStreamClient>(FindObjectsInactive.Include))
            {
                stream.endpoint="ws://192.168.212.10:8000/api/v1/stream";EditorUtility.SetDirty(stream);EditorSceneManager.MarkSceneDirty(stream.gameObject.scene);
            }
            foreach(var bridge in UnityEngine.Object.FindObjectsByType<GatewayInspectionBridge>(FindObjectsInactive.Include))bridge.StreamAddress="ws://192.168.212.10:8000/api/v1/stream";
            PlayerPrefs.SetString("AOI.JetsonPreview.Address",AoiPreviewProtocol.DefaultAddress);PlayerPrefs.Save();
            Check(AoiPreviewProtocol.UpgradeSavedAddress("ws://192.168.10.253:8500/camera/preview")==AoiPreviewProtocol.DefaultAddress,"Saved address migration failed");
            Check(AoiPreviewProtocol.UpgradeSavedAddress("ws://custom-camera.local:8500/camera/preview")=="ws://custom-camera.local:8500/camera/preview","Unrelated custom host changed");
            Check(AoiDirectClient.Endpoint=="ws://192.168.213.167:8400/aoi","Direct AOI address mismatch");
            foreach(var feed in feeds)Check(EditorSceneManager.SaveScene(feed.gameObject.scene),"Scene save failed");
            File.WriteAllText("JetsonAddressInstall.result","JETSON_ADDRESS_INSTALL_OK\nJetson 192.168.213.167 / AOI 8400 / preview 8500 / saved preview preference updated / HTTP fallback updated / legacy address migration checked\nGateway updated: 192.168.212.10:8000\nBackup: "+backup);
            Debug.Log("JETSON_ADDRESS_INSTALL_OK");
        }
        catch(Exception e){File.WriteAllText("JetsonAddressInstall.result",e.ToString());Debug.LogException(e);}
    }
}
#endif
